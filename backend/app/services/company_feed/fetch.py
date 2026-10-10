"""Fetch VCI company news and events through the project's vnstock wrapper.

The only module in this package that imports `vnstock`. The guard comes first, as in
`ticker_ingestion.py`: `import vnstock` would otherwise reach vnai's AI-config writers.

The Unified UI (`Reference().company(symbol)`) is the wrapper, and `source="vci"` is passed on
every call because `CompanyReference.news` and `.events` default to `"kbs"`. No URL, no `requests`
and no private `_fetch_*` method is used: those are paged and would bypass the wrapper.

vnai's rate limiter does not raise: it calls `sys.exit(...)`, a `SystemExit` that
`except Exception` misses and that, raised in a server process, ends the server. That is why the
snapshot is a script (design Decision 1). Here the exit is turned into an ordinary `RateLimited`
exception so the caller can wait and retry; any other `SystemExit` is a real exit request and
passes through. `RateLimitExceeded` is not imported from `vnstock.core.quota`: that module does
not exist in vnstock 4.0.5 (it lives in `vnai/beam/quota.py` and surfaces as the exit above).
"""

from __future__ import annotations

import re
from importlib import metadata

import pandas as pd
from tenacity import RetryError

from app.vnstock_guard import install as _install_vnstock_guard

_install_vnstock_guard()  # must precede any vnstock import (docs/KNOWN_ISSUES.md)

from vnstock.core.exceptions import RateLimitError  # noqa: E402
from vnstock.ui import Reference  # noqa: E402

from app.services.bulk_ingestion import _is_rate_limit_exit  # noqa: E402  one definition of vnai's exit
from app.services.company_feed.normalise import VENDOR_KINDS, UnexpectedFrame, require_columns  # noqa: E402

VENDOR_SOURCE = "vci"
VENDOR_ITEM_CAP = 50  # the vendor's page size, measured 2026-10-09; not a choice

# A listed ticker is upper-case letters and digits. The symbol ends up in the vendor's request URL, so
# anything else is refused here instead of being trusted to the library.
_TICKER = re.compile(r"[A-Z0-9]{1,12}")


class RateLimited(Exception):
    """vnai's rate limiter (a `SystemExit`) or vnstock's `RateLimitError`, as an ordinary exception.
    It carries no vendor text: the limiter's message is long and promotional."""


def parse_ticker(text: str) -> str:
    """The ticker if it is a plain upper-case symbol, else `ValueError`."""
    if not _TICKER.fullmatch(text or ""):
        raise ValueError(f"not a plain upper-case ticker: {text!r}")
    return text


def installed_vnstock_version() -> str | None:
    try:
        return metadata.version("vnstock")
    except metadata.PackageNotFoundError:
        return None


def _call_vendor(symbol: str, kind: str) -> object:
    return getattr(Reference().company(symbol), kind)(source=VENDOR_SOURCE)


def _unwrap(error: RetryError) -> BaseException:
    """The `@retry`-wrapped vendor methods raise `RetryError`; classify what their last attempt raised."""
    underlying = error.last_attempt.exception()
    return underlying if isinstance(underlying, Exception) else error


def fetch_company_frame(symbol: str, kind: str) -> pd.DataFrame:
    """One VCI frame (`news` or `events`) for `symbol`: at most `VENDOR_ITEM_CAP` rows.

    Raises `RateLimited` for vnai's limiter or `RateLimitError`, `UnexpectedFrame` for a reply that is
    not a frame or a non-empty frame lacking a required column, whatever the vendor raised otherwise
    (a `RetryError` unwrapped to its last exception), and any non-rate-limit `SystemExit` unchanged.
    An empty frame is returned as is: a quiet ticker is a normal answer.
    """
    parse_ticker(symbol)
    if kind not in VENDOR_KINDS:
        raise ValueError(f"unknown vendor kind {kind!r}; expected one of {VENDOR_KINDS}")
    try:
        frame = _call_vendor(symbol, kind)
    except SystemExit as exit_request:
        if not _is_rate_limit_exit(exit_request):
            raise
        raise RateLimited(f"vnai rate limit on {symbol} {kind}") from None  # its promotional text stays out of logged tracebacks
    except RetryError as error:
        underlying = _unwrap(error)
        if isinstance(underlying, RateLimitError):
            raise RateLimited(f"vnstock rate limit on {symbol} {kind}") from underlying
        if underlying is error:
            raise
        raise underlying from error
    except RateLimitError as error:
        raise RateLimited(f"vnstock rate limit on {symbol} {kind}") from error

    if not isinstance(frame, pd.DataFrame):
        raise UnexpectedFrame(f"{kind} reply is {type(frame).__name__}, not a DataFrame")
    require_columns(frame, kind)
    return frame
