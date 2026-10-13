"""One ticker's share count from VCI through vnstock, cross-checked against a second field of the same vendor.

The only module in this package that imports `vnstock`. The guard comes first, as everywhere else in the
repository: `import vnstock` would otherwise reach vnai's AI-config writers.

The count is the latest `RATIO_TTM` row of `ratio_summary()` (chosen by the integer columns `year_report` and
`quarter`, never by the string column `year`; annual `RATIO_YEAR` rows carry quarter 5 and would win an
unfiltered sort), field `number_of_shares_mkt_cap`. It is a live count, not "as of" the quarter. It is used only
when it equals every one of the four `issue_share` values of `overview()`, read by position because the four
columns share one name. Anything else (a missing field, a zero, NaN or non-integer value, no `RATIO_TTM` row, a
difference) means the count cannot be used, and the brief says so.

vnai's rate limiter does not raise: it calls `sys.exit(...)`, a `SystemExit` that `except Exception` misses.
Any `SystemExit` raised inside the call (the limiter, recognised by the repository's one recogniser, or another exit of
the library) is turned into an ordinary `ShareCountUnavailable`, so nothing the vendor does can end the brief before it
is written; `KeyboardInterrupt` is not a `SystemExit` and still interrupts. There is no wait and no retry (the brief is interactive):
the caller falls back to its cached value or to the no-size wording. The two vendor calls have no timeout of their
own (the library may retry with a back-off inside them); the brief is run by hand, so a hang is visible and
interruptible. No URL, no `requests` and no private method
is used.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
from tenacity import RetryError

from app.vnstock_guard import install as _install_vnstock_guard

_install_vnstock_guard()  # must precede any vnstock import (docs/KNOWN_ISSUES.md)

from vnstock import Company  # noqa: E402
from vnstock.core.exceptions import RateLimitError  # noqa: E402

from app.services.bulk_ingestion import _is_rate_limit_exit  # noqa: E402  one definition of vnai's exit

VENDOR_SOURCE = "vci"
COUNT_COLUMN = "number_of_shares_mkt_cap"
TYPE_COLUMN, TTM = "ratio_type", "RATIO_TTM"
OVERVIEW_FIELD = "issue_share"
EXPECTED_OVERVIEW_VALUES = 4  # the overview carries four columns of this name; fewer means the field changed
_MAX_COUNT = 10**13  # above any listed share count: not a count
_YEARS, _QUARTERS = range(1990, 2101), range(1, 5)  # the same bounds the cache applies when it reads a period back
# A listed ticker is upper-case letters and digits. The symbol ends up in the vendor's request, so anything else
# is refused here instead of being trusted to the library.
_TICKER = re.compile(r"[A-Z0-9]{1,12}")


class ShareCountUnavailable(Exception):
    """No usable share count this run: the limiter, a vendor failure, a missing field or an unusable frame.
    It carries no vendor text (the limiter's message is long and promotional)."""

    disagree = False  # the brief reads this attribute, so it never imports this module


class ShareCountsDisagree(ShareCountUnavailable):
    """The two vendor fields give different counts, so neither is used."""

    disagree = True


@dataclass(frozen=True)
class ShareCountReading:
    count: int
    year_report: int
    quarter: int


FramesFn = Callable[[str], tuple[pd.DataFrame, pd.DataFrame]]  # (ratio_summary, overview)


def parse_ticker(text: str) -> str:
    """The ticker if it is a plain upper-case symbol, else `ValueError`."""
    if not _TICKER.fullmatch(text or ""):
        raise ValueError(f"not a plain upper-case ticker: {text!r}")
    return text


def vendor_frames(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The two VCI frames for `symbol`: two vendor calls."""
    company = Company(source=VENDOR_SOURCE, symbol=symbol)
    return company.ratio_summary(), company.overview()


def read_share_count(ticker: str, *, frames: FramesFn = vendor_frames) -> ShareCountReading:
    """The cross-checked share count of `ticker`, or `ShareCountUnavailable` (`ShareCountsDisagree` for a difference).

    `frames` is the vendor call, replaceable so a test makes no network request. A rate-limit `SystemExit` becomes
    `ShareCountUnavailable`; any other `SystemExit` is raised unchanged.
    """
    parse_ticker(ticker)
    try:
        ratio, overview = frames(ticker)
    except SystemExit as exit_request:
        # vnai's limiter or any other library exit: neither may end the brief before it is written. KeyboardInterrupt is not
        # a SystemExit and still interrupts. Nothing the library said is carried (the limiter's text is promotional).
        reason = "vnai rate limit" if _is_rate_limit_exit(exit_request) else "the vendor library ended the call (SystemExit)"
        raise ShareCountUnavailable(reason) from None
    except RetryError as error:
        underlying = error.last_attempt.exception()
        kind = "rate limit" if isinstance(underlying, RateLimitError) else type(underlying).__name__
        raise ShareCountUnavailable(f"vendor call failed ({kind})") from None
    except RateLimitError:
        raise ShareCountUnavailable("vendor rate limit") from None
    except Exception as error:  # noqa: BLE001 - whatever the vendor raised, the size line falls back
        raise ShareCountUnavailable(f"vendor call failed ({type(error).__name__})") from None
    try:
        reading = _latest_ttm_count(ratio)
        _cross_check(reading.count, overview)
    except ShareCountUnavailable:
        raise
    except (ValueError, TypeError, KeyError) as error:  # a frame of an unexpected shape, for example a duplicated column
        raise ShareCountUnavailable(f"the vendor frames could not be read ({type(error).__name__})") from None
    return reading


def _whole_number(value: object) -> int | None:
    """A positive whole number below `_MAX_COUNT`, else None (NaN, a fraction, a bool or text is not a count)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):  # OverflowError: an integer too large for a float
        return None
    if not math.isfinite(number) or not number.is_integer() or not 0 < number < _MAX_COUNT:
        return None
    return int(number)


def _latest_ttm_count(ratio: object) -> ShareCountReading:
    if not isinstance(ratio, pd.DataFrame) or not {TYPE_COLUMN, COUNT_COLUMN, "year_report", "quarter"} <= set(ratio.columns):
        raise ShareCountUnavailable("the ratio summary lacks a needed column")
    rows = ratio[ratio[TYPE_COLUMN] == TTM].copy()
    rows["_year"] = pd.to_numeric(rows["year_report"], errors="coerce")
    rows["_quarter"] = pd.to_numeric(rows["quarter"], errors="coerce")
    rows = rows.dropna(subset=["_year", "_quarter"])
    rows = rows[(rows["_year"] % 1 == 0) & (rows["_quarter"] % 1 == 0)]
    if rows.empty:
        raise ShareCountUnavailable("the ratio summary has no usable RATIO_TTM row")
    latest = rows.sort_values(["_year", "_quarter"], kind="stable").iloc[-1]
    count = _whole_number(latest[COUNT_COLUMN])
    if count is None:
        raise ShareCountUnavailable("the latest RATIO_TTM row has no usable share count")
    year, quarter = int(latest["_year"]), int(latest["_quarter"])
    if year not in _YEARS or quarter not in _QUARTERS:
        raise ShareCountUnavailable("the latest RATIO_TTM row has an implausible period")
    return ShareCountReading(count, year, quarter)


def _cross_check(count: int, overview: object) -> None:
    """`count` must equal every `issue_share` value of the overview, read by position (the names are duplicated)."""
    if not isinstance(overview, pd.DataFrame) or overview.empty:
        raise ShareCountUnavailable("the overview is empty")
    positions = [i for i, name in enumerate(overview.columns) if name == OVERVIEW_FIELD]
    if len(positions) < EXPECTED_OVERVIEW_VALUES:
        raise ShareCountUnavailable("the overview lacks the issued-share fields")
    values = [_whole_number(overview.iat[0, i]) for i in positions]
    if None in values:
        raise ShareCountUnavailable("an issued-share value of the overview is unusable")
    if any(value != count for value in values):
        raise ShareCountsDisagree("the vendor's two share counts disagree")
