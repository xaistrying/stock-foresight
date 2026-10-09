"""Does the volatility band's coverage differ by market regime (VN-Index volatility percentile)?

STUDY OUTPUT, not shown to any user. READ-ONLY over `backend/data/app.db` (mode=ro): it writes no
table and no model file. Its only possible writes are the index CSV named by `--fetch-index` and the
report named by `--json`.

The question (openspec change evaluate-band-coverage-by-market-regime, design.md): the typical
5-session band is `range_k x sqrt(5) x sigma_daily_pct(t)`. Within each market-regime third, how often
does it contain the realised 5-session move |ln(close[t+5]/close[t])|? Regime at t is the percentile
of the VN-Index's 20-session volatility within its own trailing 252 sessions, cut into thirds, so it
uses closes up to t only. The band is measured out of time with the expanding walk-forward by calendar
year that `train_har_rv.py` defines, split early/late at SPLIT_DATE, with month-block bootstrap
intervals. The outcome is PASS, KILL or INCONCLUSIVE by the rule in the spec, applied by code below.

Rules honoured unchanged. Rule 1: the outcome is `build_window_frame`'s 5-session r5 (a session is
one stored OHLCV row). Rule 2: every printed rate is a percentage. Rule 3: the regime cut-offs are
percentiles, and nothing here is a threshold on the size of a price move. Rule 4: no reliability
figure reaches an API, the UI or an export; this is a developer printout. Rules 5 and 6: no verdict,
Agreement or model text is produced, and the output is a technical observation, not investment advice.

Index history comes from the vendor's Unified UI index call (the Macro agent's path), never from the
stocks being evaluated (a stock-derived market proxy is circular with the coverage being tested). It
needs no API key and sends a symbol and a date range only. `vnstock` is licensed for personal,
research and non-commercial use; this study is inside that (not legal advice).

Run from the project root:
    python backend/scripts/evaluate_band_coverage_by_regime.py --depth-only
    python backend/scripts/evaluate_band_coverage_by_regime.py --fetch-index backend/data/study_cache/vnindex_closes.csv --json OUT.json
    python backend/scripts/evaluate_band_coverage_by_regime.py --index-csv backend/data/study_cache/vnindex_closes.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # backend/, for `app`
sys.path.insert(0, str(HERE))  # scripts/, for the sibling `train_har_rv`

from app.vnstock_guard import install as install_vnstock_guard  # noqa: E402

install_vnstock_guard()  # must precede any vnstock import (docs/KNOWN_ISSUES.md); the fetch helpers import it lazily

# ---------------------------------------------------------------------------
# The criterion. These constants are NEW, PROVISIONAL and covered by no domain rule: none is a
# threshold on the size of a price move (Rule 3 is not engaged). They are fixed in
# specs/band-coverage-regime-evaluation/spec.md and here BEFORE any real run; changing one after a
# result has been seen is a new change, not an edit.
# ---------------------------------------------------------------------------
PASS_GAP = 0.05  # calmest minus most volatile third, as a fraction of coverage (5 points); the owner's decision 8
SPLIT_DATE = "2023-01-01"  # early: window dates before it; the Fibonacci study's split
VOL_WINDOW = 20  # sessions of daily log returns behind the index volatility (the HAR feature rv20)
PERCENTILE_WINDOW = 252  # sessions of index volatility the percentile is taken within
CONFIDENCE = 0.95  # month-block bootstrap percentile interval
BOOTSTRAP_RESAMPLES = 2000
SEED = 0
MIN_MONTHS_PER_HALF = 24  # distinct calendar months with a regime in a half
MIN_MONTHS_PER_CELL = 8  # ... and in each of its calmest and most volatile thirds
MIN_DATES_PER_YEAR_CELL = 20  # distinct dates a year's third needs to enter the year-adjusted gap
MIN_INDEX_MATCH = 0.99  # share of test dates that must have an index close
CALM, MIDDLE, VOLATILE = "calm", "middle", "volatile"
REVIEWER_REPORTED_BY_YEAR = (0.614, 0.741)  # reviewer-reported, not re-verified when the change was written

# Index history fetch (design Decisions 3-5). A request starts where the stored stock history does.
INDEX_SYMBOL = "VNINDEX"
INDEX_FIRST_DATE = "2016-01-01"
INDEX_FLOOR_DATE = "2019-12-31"  # design Decision 4: about seven years before the 2026-10 end date
FETCH_PACE_SECONDS = 5.0  # between consecutive vendor calls (about 20 requests a minute without a key)
MAX_FETCH_CALLS = 6  # the first call plus walking `end` backwards
GAP_DAYS = 10  # calendar gaps longer than this are reported
HISTORY_LIMIT_MARKERS = ("limited to", "giới hạn")  # the vendor's logged history-limit warning

HEADER = (
    "STUDY OUTPUT, not shown to any user (Rule 4); a technical observation, not investment advice (Rule 6)."
)


# ---------------------------------------------------------------------------
# Index history from the vendor
# ---------------------------------------------------------------------------
class IndexRateLimited(RuntimeError):
    """The vendor's rate limiter ended a call; no series was produced."""


@dataclass(frozen=True)
class IndexHistory:
    closes: pd.Series  # 'YYYY-MM-DD' -> close, one row per date, ascending
    calls: list[dict]  # one entry per vendor call: end, count, rows, first, last
    history_limit_warning: bool
    warnings: tuple[str, ...]


def _index_handle():
    """`Market().index("VNINDEX")`, imported after the guard so vnstock cannot write AI-config files."""
    install_vnstock_guard()
    from vnstock.ui import Market  # noqa: E402 — after the guard above

    return Market().index(INDEX_SYMBOL)


def _rate_limit_errors() -> tuple[type[BaseException], ...]:
    """The rate-limit exceptions the installed vnstock 4.0.5 has (the skill names a module that does not exist)."""
    install_vnstock_guard()
    from vnstock.core.exceptions import RateLimitError  # noqa: E402 — after the guard above

    errors: list[type[BaseException]] = [RateLimitError]
    try:
        from vnai.beam.quota import RateLimitExceeded
    except ImportError:
        pass
    else:
        errors.append(RateLimitExceeded)
    return tuple(errors)


def closes_from_frame(df: pd.DataFrame) -> pd.Series:
    """Closes indexed by 'YYYY-MM-DD', one per date, the later row of a date winning.

    The live frame can repeat the latest session (same date, two rows, measured on VNINDEX), as
    `macro._market_closes` documents. A frame without a `time` column raises, as it does there.
    """
    if df is None or df.empty:
        return pd.Series(dtype="float64")
    if "time" not in df.columns or "close" not in df.columns:
        raise KeyError(f"time column missing from market frame: {list(df.columns)[:6]}")
    closes = pd.Series(
        df["close"].astype("float64").to_numpy(), index=pd.to_datetime(df["time"]).dt.strftime("%Y-%m-%d")
    )
    if not (np.isfinite(closes.to_numpy()).all() and (closes > 0).all()):
        raise ValueError("index frame has a missing or non-positive close")
    return closes[~closes.index.duplicated(keep="last")].sort_index()


def _call_index(handle, start: str, end: str, source: str | None, calls: list[dict]) -> pd.Series:
    """One vendor call with an explicit `count` (never omitted: the default of 100 rows truncates silently)."""
    count = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1  # at least the sessions in the span
    kwargs = {"start": start, "end": end, "count": count} | ({"source": source} if source else {})
    try:
        frame = handle.ohlcv(**kwargs)
    except SystemExit as exit_request:
        from app.services.bulk_ingestion import _is_rate_limit_exit  # imports vnstock: after the guard

        if not _is_rate_limit_exit(exit_request):
            raise
        raise IndexRateLimited(str(exit_request.code)) from None
    except Exception as error:
        if isinstance(error, _rate_limit_errors()):
            raise IndexRateLimited(str(error)) from None
        raise
    closes = closes_from_frame(frame)
    calls.append({
        "end": end, "count": count, "rows": int(len(closes)),
        "first": closes.index[0] if len(closes) else None, "last": closes.index[-1] if len(closes) else None,
    })
    return closes


def fetch_index_closes(start: str, end: str, *, handle=None, source: str | None = None) -> pd.Series:
    """One call for VN-Index closes in [start, end]; raises when the vendor returns no rows."""
    closes = _call_index(handle or _index_handle(), start, end, source, [])
    if closes.empty:
        raise ValueError(f"the vendor returned no rows for {INDEX_SYMBOL} {start}..{end}")
    return closes


class _HistoryLimitWatcher(logging.Handler):
    """Records the vendor's logged (not raised) history-limit warning."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        text = record.getMessage()
        if any(marker in text.lower() for marker in HISTORY_LIMIT_MARKERS):
            self.messages.append(text.splitlines()[0][:160])


@contextmanager
def _watching_history_limit():
    watcher = _HistoryLimitWatcher()
    root = logging.getLogger()
    root.addHandler(watcher)
    try:
        yield watcher
    finally:
        root.removeHandler(watcher)


def fetch_index_history(
    start: str, end: str, *, need_start: str, handle=None, source: str | None = None, sleep=None
) -> IndexHistory:
    """VN-Index closes from `start` to `end`, walking `end` backwards while the first date is later than `need_start`.

    The vendor truncates silently (design Decision 4), so when the first call does not reach
    `need_start` the call is repeated with `end` just before the earliest date returned, until that
    date stops moving. Calls are paced. A rate limit raises `IndexRateLimited` and returns no partial series.
    """
    handle = handle or _index_handle()
    sleep = sleep or time.sleep
    calls: list[dict] = []
    with _watching_history_limit() as watcher:
        closes = _call_index(handle, start, end, source, calls)
        if closes.empty:
            raise ValueError(f"the vendor returned no rows for {INDEX_SYMBOL} {start}..{end}")
        while closes.index[0] > need_start and len(calls) < MAX_FETCH_CALLS:
            earlier_end = (date.fromisoformat(closes.index[0]) - timedelta(days=1)).isoformat()
            if earlier_end < start:
                break
            sleep(FETCH_PACE_SECONDS)
            earlier = _call_index(handle, start, earlier_end, source, calls)
            if earlier.empty or earlier.index[0] >= closes.index[0]:
                break  # the earliest date stopped moving
            closes = pd.concat([earlier, closes])
    return IndexHistory(
        closes[~closes.index.duplicated(keep="last")].sort_index(),
        calls, bool(watcher.messages), tuple(dict.fromkeys(watcher.messages)),
    )


def index_depth(closes: pd.Series) -> dict:
    """First and last date, sessions and calendar gaps over GAP_DAYS of an index series."""
    dates = pd.to_datetime(pd.Series(closes.index))
    days = dates.diff().dt.days
    gaps = [
        (closes.index[i - 1], closes.index[i], int(days.iloc[i]))
        for i in range(1, len(closes)) if days.iloc[i] > GAP_DAYS
    ]
    return {
        "first_date": closes.index[0], "last_date": closes.index[-1],
        "sessions": int(len(closes)), "gaps_over_10_days": gaps,
    }


def _versions() -> dict:
    return {name: metadata.version(name) for name in ("vnstock", "vnai")}


def format_depth(history: IndexHistory, source: str | None) -> str:
    depth = index_depth(history.closes)
    reached = depth["first_date"] <= INDEX_FLOOR_DATE
    lines = [
        f"VN-Index history depth: Market.index('{INDEX_SYMBOL}').ohlcv, source "
        f"{source or 'default (kbs)'}, versions {_versions()}",
        f"  first date: {depth['first_date']}   last date: {depth['last_date']}   sessions: {depth['sessions']}",
        "  calendar gaps over 10 days: "
        + ("none" if not depth["gaps_over_10_days"] else str(depth["gaps_over_10_days"])),
        f"  vendor history-limit warning logged: {'yes' if history.history_limit_warning else 'no'}"
        + (f" {list(history.warnings)}" if history.warnings else ""),
        f"  floor for the study (Decision 4): first date <= {INDEX_FLOOR_DATE}: {'reached' if reached else 'NOT reached'}",
    ]
    lines += [f"  call {i}: {c}" for i, c in enumerate(history.calls, 1)]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--depth-only", action="store_true", help="fetch, print the index depth and exit; reads no database")
    parser.add_argument("--source", choices=("kbs", "vci"), default=None, help="pin the vendor source (default: the vendor's)")
    args = parser.parse_args(argv)

    print(HEADER)
    if args.depth_only:
        try:
            history = fetch_index_history(
                INDEX_FIRST_DATE, date.today().isoformat(), need_start=INDEX_FLOOR_DATE,
                source=args.source, sleep=time.sleep,
            )
        except IndexRateLimited as error:
            sys.exit(f"ERROR: the vendor's rate limit ended the call ({error}); no series was written.")
        print(format_depth(history, args.source))
        return
    parser.error("only --depth-only is implemented so far")


if __name__ == "__main__":
    main()
