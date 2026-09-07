import logging
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from app.db.connection import get_connection
from app.services.ohlcv_quality_gate import level_shift_dates

logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "tenkan_sen", "kijun_sen", "senkou_span_a", "senkou_span_b",
    "chikou_signal", "rsi", "macd_line", "macd_signal", "macd_histogram",
    "bb_upper", "bb_middle", "bb_lower", "atr", "obv", "target", "near_gap",
]

UPSERT_FEATURES = """
INSERT INTO features (
    ticker, date, tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b,
    chikou_signal, rsi, macd_line, macd_signal, macd_histogram, bb_upper,
    bb_middle, bb_lower, atr, obv, target, near_gap, computed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(ticker, date) DO UPDATE SET
    tenkan_sen = excluded.tenkan_sen,
    kijun_sen = excluded.kijun_sen,
    senkou_span_a = excluded.senkou_span_a,
    senkou_span_b = excluded.senkou_span_b,
    chikou_signal = excluded.chikou_signal,
    rsi = excluded.rsi,
    macd_line = excluded.macd_line,
    macd_signal = excluded.macd_signal,
    macd_histogram = excluded.macd_histogram,
    bb_upper = excluded.bb_upper,
    bb_middle = excluded.bb_middle,
    bb_lower = excluded.bb_lower,
    atr = excluded.atr,
    obv = excluded.obv,
    target = excluded.target,
    near_gap = excluded.near_gap,
    computed_at = excluded.computed_at
"""


def _bindable(value):
    """A feature value sqlite3 can bind, with every flavour of missing as None.

    `_wilder_smooth` returns a nullable `Float64` series for a too-short
    input, so its missing values are `pd.NA`, which sqlite3 refuses to bind
    at all (`type 'NAType' is not supported`) — the whole ticker's upsert
    then raises and `features` is left empty for it. That is the silent
    failure `docs/KNOWN_ISSUES.md` records for short series, one layer
    further down than the guard that was added there.
    """
    return None if value is None or pd.isna(value) else value


def upsert_features(features: pd.DataFrame) -> None:
    """Upsert a `ticker`-labeled features DataFrame (as produced by
    `compute_all_features`/`compute_features_for_ticker` with a `ticker`
    column attached) into the `features` table, matching the
    `ON CONFLICT(ticker, date) DO UPDATE` pattern used for `ohlcv`/`tickers`
    in `ticker_ingestion.py`. Sets `computed_at` to the current time on
    every row, per design Decision 8.
    """
    computed_at = datetime.now().isoformat()
    rows = [
        (
            row.ticker, row.date,
            *(_bindable(getattr(row, col)) for col in FEATURE_COLUMNS),
            computed_at,
        )
        for row in features.itertuples()
    ]

    conn = get_connection()
    try:
        conn.executemany(UPSERT_FEATURES, rows)
        conn.commit()
    finally:
        conn.close()


def recompute_features_for_ticker(ticker: str) -> int:
    """Entry point to (re)compute and upsert `features` for a single ticker.

    Per design Decision 5, this always recomputes the ticker's entire
    `features` series from its earliest stored `ohlcv` row and upserts the
    full result — never an incremental/append-only update — since OBV's
    correctness depends on being computed over the complete ordered history
    every time. Returns the number of rows upserted.
    """
    conn = get_connection()
    try:
        ohlcv = pd.read_sql_query(
            "SELECT * FROM ohlcv WHERE ticker = ? ORDER BY date ASC",
            conn,
            params=(ticker,),
        )
        # Read through this module's own connection, so a caller that has
        # redirected `get_connection` sees its own flags rather than the real
        # database's. Only *level-shift* flags: an invalid close is absent
        # data rather than a change of price scale, so it gets neither the
        # blackout nor a segment boundary (see `level_shift_dates`).
        flagged = level_shift_dates(ticker, conn)
    finally:
        conn.close()

    # A close of zero is not a price, so those rows cannot take part in any
    # indicator — and they arrive in long runs on suspended or delisted
    # symbols (37 symbols, 1,122 rows in the first full ingest; `AUM` has 120
    # consecutive). Dropping them leaves `ohlcv` a faithful record of what
    # the source returned while turning the run into the calendar gap it
    # really is, which `compute_near_gap` already excludes on its own terms.
    priced = ohlcv[pd.to_numeric(ohlcv["close"], errors="coerce") > 0]
    if len(priced) < len(ohlcv):
        logger.info(
            "Dropping %d non-priced session(s) for %s before computing features",
            len(ohlcv) - len(priced), ticker,
        )
    ohlcv = priced.reset_index(drop=True)

    if ohlcv.empty:
        return 0

    features = compute_features_for_ticker(ohlcv, flagged)
    features.insert(0, "ticker", ticker)
    upsert_features(features)
    return len(features)


def _wilder_smooth(values: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing: seed with a simple mean of the first `period`
    values, then recursively smooth (avg = (avg*(period-1) + new) / period).
    Index 0..period-2 are NaN (insufficient history); index period-1 is the
    seed. `values` must already be aligned so index 0 is the first usable
    input (e.g. the first close-to-close delta).

    If `values` has fewer than `period` rows, there isn't enough history to
    seed even the first value — returns an all-NaN series of the same
    length/index rather than raising. Deliberate: a too-short series should
    surface as missing indicator values (the row is already near_gap=1
    regardless, per M2 Decision 2's longest-lookback rule), not as a crash
    that silently empties the whole features table for that ticker.
    """
    if len(values) < period:
        return pd.Series(pd.NA, index=values.index, dtype="Float64")

    smoothed = values.copy()
    smoothed.iloc[: period - 1] = pd.NA
    smoothed.iloc[period - 1] = values.iloc[:period].mean()
    for i in range(period, len(values)):
        smoothed.iloc[i] = (smoothed.iloc[i - 1] * (period - 1) + values.iloc[i]) / period
    return smoothed


TENKAN_PERIOD = 9
KIJUN_PERIOD = 26
SENKOU_B_PERIOD = 52
CHIKOU_PERIOD = 26
RSI_PERIOD = 14
MACD_FAST_PERIOD = 12
MACD_SLOW_PERIOD = 26
MACD_SIGNAL_PERIOD = 9
BOLLINGER_PERIOD = 20
BOLLINGER_NUM_STD = 2
ATR_PERIOD = 14
TARGET_HORIZON = 5
GAP_THRESHOLD_DAYS = 5


def detect_gaps(df: pd.DataFrame) -> list[int]:
    """Session-to-session gaps for a single ticker's OHLCV rows, sorted by
    date ascending, per M1's gap-detection rule (`ticker_ingestion.py`):
    a gap is any pair of consecutive stored sessions more than
    `GAP_THRESHOLD_DAYS` calendar days apart. Advisory only — mirrors M1's
    posture of logging gaps without filtering or repairing them.

    Returns the row positions (0-indexed within this ticker's stored
    sequence) of the *later* session in each gap-straddling pair, for task
    4.2's per-row lookback-window overlap check.
    """
    dates = [date.fromisoformat(d) for d in df["date"]]
    return [
        i
        for i, (prev, curr) in enumerate(zip(dates, dates[1:]), start=1)
        if curr - prev > timedelta(days=GAP_THRESHOLD_DAYS)
    ]


LONGEST_LOOKBACK_END_OFFSET = KIJUN_PERIOD
LONGEST_LOOKBACK_WINDOW = SENKOU_B_PERIOD


def compute_near_gap(df: pd.DataFrame) -> pd.Series:
    """`near_gap` flag for a single ticker's OHLCV rows, sorted by date
    ascending, per design Decision 2 / task 4.2.

    The longest indicator lookback window is Senkou Span B: the value
    stored against row D is computed from a `SENKOU_B_PERIOD`-row window
    ending `LONGEST_LOOKBACK_END_OFFSET` (= KIJUN_PERIOD) rows before D (see
    `compute_ichimoku`'s forward shift). So row D's full input window spans
    row positions `[D - KIJUN_PERIOD - SENKOU_B_PERIOD + 1, D - KIJUN_PERIOD]`
    (inclusive, 0-indexed by row position within this ticker's stored
    sequence — not calendar days).

    `near_gap(D) = 1` when that window either extends before the ticker's
    first stored row (position 0), or contains a `detect_gaps` position
    (the later session of a gap-straddling pair falls inside the window).
    """
    n = len(df)
    gap_positions = detect_gaps(df)

    near_gap = []
    for i in range(n):
        window_start = i - LONGEST_LOOKBACK_END_OFFSET - LONGEST_LOOKBACK_WINDOW + 1
        window_end = i - LONGEST_LOOKBACK_END_OFFSET

        if window_start < 0:
            near_gap.append(1)
            continue

        flagged = any(window_start <= pos <= window_end for pos in gap_positions)
        near_gap.append(1 if flagged else 0)

    return pd.Series(near_gap, index=df.index, name="near_gap")


def compute_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    """Ichimoku components for a single ticker's OHLCV rows, sorted by date ascending.

    Senkou Span A/B use the standard forward-shifted (as-charted) convention:
    the value stored against row D is computed from data as of D-26, so it
    remains safe to use only data on or before D. Chikou Span is replaced by
    `chikou_signal`, a leakage-safe comparison of close(D) to close(D-26), per
    design Decision 6 — the literal backward-shifted Chikou would require
    close(D+26), which is not available at prediction time.
    """
    high, low, close = df["high"], df["low"], df["close"]

    tenkan_sen = (
        high.rolling(TENKAN_PERIOD).max() + low.rolling(TENKAN_PERIOD).min()
    ) / 2
    kijun_sen = (
        high.rolling(KIJUN_PERIOD).max() + low.rolling(KIJUN_PERIOD).min()
    ) / 2
    senkou_span_a_asof = (tenkan_sen + kijun_sen) / 2
    senkou_span_b_asof = (
        high.rolling(SENKOU_B_PERIOD).max() + low.rolling(SENKOU_B_PERIOD).min()
    ) / 2
    chikou_signal = close - close.shift(CHIKOU_PERIOD)

    return pd.DataFrame(
        {
            "tenkan_sen": tenkan_sen,
            "kijun_sen": kijun_sen,
            "senkou_span_a": senkou_span_a_asof.shift(KIJUN_PERIOD),
            "senkou_span_b": senkou_span_b_asof.shift(KIJUN_PERIOD),
            "chikou_signal": chikou_signal,
        },
        index=df.index,
    )


def compute_rsi(df: pd.DataFrame) -> pd.Series:
    """RSI (Wilder's smoothing), period 14, for a single ticker's OHLCV rows
    sorted by date ascending. Only uses each row's own and prior closes.

    Wilder's method seeds the first average gain/loss as a simple mean of the
    first 14 deltas, then recursively smooths later values
    (avg = (avg*13 + new)/14) — this differs from an EWM seeded from the
    series start, which biases early values, so the seed is computed
    explicitly rather than via `Series.ewm(...)`.
    """
    delta = df["close"].diff()
    gain = delta.clip(lower=0).iloc[1:].reset_index(drop=True)
    loss = -delta.clip(upper=0).iloc[1:].reset_index(drop=True)

    avg_gain = _wilder_smooth(gain, RSI_PERIOD)
    avg_loss = _wilder_smooth(loss, RSI_PERIOD)
    avg_gain.index = df.index[1:]
    avg_loss.index = df.index[1:]
    avg_gain = avg_gain.reindex(df.index)
    avg_loss = avg_loss.reindex(df.index)

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(~((avg_gain == 0) & (avg_loss == 0)), other=pd.NA)
    return rsi.rename("rsi")


def compute_macd(df: pd.DataFrame) -> pd.DataFrame:
    """MACD (12/26/9), for a single ticker's OHLCV rows sorted by date
    ascending. Only uses each row's own and prior closes.

    Standard EMA definition: each EMA is seeded from and recursively computed
    over the full series from its start (`ewm(adjust=False)`), unlike RSI's
    Wilder seeding — this is the textbook MACD convention.
    """
    close = df["close"].reset_index(drop=True)
    ema_fast = close.ewm(span=MACD_FAST_PERIOD, adjust=False).mean()
    ema_slow = close.ewm(span=MACD_SLOW_PERIOD, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=MACD_SIGNAL_PERIOD, adjust=False).mean()
    macd_histogram = macd_line - macd_signal

    macd_line.iloc[: MACD_SLOW_PERIOD - 1] = pd.NA
    macd_signal.iloc[: MACD_SLOW_PERIOD + MACD_SIGNAL_PERIOD - 2] = pd.NA
    macd_histogram.iloc[: MACD_SLOW_PERIOD + MACD_SIGNAL_PERIOD - 2] = pd.NA

    macd_line.index = df.index
    macd_signal.index = df.index
    macd_histogram.index = df.index

    return pd.DataFrame(
        {
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "macd_histogram": macd_histogram,
        },
        index=df.index,
    )


def compute_bollinger_bands(df: pd.DataFrame) -> pd.DataFrame:
    """Bollinger Bands (20-period SMA, 2 population standard deviations),
    for a single ticker's OHLCV rows sorted by date ascending. Only uses each
    row's own and prior closes."""
    close = df["close"]
    bb_middle = close.rolling(BOLLINGER_PERIOD).mean()
    bb_std = close.rolling(BOLLINGER_PERIOD).std(ddof=0)
    bb_upper = bb_middle + BOLLINGER_NUM_STD * bb_std
    bb_lower = bb_middle - BOLLINGER_NUM_STD * bb_std

    return pd.DataFrame(
        {
            "bb_upper": bb_upper,
            "bb_middle": bb_middle,
            "bb_lower": bb_lower,
        },
        index=df.index,
    )


def compute_atr(df: pd.DataFrame) -> pd.Series:
    """ATR (Wilder's smoothing), period 14, for a single ticker's OHLCV rows
    sorted by date ascending. Only uses each row's own and prior high/low/close.

    True Range for row i is max(high-low, |high-prev_close|, |low-prev_close|);
    ATR is Wilder's smoothed average of True Range, same seeding convention as
    RSI (simple-mean seed, then recursive smoothing).
    """
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    tr = true_range.iloc[1:].reset_index(drop=True)
    atr = _wilder_smooth(tr, ATR_PERIOD)
    atr.index = df.index[1:]
    atr = atr.reindex(df.index)

    return atr.rename("atr")


def compute_obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume for a single ticker's OHLCV rows sorted by date
    ascending. Only uses each row's own and prior close/volume.

    OBV(0) = volume(0); OBV(i) = OBV(i-1) + volume(i) if close rises,
    OBV(i-1) - volume(i) if close falls, OBV(i-1) unchanged if close is flat.
    A cumulative running total from the ticker's earliest stored row — per
    design Decision 5, this is why feature computation always recomputes a
    ticker's entire series rather than appending incrementally.
    """
    close_direction = df["close"].diff().apply(
        lambda delta: 1 if delta > 0 else (-1 if delta < 0 else 0)
    )
    signed_volume = df["volume"] * close_direction
    signed_volume.iloc[0] = df["volume"].iloc[0]

    return signed_volume.cumsum().rename("obv")


def compute_target(
    df: pd.DataFrame, hard_flagged_dates: set[str] | None = None
) -> pd.Series:
    """Prediction target for a single ticker's OHLCV rows sorted by date
    ascending, per Rule 1: `target(t) = ln(close[t+5] / close[t])`, where
    `t+5` is 5 TRADING SESSIONS ahead (row offset within this ticker's stored
    sequence), not a 5-calendar-day lookahead.

    `hard_flagged_dates` names sessions whose own return the
    `ohlcv-quality-gate` has hard-flagged as impossible under any Vietnamese
    exchange's price limit. Rule 1's definition is unchanged; what changes is
    that the target is left null where the data it would be computed from is
    known corrupt — the same posture `near_gap` already takes toward
    unreliable rows.

    Which targets are affected is exact rather than approximate. A flagged
    session `d` means the step from `close[d-1]` to `close[d]` is spurious,
    so `target(t)` is contaminated precisely when that step falls inside its
    lookahead window: `t < d <= t + TARGET_HORIZON`, i.e. the
    TARGET_HORIZON rows before `d`. `target(d)` itself spans `close[d]` to
    `close[d + 5]`, both on the far side of the step, and stays valid.
    """
    close = df["close"]
    future_close = close.shift(-TARGET_HORIZON)
    target = pd.Series(np.log(future_close / close), index=df.index).rename("target")

    if not hard_flagged_dates:
        return target

    dates = df["date"].astype(str).tolist()
    contaminated = [
        position
        for index, session in enumerate(dates)
        if session in hard_flagged_dates
        for position in range(max(index - TARGET_HORIZON, 0), index)
    ]
    if contaminated:
        target.iloc[sorted(set(contaminated))] = np.nan
    return target


# The longest indicator lookback, in sessions. Senkou Span B's
# SENKOU_B_PERIOD-row window is read LONGEST_LOOKBACK_END_OFFSET rows further
# back (`compute_ichimoku`'s forward shift), so the furthest-reaching window
# any indicator has spans 78 row positions — the same span `compute_near_gap`
# uses for warm-up and calendar gaps.
HARD_FLAG_BLACKOUT_SESSIONS = LONGEST_LOOKBACK_END_OFFSET + LONGEST_LOOKBACK_WINDOW

# Every column a price level reaches. `target` is excluded because
# `compute_target` already nulls exactly the rows a flag contaminates (the
# TARGET_HORIZON rows *before* it), and `near_gap` because it describes
# calendar gaps rather than price discontinuities and is an input to the
# blackout's own justification, not a subject of it.
INDICATOR_COLUMNS = [
    column for column in FEATURE_COLUMNS if column not in ("target", "near_gap")
]


def blackout_indicators_after_hard_flags(
    features: pd.DataFrame, hard_flagged_dates: set[str] | None
) -> pd.DataFrame:
    """Null every indicator column for HARD_FLAG_BLACKOUT_SESSIONS sessions
    starting at each hard-flagged session (design Decision 9).

    A hard-flagged session is a persistent level shift — the one measured in
    this data, `VHM` 2018-08-14, is a missed 2:1 split, where the close halves
    and *stays* halved. So unlike the flagged return, which
    `neutralise_hard_flagged_returns` removes in one place, the level
    discontinuity contaminates every rolling window reaching across it:
    `bb_middle` (20 sessions), `kijun_sen` and `macd` (26), `senkou_span_b`
    (78). Each such window blends two different price scales, so its value is
    not a smoothed price at all.

    The blackout starts at the flagged session itself, not after it: the
    flagged return is the step from `close[d-1]` to `close[d]`, and a window
    ending at `d` already contains both sides of it.

    Blacking out the longest lookback uniformly, rather than each indicator's
    own window length, mirrors what `compute_near_gap` does for warm-up and
    is the option the design chose (Decision 9 option (a)); the alternative,
    detecting and repairing the split, is deferred with task 9.1's measured
    flag rate as the trigger to reopen it.

    `obv` is blacked out with the rest for consistency, but note that its
    contamination is *not* bounded by the window: it is a cumulative sum, so a
    spurious direction at the step shifts every later value permanently. The
    blackout hides the affected span; it does not repair `obv`.
    """
    if not hard_flagged_dates:
        return features

    sessions = features["date"].astype(str).tolist()
    blacked_out = sorted(
        {
            position
            for index, session in enumerate(sessions)
            if session in hard_flagged_dates
            for position in range(
                index, min(index + HARD_FLAG_BLACKOUT_SESSIONS, len(sessions))
            )
        }
    )
    if not blacked_out:
        return features

    mask = pd.Series(False, index=features.index)
    mask.iloc[blacked_out] = True
    # A copy, so the caller's frame is not mutated as a side effect of a
    # function that also returns one — the two behaviours together invite a
    # caller to assume the original is still un-blacked-out.
    blacked = features.copy()
    for column in INDICATOR_COLUMNS:
        # `Series.mask` rather than positional assignment so an integer column
        # (`obv`) widens to float instead of rejecting the null.
        blacked[column] = blacked[column].mask(mask)
    return blacked


def compute_features_for_ticker(
    ohlcv: pd.DataFrame, hard_flagged_dates: set[str] | None = None
) -> pd.DataFrame:
    """All six indicator families for a single ticker's OHLCV rows.

    `ohlcv` must already be filtered to one ticker and sorted by date
    ascending — this function does not group or sort, so calling it directly
    on a multi-ticker frame would blend rows across tickers into shared
    rolling/EWM/cumulative windows (Ichimoku, RSI, MACD, Bollinger, ATR, and
    OBV are all sequence-order-dependent). Use `compute_all_features` when
    starting from a raw `ohlcv` table spanning multiple tickers.

    `hard_flagged_dates` has two distinct effects, and they point in opposite
    directions along the series. `compute_target` nulls the targets *before*
    each flag, whose lookahead spans the spurious step;
    `blackout_indicators_after_hard_flags` nulls the indicators *at and after*
    it, whose lookback spans the same step. See each for why.
    """
    ohlcv = ohlcv.reset_index(drop=True)
    indicators = _compute_indicators_in_segments(ohlcv, hard_flagged_dates)
    features = pd.concat(
        [
            ohlcv[["date"]],
            indicators,
            # Computed over the whole series, never per segment. `target`
            # already nulls exactly the rows whose lookahead spans a flag,
            # and `near_gap` describes calendar gaps, which segmentation
            # would silently redefine.
            compute_target(ohlcv, hard_flagged_dates),
            compute_near_gap(ohlcv),
        ],
        axis=1,
    )
    return blackout_indicators_after_hard_flags(features, hard_flagged_dates)


def _indicator_block(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Every indicator family for one contiguous run of sessions."""
    return pd.concat(
        [
            compute_ichimoku(ohlcv),
            compute_rsi(ohlcv),
            compute_macd(ohlcv),
            compute_bollinger_bands(ohlcv),
            compute_atr(ohlcv),
            compute_obv(ohlcv),
        ],
        axis=1,
    )


def _compute_indicators_in_segments(
    ohlcv: pd.DataFrame, hard_flagged_dates: set[str] | None
) -> pd.DataFrame:
    """Indicators computed independently on each side of a hard flag.

    The 78-session blackout is sufficient only for the window-bounded
    indicators — `bb_middle` (20), `kijun_sen` (26), `senkou_span_b` (78).
    The rest are recursive and unbounded: `rsi` and `atr` use Wilder
    smoothing, `macd_*` an EWM from the series start, `obv` a cumulative
    sum. A hard flag is a persistent level shift, so those carry it past any
    fixed span. Measured against a split-repaired reference on `VHM`, at the
    first row past the blackout: `macd_signal` 54.5% error, `macd_line`
    19.5%, `obv` 20.4% — and `obv` still 12% off nine months later.

    Treating the flagged session as the start of a new series is what the
    data actually is: two price scales, spliced. Each segment pays its own
    warm-up nulls once, which the blackout already covers, and beyond that
    every indicator is computed from one scale only — which is what makes
    the `ohlcv-quality-gate` scenario "sessions beyond the lookback are
    unaffected" true rather than aspirational.

    Chosen over detect-and-repair (design Decision 11 option b), which would
    keep the history continuous but means writing corrected prices into
    `ohlcv`.
    """
    if not hard_flagged_dates:
        return _indicator_block(ohlcv)

    sessions = ohlcv["date"].astype(str)
    # Each flagged session opens a segment; `cumsum` over that indicator
    # labels every row with the segment it belongs to.
    segment_ids = sessions.isin(hard_flagged_dates).cumsum()
    if segment_ids.nunique() == 1:
        return _indicator_block(ohlcv)

    blocks = []
    for _, group in ohlcv.groupby(segment_ids, sort=True):
        block = _indicator_block(group.reset_index(drop=True))
        block.index = group.index
        # Cast before concatenating: a segment too short to seed an indicator
        # yields an all-null column, and pandas otherwise infers the combined
        # dtype from whichever blocks are not all-null (a deprecation warning
        # today, a behaviour change later). Every indicator is real-valued,
        # and `obv` widening from int is the same widening the blackout does.
        blocks.append(block.astype("float64"))
    return pd.concat(blocks).sort_index()


def compute_all_features(
    ohlcv: pd.DataFrame, hard_flagged_by_ticker: dict[str, set[str]] | None = None
) -> pd.DataFrame:
    """All six indicator families for every ticker in a multi-ticker `ohlcv`
    frame, computed independently per ticker (no cross-ticker leakage).

    Groups by `ticker`, sorts each group by `date` ascending, and computes
    indicators within that group only — rolling windows, EWMs, and OBV's
    cumulative sum never span a ticker boundary.

    `hard_flagged_by_ticker` threads each ticker's flagged sessions through
    to `compute_features_for_ticker`. Without it this function silently
    produces features with no blackout and no target nulling — the entire
    design Decision 9 mechanism bypassed — which is why it is a parameter
    rather than something a caller can simply forget: prefer
    `recompute_features_for_ticker`, which reads the flags itself.
    """
    flagged_by_ticker = hard_flagged_by_ticker or {}
    results = []
    for ticker, group in ohlcv.groupby("ticker", sort=False):
        sorted_group = group.sort_values("date").reset_index(drop=True)
        features = compute_features_for_ticker(
            sorted_group, flagged_by_ticker.get(ticker)
        )
        features.insert(0, "ticker", ticker)
        results.append(features)

    if not results:
        return pd.DataFrame(
            columns=[
                "ticker", "date", "tenkan_sen", "kijun_sen", "senkou_span_a",
                "senkou_span_b", "chikou_signal", "rsi", "macd_line",
                "macd_signal", "macd_histogram", "bb_upper", "bb_middle",
                "bb_lower", "atr", "obv", "target", "near_gap",
            ]
        )
    return pd.concat(results, ignore_index=True)
