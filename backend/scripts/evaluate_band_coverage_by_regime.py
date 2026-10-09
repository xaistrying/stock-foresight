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
from numpy.lib.stride_tricks import sliding_window_view

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # backend/, for `app`
sys.path.insert(0, str(HERE))  # scripts/, for the sibling `train_har_rv`

from app.vnstock_guard import install as install_vnstock_guard  # noqa: E402

install_vnstock_guard()  # must precede any vnstock import (docs/KNOWN_ISSUES.md); the fetch helpers import it lazily

from app.db.connection import DB_PATH, open_readonly  # noqa: E402
from app.ml.volatility import FEATURE_NAMES, scaled_band, sigma_pct  # noqa: E402
from app.services.ticker_universe import modelling_universe  # noqa: E402
from train_har_rv import MIN_TRAIN_ROWS, RANGE_COVERAGE, fit_fold, load_frame, split_fold  # noqa: E402

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


# ---------------------------------------------------------------------------
# Regime: trailing percentile of the index's volatility, in thirds (design Decision 2)
# ---------------------------------------------------------------------------
REGIMES = (CALM, MIDDLE, VOLATILE)


def index_volatility(closes: pd.Series) -> pd.Series:
    """Std of the last VOL_WINDOW daily log returns at each session (the HAR feature rv20); NaN until it has 20."""
    return np.log(closes / closes.shift(1)).rolling(VOL_WINDOW).std()


def trailing_percentile(sigma: pd.Series) -> pd.Series:
    """Share of the last PERCENTILE_WINDOW volatility values, the current one included, at or below the current one.

    NaN until PERCENTILE_WINDOW values exist, so the first regime is the 271st session. Only values up to
    and including each session are used (no look-ahead).
    """
    valid = sigma.dropna()
    percentile = pd.Series(np.nan, index=sigma.index)
    if len(valid) >= PERCENTILE_WINDOW:
        windows = sliding_window_view(valid.to_numpy(), PERCENTILE_WINDOW)
        percentile.loc[valid.index[PERCENTILE_WINDOW - 1:]] = (windows <= windows[:, -1:]).mean(axis=1)
    return percentile


def expanding_percentile(sigma: pd.Series) -> pd.Series:
    """The same with every prior volatility value instead of the last PERCENTILE_WINDOW (sensitivity only)."""
    valid = sigma.dropna()
    values = valid.to_numpy()
    percentile = pd.Series(np.nan, index=sigma.index)
    for i in range(PERCENTILE_WINDOW - 1, len(values)):
        percentile.loc[valid.index[i]] = np.count_nonzero(values[: i + 1] <= values[i]) / (i + 1)
    return percentile


def label_thirds(percentile: pd.Series) -> pd.Series:
    """'calm' up to one third, 'volatile' above two thirds, else 'middle'; NaN stays NaN."""
    labels = np.where(percentile <= 1 / 3, CALM, np.where(percentile > 2 / 3, VOLATILE, MIDDLE))
    return pd.Series(labels, index=percentile.index, dtype=object).where(percentile.notna())


def regime_labels(closes: pd.Series, *, expanding: bool = False) -> pd.Series:
    """The regime of every index session ('calm', 'middle', 'volatile'), NaN while there is too little history."""
    percentile = expanding_percentile if expanding else trailing_percentile
    return label_thirds(percentile(index_volatility(closes)))


def attach_regime(windows: pd.DataFrame, labels: pd.Series) -> tuple[pd.DataFrame, dict]:
    """Windows (columns date, hit) that have a regime, and counts of those that do not and why.

    A window whose date has no index close, or whose session is inside the warm-up, is excluded and
    counted; it is never assigned a third.
    """
    regime = windows["date"].map(labels)
    has_close = windows["date"].isin(labels.index)
    distinct = windows["date"].drop_duplicates()
    with_close = int(distinct.isin(labels.index).sum())
    kept = windows.assign(regime=regime)[regime.notna()].reset_index(drop=True)
    return kept, {
        "windows": int(len(windows)), "no_index_close": int((~has_close).sum()),
        "warm_up": int((has_close & regime.isna()).sum()), "with_regime": int(len(kept)),
        "test_dates": int(len(distinct)), "dates_with_index_close": with_close,
        "index_match": with_close / len(distinct) if len(distinct) else float("nan"),
    }


def episode_counts(labels: pd.Series) -> dict:
    """Regime episodes: maximal runs of consecutive sessions in one third."""
    values = labels.dropna().to_numpy(dtype=object)
    starts = np.ones(len(values), dtype=bool)
    starts[1:] = values[1:] != values[:-1]
    return {regime: int((values[starts] == regime).sum()) for regime in REGIMES}


# ---------------------------------------------------------------------------
# Gaps, month-block intervals and cell statistics (design Decision 7)
#
# `cells` has one row per (date, regime): the hits and windows on that date. Every window of a date
# shares the index's regime, so a date is one cell and a month is one block.
# ---------------------------------------------------------------------------
def cell_table(windows: pd.DataFrame) -> pd.DataFrame:
    """Per-date, per-regime hits and window counts from windows with columns date, hit, regime."""
    grouped = windows.groupby(["date", "regime"], sort=True)["hit"]
    return pd.DataFrame({"hits": grouped.sum(), "n": grouped.size()}).reset_index()


def split_halves(cells: pd.DataFrame) -> dict[str, pd.DataFrame]:
    early = cells["date"] < SPLIT_DATE
    return {"early": cells[early].reset_index(drop=True), "late": cells[~early].reset_index(drop=True)}


def _block_key(dates: pd.Series, block: str) -> pd.Series:
    if block == "month":
        return dates.str[:7]
    if block == "quarter":
        return dates.str[:4] + "Q" + ((dates.str[5:7].astype(int) - 1) // 3 + 1).astype(str)
    raise ValueError(f"unknown block {block!r}")


def _block_sums(cells: pd.DataFrame, block: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Hits and windows per block, for the calm and the volatile third, over every block that has any window."""
    codes, blocks = pd.factorize(_block_key(cells["date"], block), sort=True)
    hits, windows = cells["hits"].to_numpy(float), cells["n"].to_numpy(float)
    sums = {}
    for regime in (CALM, VOLATILE):
        mask = (cells["regime"] == regime).to_numpy()
        sums[regime] = (
            np.bincount(codes[mask], weights=hits[mask], minlength=len(blocks)),
            np.bincount(codes[mask], weights=windows[mask], minlength=len(blocks)),
        )
    return sums


def _gap_draws(sums: dict, picks: np.ndarray) -> np.ndarray:
    """The calm-minus-volatile gap of each resample (rows of block indices); NaN where a third is empty."""
    (calm_hits, calm_n), (volatile_hits, volatile_n) = sums[CALM], sums[VOLATILE]
    calm_windows, volatile_windows = calm_n[picks].sum(axis=1), volatile_n[picks].sum(axis=1)
    ok = (calm_windows > 0) & (volatile_windows > 0)
    gaps = np.full(len(picks), np.nan)
    gaps[ok] = np.divide(calm_hits[picks[ok]].sum(axis=1), calm_windows[ok]) - np.divide(
        volatile_hits[picks[ok]].sum(axis=1), volatile_windows[ok]
    )
    return gaps


def _point_gap(sums: dict) -> float | None:
    (calm_hits, calm_n), (volatile_hits, volatile_n) = sums[CALM], sums[VOLATILE]
    if calm_n.sum() == 0 or volatile_n.sum() == 0:
        return None
    return float(calm_hits.sum() / calm_n.sum() - volatile_hits.sum() / volatile_n.sum())


def _percentile_interval(draws: np.ndarray) -> tuple[float, float] | tuple[None, None]:
    draws = draws[np.isfinite(draws)]
    if len(draws) == 0:
        return (None, None)
    tail = (1 - CONFIDENCE) / 2 * 100
    low, high = np.percentile(draws, [tail, 100 - tail])
    return float(low), float(high)


def _interval_result(gap: float | None, draws: np.ndarray | None, blocks: int) -> dict:
    ci = _percentile_interval(draws) if draws is not None else (None, None)
    return {
        "gap": gap, "ci": ci, "blocks": blocks,
        "half_width": None if ci[0] is None else (ci[1] - ci[0]) / 2,
        "dropped_share": None if draws is None else float(np.isnan(draws).mean()),
    }


def gap_interval(cells: pd.DataFrame, block: str = "month") -> dict:
    """Calm-minus-volatile coverage gap with a 95% block-bootstrap percentile interval.

    Whole blocks (calendar months, or quarters for the cross-check) are resampled so every window of a
    date moves together. Draws with an empty third are dropped and their share reported.
    """
    if cells.empty:
        return _interval_result(None, None, 0)
    sums = _block_sums(cells, block)
    blocks = len(sums[CALM][0])
    gap = _point_gap(sums)
    if gap is None:
        return _interval_result(None, None, blocks)
    picks = np.random.default_rng(SEED).integers(0, blocks, size=(BOOTSTRAP_RESAMPLES, blocks))
    return _interval_result(gap, _gap_draws(sums, picks), blocks)


def interval_disagreement(month_ci: tuple, quarter_ci: tuple) -> bool:
    """Whether the two intervals disagree about excluding zero (printed; it does not change the outcome)."""
    return _excludes_zero(month_ci) != _excludes_zero(quarter_ci)


def year_adjusted_gap(cells: pd.DataFrame) -> dict | None:
    """Equal-weighted mean of each calendar year's own gap, so a gap that only restates year-to-year variation fails.

    Only years in which the calmest and the most volatile third each have windows on at least
    MIN_DATES_PER_YEAR_CELL dates enter. The interval is a month-block bootstrap stratified by year
    (months resampled within each year). Draws with an empty third in any year are dropped.
    """
    if cells.empty:
        return None
    by_year = {}
    for year, group in cells.groupby(cells["date"].str[:4]):
        dates = {regime: group.loc[group["regime"] == regime, "date"].nunique() for regime in (CALM, VOLATILE)}
        if min(dates.values()) >= MIN_DATES_PER_YEAR_CELL:
            by_year[int(year)] = _block_sums(group, "month")
    if not by_year:
        return None
    rng = np.random.default_rng(SEED)
    year_gaps, draws = [], []
    for sums in by_year.values():
        year_gaps.append(_point_gap(sums))
        months = len(sums[CALM][0])
        draws.append(_gap_draws(sums, rng.integers(0, months, size=(BOOTSTRAP_RESAMPLES, months))))
    mean_draws = np.mean(draws, axis=0)  # NaN where any year's draw had an empty third
    result = _interval_result(float(np.mean(year_gaps)), mean_draws, sum(len(s[CALM][0]) for s in by_year.values()))
    return result | {"years": sorted(by_year)}


def cell_stats(cells: pd.DataFrame, labels: pd.Series) -> dict:
    """Per third: windows, distinct dates and months, regime episodes, coverage, and the mean and sd of the per-date coverage."""
    episodes = episode_counts(labels.reindex(sorted(cells["date"].unique())))
    stats = {}
    for regime in REGIMES:
        cell = cells[cells["regime"] == regime]
        windows = int(cell["n"].sum())
        per_date = cell["hits"].to_numpy(float) / cell["n"].to_numpy(float) if len(cell) else np.array([])
        stats[regime] = {
            "windows": windows, "dates": int(cell["date"].nunique()), "months": int(cell["date"].str[:7].nunique()),
            "episodes": episodes[regime],
            "coverage": float(cell["hits"].sum() / windows) if windows else None,
            "date_mean": float(per_date.mean()) if len(per_date) else None,
            "date_sd": float(per_date.std(ddof=1)) if len(per_date) > 1 else None,
        }
    return stats


def evaluate_half(cells: pd.DataFrame, labels: pd.Series) -> dict:
    """Everything the outcome rule and the report need for one half."""
    month, quarter = gap_interval(cells, "month"), gap_interval(cells, "quarter")
    stats = cell_stats(cells, labels) if len(cells) else {regime: None for regime in REGIMES}
    return {
        "gap": month["gap"], "ci": month["ci"], "half_width": month["half_width"],
        "dropped_share": month["dropped_share"],
        "quarter_ci": quarter["ci"], "quarter_half_width": quarter["half_width"],
        "disagreement": interval_disagreement(month["ci"], quarter["ci"]),
        "months": int(cells["date"].str[:7].nunique()) if len(cells) else 0,
        "calm_months": stats[CALM]["months"] if stats[CALM] else 0,
        "volatile_months": stats[VOLATILE]["months"] if stats[VOLATILE] else 0,
        "cells": stats,
    }


def evaluate_regime(windows: pd.DataFrame, labels: pd.Series) -> dict:
    """Halves, year-adjusted gap and outcome for windows (date, hit) under one regime labelling."""
    kept, exclusions = attach_regime(windows, labels)
    cells = cell_table(kept) if len(kept) else pd.DataFrame({"date": [], "regime": [], "hits": [], "n": []}).astype(
        {"date": object, "regime": object}
    )
    halves = {name: evaluate_half(part, labels) for name, part in split_halves(cells).items()}
    year_adjusted = year_adjusted_gap(cells)
    return {
        "exclusions": exclusions, "halves": halves, "year_adjusted": year_adjusted,
        "outcome": decide_outcome(halves["early"], halves["late"], year_adjusted, exclusions["index_match"]),
    }


# ---------------------------------------------------------------------------
# The outcome rule (spec: "The kill criterion and pass level are fixed in the spec before any result")
# ---------------------------------------------------------------------------
def _excludes_zero(ci: tuple) -> bool:
    low, high = ci
    return low is not None and (low > 0 or high < 0)


def _points(value: float) -> str:
    return f"{value * 100:+.1f} points"


def _interval_text(ci: tuple) -> str:
    return f"[{ci[0] * 100:+.1f}, {ci[1] * 100:+.1f}]"


def _not_evaluable(half: dict) -> str | None:
    """Why a half cannot be judged, or None when it is evaluable."""
    if half["gap"] is None or half["ci"][0] is None:
        return "no gap or interval could be computed (a third has no windows)"
    if half["months"] < MIN_MONTHS_PER_HALF:
        return f"windows in {half['months']} months, need {MIN_MONTHS_PER_HALF}"
    for name in ("calm", "volatile"):
        if half[f"{name}_months"] < MIN_MONTHS_PER_CELL:
            return f"the {name} third has windows in {half[f'{name}_months']} months, need {MIN_MONTHS_PER_CELL}"
    return None


def decide_outcome(early: dict, late: dict, year_adjusted: dict | None, index_match: float) -> dict:
    """PASS, KILL or INCONCLUSIVE with its reasons and notes, applying the spec's constants.

    A half is a dict with gap, ci, months, calm_months and volatile_months; gaps are fractions of
    coverage (0.05 is 5 points). `year_adjusted` is {gap, ci} or None.
    """
    halves = {"early": early, "late": late}
    reasons = [f"{name} half is not evaluable: {why}" for name, half in halves.items() if (why := _not_evaluable(half))]
    if not index_match >= MIN_INDEX_MATCH:  # also true for NaN
        reasons.append(f"only {index_match:.1%} of test dates have an index close, need {MIN_INDEX_MATCH:.0%}")
    if reasons:
        return {"outcome": "INCONCLUSIVE", "reasons": reasons,
                "notes": ["INCONCLUSIVE: the data cannot answer the question yet; it may be re-run as history grows."]}

    under = {name: half for name, half in halves.items() if abs(half["gap"]) < PASS_GAP}
    opposite = early["gap"] * late["gap"] < 0
    if under or opposite:
        reasons = [f"{name} half gap {_points(half['gap'])} is under the {PASS_GAP * 100:.0f}-point level" for name, half in under.items()]
        reasons += ["the two halves' gaps have opposite signs"] if opposite else []
        notes = [
            f"{name} half: its interval {_interval_text(half['ci'])} reaches {PASS_GAP * 100:.0f} points, so the level is "
            "not met but this is not evidence that no regime effect exists"
            for name, half in under.items() if max(abs(half["ci"][0]), abs(half["ci"][1])) >= PASS_GAP
        ]
        return {"outcome": "KILL", "reasons": reasons, "notes": notes}

    failing = [f"{name} interval {_interval_text(half['ci'])} includes zero" for name, half in halves.items()
               if not _excludes_zero(half["ci"])]
    if year_adjusted is None:
        failing.append("year-adjusted gap unavailable: no year has both thirds on enough dates")
    elif year_adjusted["gap"] * early["gap"] < 0:
        failing.append(f"year-adjusted gap {_points(year_adjusted['gap'])} has the opposite sign to the halves")
    elif not _excludes_zero(year_adjusted["ci"]):
        failing.append(
            f"year-adjusted interval {_interval_text(year_adjusted['ci'])} includes zero: not separable from the by-year variation"
        )
    if failing:
        return {"outcome": "INCONCLUSIVE", "reasons": failing,
                "notes": ["Both gaps meet the level; failing an interval is not evidence that no regime effect exists."]}
    return {"outcome": "PASS", "reasons": [], "notes": [
        "PASS is evidence that a later change may design a regime-aware reading. Nothing is served: any "
        "user-facing use needs its own change (P7) and Rule 4 sign-off, because a by-regime coverage figure "
        "is a second reliability figure."
    ]}


# ---------------------------------------------------------------------------
# The band under test, measured out of time (design Decision 6)
# ---------------------------------------------------------------------------
def out_of_time_windows(
    frame: pd.DataFrame, coverage: float = RANGE_COVERAGE, min_train_rows: int = MIN_TRAIN_ROWS
) -> tuple[pd.DataFrame, list[dict]]:
    """Every walk-forward test window's date and hit, and each fold's year, window count and coverage.

    The folds are `train_har_rv.run_validation`'s: expanding by calendar year, HAR and `range_k` refit
    on windows whose OUTCOME date precedes the test year (the 5-session purge). Coverage is that of the
    served band, range_k x sqrt(5) x sigma_daily_pct(t) (a test asserts it equals the training script's).
    """
    pieces, folds = [], []
    for year in sorted(int(y) for y in frame["date"].str[:4].unique()):
        fit, test = split_fold(frame, year)
        if len(fit) < min_train_rows or test.empty:
            continue
        intercept, coef, range_k = fit_fold(fit, coverage)
        sigma = sigma_pct(test[list(FEATURE_NAMES)].to_numpy(), intercept, coef)
        hit = test["abs_r5_pct"].to_numpy() <= scaled_band(sigma, range_k)
        folds.append({"test_year": year, "n": int(len(test)), "coverage": float(hit.mean()), "k": range_k})
        pieces.append(pd.DataFrame({"date": test["date"].to_numpy(), "hit": hit}))
    windows = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame({"date": [], "hit": []})
    return windows.astype({"date": object, "hit": bool}), folds


def _pct(value: float | None) -> str:
    return "n/a" if value is None or np.isnan(value) else f"{value * 100:.1f}%"


def format_by_year(folds: list[dict]) -> str:
    """This run's out-of-time coverage by test year, beside the reviewer-reported range as a labelled reference."""
    low, high = REVIEWER_REPORTED_BY_YEAR
    lines = ["Out-of-time coverage by test year (recomputed in this run; nominal 68%):"]
    lines += [f"  {f['test_year']}  windows {f['n']:>9,}  coverage {_pct(f['coverage'])}" for f in folds]
    lines.append(
        f"  reference: by-year range {_pct(low)} to {_pct(high)} is reviewer-reported and not re-verified "
        "when this change was written; it is not a result of this run"
    )
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
