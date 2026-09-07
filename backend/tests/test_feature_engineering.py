import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest

import numpy as np

import app.ml.feature_engineering as feature_engineering
from app.db.schema import CREATE_FEATURES_TABLE, CREATE_OHLCV_QUALITY_FLAGS_TABLE, CREATE_OHLCV_TABLE
from app.ml.feature_engineering import (
    CHIKOU_PERIOD,
    HARD_FLAG_BLACKOUT_SESSIONS,
    INDICATOR_COLUMNS,
    LONGEST_LOOKBACK_END_OFFSET,
    LONGEST_LOOKBACK_WINDOW,
    TARGET_HORIZON,
    _wilder_smooth,
    compute_atr,
    compute_bollinger_bands,
    compute_features_for_ticker,
    compute_ichimoku,
    compute_macd,
    compute_near_gap,
    compute_obv,
    compute_rsi,
    compute_target,
    recompute_features_for_ticker,
)


def _dates(n, start=date(2024, 1, 1)):
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


# Classic Wilder RSI/ATR textbook fixture (Wilder's "New Concepts", 14-period
# seed): 15 closes -> 14 deltas, exactly enough for one seeded RSI/ATR value
# with no further smoothing steps, so the reference value is a plain average.
WILDER_CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
    45.89, 46.03, 45.61, 46.28, 46.28,
]


def _wilder_df():
    return pd.DataFrame(
        {
            "date": _dates(len(WILDER_CLOSES)),
            "high": [c + 0.5 for c in WILDER_CLOSES],
            "low": [c - 0.5 for c in WILDER_CLOSES],
            "close": WILDER_CLOSES,
            "volume": [1000 + 10 * i for i in range(len(WILDER_CLOSES))],
        }
    )


def test_rsi_matches_hand_computed_wilder_seed_value():
    df = _wilder_df()
    rsi = compute_rsi(df)

    assert rsi.iloc[:14].isna().all()
    assert rsi.iloc[14] == pytest.approx(70.464135, abs=1e-5)


def test_atr_matches_hand_computed_wilder_seed_value():
    df = _wilder_df()
    atr = compute_atr(df)

    assert atr.iloc[:14].isna().all()
    assert atr.iloc[14] == pytest.approx(1.030714, abs=1e-5)


def test_wilder_smooth_returns_nan_series_when_too_short():
    short_series = pd.Series([1.0, 2.0, 3.0])  # len=3, period=14
    result = _wilder_smooth(short_series, period=14)
    assert len(result) == len(short_series)
    assert result.isna().all()


def test_wilder_smooth_seed_at_exact_boundary_still_works():
    exact_series = pd.Series(range(14), dtype=float)  # len == period
    result = _wilder_smooth(exact_series, period=14)
    assert not pd.isna(result.iloc[13])  # seed value present, no crash


def test_obv_matches_hand_computed_signed_cumulative_volume():
    df = _wilder_df()
    obv = compute_obv(df)

    expected = [
        1000, -10, 1010, -20, 1020, 2070, 3130, 4200, 5280, 6370,
        5270, 6380, 5260, 6390, 6390,
    ]
    assert obv.tolist() == pytest.approx(expected)


def test_bollinger_bands_match_hand_computed_population_std():
    closes = list(range(1, 21))  # 1..20, period-20 window exactly full
    df = pd.DataFrame({"date": _dates(len(closes)), "close": closes})
    bb = compute_bollinger_bands(df)

    mean = sum(closes) / len(closes)
    variance = sum((c - mean) ** 2 for c in closes) / len(closes)
    std = variance**0.5

    assert bb["bb_middle"].iloc[:19].isna().all()
    assert bb["bb_middle"].iloc[19] == pytest.approx(mean)
    assert bb["bb_upper"].iloc[19] == pytest.approx(mean + 2 * std)
    assert bb["bb_lower"].iloc[19] == pytest.approx(mean - 2 * std)


def test_macd_matches_hand_computed_ema_chain():
    closes = list(range(10, 50))  # 40 rows: enough for line (26) and signal (34)
    df = pd.DataFrame({"date": _dates(len(closes)), "close": closes})
    macd = compute_macd(df)

    # Independent EMA re-derivation (adjust=False convention: ema[0] = x[0]).
    def ema(series, span):
        alpha = 2.0 / (span + 1)
        out = [series[0]]
        for x in series[1:]:
            out.append(alpha * x + (1 - alpha) * out[-1])
        return out

    ema_fast = ema(closes, 12)
    ema_slow = ema(closes, 26)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    macd_signal = ema(macd_line, 9)
    macd_hist = [m - s for m, s in zip(macd_line, macd_signal)]

    assert macd["macd_line"].iloc[:25].isna().all()
    assert macd["macd_signal"].iloc[:33].isna().all()

    for idx in (25, 33, 39):
        assert macd["macd_line"].iloc[idx] == pytest.approx(macd_line[idx])
    for idx in (33, 39):
        assert macd["macd_signal"].iloc[idx] == pytest.approx(macd_signal[idx])
        assert macd["macd_histogram"].iloc[idx] == pytest.approx(macd_hist[idx])


def test_ichimoku_matches_hand_computed_reference_values():
    n = 90
    highs = [100 + (i % 10) for i in range(n)]
    lows = [90 + (i % 7) for i in range(n)]
    closes = [95 + (i % 5) for i in range(n)]
    df = pd.DataFrame(
        {"date": _dates(n), "high": highs, "low": lows, "close": closes}
    )
    ichimoku = compute_ichimoku(df)

    # Tenkan-sen (period 9): first valid value at row 8.
    row = 8
    expected_tenkan = (max(highs[row - 8 : row + 1]) + min(lows[row - 8 : row + 1])) / 2
    assert ichimoku["tenkan_sen"].iloc[row] == pytest.approx(expected_tenkan)

    # Kijun-sen (period 26): first valid value at row 25.
    row = 25
    expected_kijun = (max(highs[row - 25 : row + 1]) + min(lows[row - 25 : row + 1])) / 2
    assert ichimoku["kijun_sen"].iloc[row] == pytest.approx(expected_kijun)

    # Senkou Span A at row D is (tenkan+kijun)/2 as of D-26, forward-shifted.
    d, lookback = 60, 26
    ref = d - lookback
    tenkan_ref = (
        max(highs[ref - 8 : ref + 1]) + min(lows[ref - 8 : ref + 1])
    ) / 2
    kijun_ref = (
        max(highs[ref - 25 : ref + 1]) + min(lows[ref - 25 : ref + 1])
    ) / 2
    expected_senkou_a = (tenkan_ref + kijun_ref) / 2
    assert ichimoku["senkou_span_a"].iloc[d] == pytest.approx(expected_senkou_a)

    # chikou_signal(D) = close(D) - close(D-26): leakage-safe comparison.
    d = 30
    expected_chikou = closes[d] - closes[d - 26]
    assert ichimoku["chikou_signal"].iloc[d] == pytest.approx(expected_chikou)


def test_ichimoku_outputs_at_row_d_are_unaffected_by_ohlcv_rows_after_d():
    # Guards the Chikou leakage bug class specifically (design Decision 6):
    # asserts no Ichimoku-derived column's value at row D changes when the
    # *inputs* dated after D change, i.e. construction is restricted to
    # ohlcv[date <= D], not merely that some particular output happens to
    # match a hand-computed value.
    n = 120
    d = 85  # far enough in for every Ichimoku component (incl. Senkou B's
    # KIJUN_PERIOD + SENKOU_B_PERIOD - 1 = 77-row warm-up) to be non-null

    def build(high_after, low_after, close_after):
        highs = [100 + (i % 10) for i in range(n)]
        lows = [90 + (i % 7) for i in range(n)]
        closes = [95 + (i % 5) for i in range(n)]
        for i in range(d + 1, n):
            highs[i] = high_after
            lows[i] = low_after
            closes[i] = close_after
        return pd.DataFrame(
            {"date": _dates(n), "high": highs, "low": lows, "close": closes}
        )

    baseline = compute_ichimoku(build(100, 90, 95))
    # Wildly different future OHLCV values (dated after D) — if any
    # Ichimoku column at row D reads them, its value at D would change.
    mutated = compute_ichimoku(build(100_000.0, 99_000.0, 99_500.0))

    for col in (
        "tenkan_sen", "kijun_sen", "senkou_span_a", "senkou_span_b",
        "chikou_signal",
    ):
        assert baseline[col].iloc[d] == pytest.approx(mutated[col].iloc[d]), (
            f"{col} at row {d} changed when only post-D ohlcv rows were "
            "mutated — it is reading future data"
        )

    # Explicit check on chikou_signal's construction per Decision 6: it must
    # be close(D) - close(D - 26), never close(D) - close(D + 26). Confirms
    # the guard above isn't accidentally vacuous for this column.
    closes = [95 + (i % 5) for i in range(n)]
    expected_chikou = closes[d] - closes[d - CHIKOU_PERIOD]
    assert baseline["chikou_signal"].iloc[d] == pytest.approx(expected_chikou)


def test_target_is_log_return_5_sessions_ahead_and_null_at_series_tail():
    n = 20
    closes = [100 + i for i in range(n)]  # simple increasing series
    df = pd.DataFrame({"date": _dates(n), "close": closes})
    target = compute_target(df)

    # Rows with 5 future sessions available: correct log-return value.
    for t in range(n - TARGET_HORIZON):
        expected = np.log(closes[t + TARGET_HORIZON] / closes[t])
        assert target.iloc[t] == pytest.approx(expected)

    # Last TARGET_HORIZON rows lack 5 future sessions: target is null.
    assert target.iloc[n - TARGET_HORIZON :].isna().all()


def _windowed_dates(n, gap_after_row=None, gap_days=10, start=date(2024, 1, 1)):
    """Build n sequential daily dates, optionally inserting a single
    calendar-day gap of `gap_days` immediately after row `gap_after_row`
    (0-indexed) — i.e. row positions stay contiguous, but the calendar
    distance between that row and the next one exceeds GAP_THRESHOLD_DAYS."""
    dates = []
    current = start
    for i in range(n):
        dates.append(current.isoformat())
        step = gap_days if i == gap_after_row else 1
        current = current + timedelta(days=step)
    return dates


def _flat_ohlcv(dates):
    n = len(dates)
    return pd.DataFrame(
        {
            "date": dates,
            "high": [100.0] * n,
            "low": [99.0] * n,
            "close": [99.5] * n,
            "volume": [1000] * n,
        }
    )


def test_near_gap_flags_rows_within_lookback_of_an_injected_gap():
    # Long enough series that rows both inside and outside the
    # gap-straddling row's lookback window exist on both sides.
    n = 250
    gap_after_row = 100
    dates = _windowed_dates(n, gap_after_row=gap_after_row)
    df = _flat_ohlcv(dates)

    near_gap = compute_near_gap(df)

    gap_row = gap_after_row + 1  # later session of the gap-straddling pair

    # Row d's lookback window is [d - offset - window + 1, d - offset], so it
    # includes gap_row exactly when
    # gap_row <= d - offset <= gap_row + window - 1, i.e.
    # d in [gap_row + offset, gap_row + offset + window - 1].
    first_flagged = gap_row + LONGEST_LOOKBACK_END_OFFSET
    last_flagged = first_flagged + LONGEST_LOOKBACK_WINDOW - 1
    for d in range(first_flagged, min(last_flagged + 1, n)):
        assert near_gap.iloc[d] == 1, f"row {d} should be flagged near_gap"

    # A row far enough past the gap that its lookback window no longer
    # overlaps it, and far enough from the series start too, is not flagged.
    clean_row = last_flagged + 5
    assert clean_row < n, "fixture too short to cover a clean row past the gap"
    assert near_gap.iloc[clean_row] == 0


def test_near_gap_is_zero_for_rows_with_clean_history():
    n = 150
    dates = _windowed_dates(n)  # no gap injected
    df = _flat_ohlcv(dates)

    near_gap = compute_near_gap(df)

    window = LONGEST_LOOKBACK_END_OFFSET + LONGEST_LOOKBACK_WINDOW
    # Rows whose full lookback window fits within stored history and
    # contains no gap are clean.
    for d in range(window, n):
        assert near_gap.iloc[d] == 0, f"row {d} should not be flagged near_gap"


def test_near_gap_flags_rows_near_the_start_of_a_short_series():
    # A short/tier-truncated series: every row's lookback window extends
    # before the ticker's first stored session, so all rows are flagged.
    n = 30
    dates = _windowed_dates(n)
    df = _flat_ohlcv(dates)

    near_gap = compute_near_gap(df)

    assert (near_gap == 1).all()

    # Sanity check against the spec's own boundary: even the last row's
    # window still reaches before row 0 given how short this series is.
    last = n - 1
    window_start = last - LONGEST_LOOKBACK_END_OFFSET - LONGEST_LOOKBACK_WINDOW + 1
    assert window_start < 0


def _seed_ohlcv_db(tmp_path, ticker, dates):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.executemany(
        "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (ticker, d, 100.0 + i, 100.5 + i, 99.5 + i, 100.0 + i, 1000 + i)
            for i, d in enumerate(dates)
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def test_recompute_features_upsert_is_idempotent_without_duplicating_rows(
    monkeypatch, tmp_path
):
    ticker = "VIB"
    dates = _dates(80)
    db_path = _seed_ohlcv_db(tmp_path, ticker, dates)

    monkeypatch.setattr(
        feature_engineering, "get_connection", lambda: sqlite3.connect(db_path)
    )

    first_count = recompute_features_for_ticker(ticker)
    conn = sqlite3.connect(db_path)
    first_rows = conn.execute(
        "SELECT ticker, date, rsi, computed_at FROM features ORDER BY date"
    ).fetchall()
    conn.close()

    assert first_count == len(dates)
    assert len(first_rows) == len(dates)

    second_count = recompute_features_for_ticker(ticker)
    conn = sqlite3.connect(db_path)
    second_rows = conn.execute(
        "SELECT ticker, date, rsi, computed_at FROM features ORDER BY date"
    ).fetchall()
    row_count = conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
    conn.close()

    assert second_count == len(dates)
    assert row_count == len(dates)  # re-run updates existing rows, no duplicates
    assert [(t, d, rsi) for t, d, rsi, _ in second_rows] == [
        (t, d, rsi) for t, d, rsi, _ in first_rows
    ]


def test_recompute_features_updates_obv_for_all_rows_after_ticker_reload(
    monkeypatch, tmp_path
):
    # OBV is a cumulative running total seeded at the ticker's earliest
    # stored row (per design Decision 5), so backfilling earlier history
    # must shift OBV for every pre-existing row, not just append new ones.
    ticker = "VIB"
    dates = _dates(80)
    db_path = _seed_ohlcv_db(tmp_path, ticker, dates)

    monkeypatch.setattr(
        feature_engineering, "get_connection", lambda: sqlite3.connect(db_path)
    )

    recompute_features_for_ticker(ticker)
    conn = sqlite3.connect(db_path)
    first_obv = conn.execute(
        "SELECT date, obv FROM features ORDER BY date"
    ).fetchall()
    conn.close()

    # Simulate a reload that backfills 10 earlier sessions ahead of the
    # ticker's previously-earliest stored row.
    earlier_dates = _dates(10, start=date(2024, 1, 1) - timedelta(days=10))
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (ticker, d, 50.0 + i, 50.5 + i, 49.5 + i, 50.0 + i, 500 + i)
            for i, d in enumerate(earlier_dates)
        ],
    )
    conn.commit()
    conn.close()

    second_count = recompute_features_for_ticker(ticker)
    conn = sqlite3.connect(db_path)
    second_obv = conn.execute(
        "SELECT date, obv FROM features ORDER BY date"
    ).fetchall()
    row_count = conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
    conn.close()

    assert second_count == len(dates) + len(earlier_dates)
    assert row_count == len(dates) + len(earlier_dates)

    second_obv_by_date = dict(second_obv)
    first_obv_by_date = dict(first_obv)

    # Every previously-existing row's OBV must be updated (not left as the
    # stale value from before the reload) to reflect the new cumulative
    # base built from the backfilled rows.
    changed = [
        d for d in first_obv_by_date if second_obv_by_date[d] != first_obv_by_date[d]
    ]
    assert changed == list(first_obv_by_date), (
        "reload must recompute OBV for ALL existing rows, not just append "
        "new ones"
    )


# --- hard-flagged return neutralisation (hose-universe-ingestion task 3.6) ---


def _step_ohlcv(rows: int, jump_at: int, factor: float = 0.5) -> pd.DataFrame:
    """A clean series with a single unadjusted-split-style step at `jump_at`,
    modelled on VHM 2018-08-14 (60.30 -> 30.23 across all OHLC fields)."""
    closes = []
    price = 100.0
    for index in range(rows):
        if index == jump_at:
            price *= factor
        closes.append(price)
        price *= 1.001
    return pd.DataFrame(
        {
            "date": [f"2018-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(rows)],
            "open": closes,
            "high": [c * 1.001 for c in closes],
            "low": [c * 0.999 for c in closes],
            "close": closes,
            "volume": [1000] * rows,
        }
    )


def test_target_is_nulled_only_for_the_rows_whose_lookahead_spans_the_flagged_step():
    """`target(t)` is contaminated exactly when the spurious step falls inside
    its lookahead: `t < d <= t + TARGET_HORIZON`. `target(d)` itself spans
    two closes on the far side of the step and stays valid."""
    jump_at = 20
    df = _step_ohlcv(40, jump_at)
    flagged = {df["date"].iloc[jump_at]}

    baseline = compute_target(df)
    neutralised = compute_target(df, flagged)

    expected_null = set(range(jump_at - TARGET_HORIZON, jump_at))
    actual_null = {
        i for i in range(len(df))
        if pd.isna(neutralised.iloc[i]) and not pd.isna(baseline.iloc[i])
    }
    assert actual_null == expected_null
    assert not pd.isna(neutralised.iloc[jump_at])
    assert neutralised.iloc[jump_at] == pytest.approx(baseline.iloc[jump_at])


def test_the_nulled_targets_are_exactly_the_ones_carrying_the_spurious_move():
    """Sanity check on the claim above: every target nulled really did span
    the step, and every retained target really did not."""
    jump_at = 20
    df = _step_ohlcv(40, jump_at)
    baseline = compute_target(df)
    step = abs(float(baseline.iloc[jump_at - 1]))
    # A target spanning a 50% step is an order of magnitude larger than the
    # 0.1%/session drift the rest of the series carries.
    assert step > 0.5
    assert abs(float(baseline.iloc[jump_at])) < 0.01


def test_target_is_untouched_when_nothing_is_flagged():
    df = _step_ohlcv(40, 20)
    pd.testing.assert_series_equal(compute_target(df), compute_target(df, set()))
    pd.testing.assert_series_equal(compute_target(df), compute_target(df, None))


def test_a_flag_in_the_first_rows_does_not_index_before_the_start():
    df = _step_ohlcv(20, 2)
    target = compute_target(df, {df["date"].iloc[2]})
    assert pd.isna(target.iloc[0])
    assert pd.isna(target.iloc[1])
    assert not pd.isna(target.iloc[2])


def test_compute_features_for_ticker_passes_flags_through_to_target():
    jump_at = 20
    df = _step_ohlcv(40, jump_at)
    features = compute_features_for_ticker(df, {df["date"].iloc[jump_at]})
    assert pd.isna(features["target"].iloc[jump_at - 1])
    assert not pd.isna(features["target"].iloc[jump_at])


# --- indicator blackout after a hard flag (task 4.7, design Decision 9) ---

# Long enough that the blackout ends well before the series does, so "beyond
# the lookback" is actually observable.
_BLACKOUT_ROWS = 200
_BLACKOUT_JUMP_AT = 100


def test_every_indicator_column_is_nulled_through_the_longest_lookback():
    """A hard flag is a persistent level shift, so every window reaching
    across it blends two price scales. The blackout starts at the flagged
    session itself — a window ending there already spans both sides of the
    step."""
    df = _step_ohlcv(_BLACKOUT_ROWS, _BLACKOUT_JUMP_AT)
    features = compute_features_for_ticker(df, {df["date"].iloc[_BLACKOUT_JUMP_AT]})

    blacked_out = range(
        _BLACKOUT_JUMP_AT, _BLACKOUT_JUMP_AT + HARD_FLAG_BLACKOUT_SESSIONS
    )
    for column in INDICATOR_COLUMNS:
        assert features[column].iloc[blacked_out.start : blacked_out.stop].isna().all(), (
            f"{column} must be null for {HARD_FLAG_BLACKOUT_SESSIONS} sessions "
            "from the flagged one"
        )


def test_the_blackout_does_not_reach_backwards_past_the_flag():
    """Rows before the flag keep the values they would have had — nothing
    about the blackout reaches backwards."""
    df = _step_ohlcv(_BLACKOUT_ROWS, _BLACKOUT_JUMP_AT)
    plain = compute_features_for_ticker(df)
    flagged = compute_features_for_ticker(df, {df["date"].iloc[_BLACKOUT_JUMP_AT]})

    for column in INDICATOR_COLUMNS:
        pd.testing.assert_series_equal(
            plain[column].iloc[:_BLACKOUT_JUMP_AT],
            flagged[column].iloc[:_BLACKOUT_JUMP_AT],
            check_dtype=False,
        )


def test_past_the_blackout_indicators_match_the_post_flag_segment_alone():
    """The correctness claim the spec actually makes — "sessions beyond the
    lookback are unaffected" — measured against a *clean* reference rather
    than against the same contaminated series.

    An earlier version of this test compared the flagged run against
    `compute_features_for_ticker(df)` with no flag, i.e. one equally
    contaminated by the step. Both sides carried the same error, so it passed
    while `macd_signal` was 54% wrong on the first clear row (design
    Decision 11). The honest reference is the post-flag rows computed on
    their own: that is the price scale those sessions actually belong to.
    """
    df = _step_ohlcv(_BLACKOUT_ROWS, _BLACKOUT_JUMP_AT)
    flagged = compute_features_for_ticker(df, {df["date"].iloc[_BLACKOUT_JUMP_AT]})
    segment_only = compute_features_for_ticker(
        df.iloc[_BLACKOUT_JUMP_AT:].reset_index(drop=True)
    )

    first_clear = _BLACKOUT_JUMP_AT + HARD_FLAG_BLACKOUT_SESSIONS
    assert first_clear < _BLACKOUT_ROWS
    for column in INDICATOR_COLUMNS:
        pd.testing.assert_series_equal(
            flagged[column].iloc[first_clear:].reset_index(drop=True),
            segment_only[column].iloc[HARD_FLAG_BLACKOUT_SESSIONS:].reset_index(drop=True),
            check_dtype=False,
            check_names=False,
        )


def test_the_recursive_indicators_carry_no_pre_flag_contamination():
    """The specific defect: `rsi`/`atr` (Wilder), `macd_*` (EWM from series
    start) and `obv` (cumsum) are not window-bounded, so before segmentation
    a level shift survived the 78-session blackout — `macd_signal` 54.5%
    wrong, `obv` still 12% off nine months later."""
    df = _step_ohlcv(_BLACKOUT_ROWS, _BLACKOUT_JUMP_AT)
    contaminated = compute_features_for_ticker(df)
    flagged = compute_features_for_ticker(df, {df["date"].iloc[_BLACKOUT_JUMP_AT]})

    first_clear = _BLACKOUT_JUMP_AT + HARD_FLAG_BLACKOUT_SESSIONS
    for column in ("rsi", "macd_line", "macd_signal", "obv"):
        assert flagged[column].iloc[first_clear] != pytest.approx(
            contaminated[column].iloc[first_clear]
        ), f"{column} still matches the whole-series value, so it was not reseeded"


def test_the_first_session_past_the_lookback_is_computed_normally():
    """The scenario the spec states explicitly: no window reaching that far
    back can still span the step, so nothing is withheld."""
    df = _step_ohlcv(_BLACKOUT_ROWS, _BLACKOUT_JUMP_AT)
    flagged = compute_features_for_ticker(df, {df["date"].iloc[_BLACKOUT_JUMP_AT]})

    first_clear = _BLACKOUT_JUMP_AT + HARD_FLAG_BLACKOUT_SESSIONS
    assert not pd.isna(flagged["senkou_span_b"].iloc[first_clear])
    assert pd.isna(flagged["senkou_span_b"].iloc[first_clear - 1])


def test_target_nulling_is_unchanged_by_the_indicator_blackout():
    """The two effects point in opposite directions along the series and must
    not bleed into each other: targets null for the TARGET_HORIZON rows
    *before* the flag, indicators for the lookback *at and after* it."""
    df = _step_ohlcv(_BLACKOUT_ROWS, _BLACKOUT_JUMP_AT)
    baseline = compute_features_for_ticker(df)
    flagged = compute_features_for_ticker(df, {df["date"].iloc[_BLACKOUT_JUMP_AT]})

    newly_null = {
        i
        for i in range(_BLACKOUT_ROWS)
        if pd.isna(flagged["target"].iloc[i]) and not pd.isna(baseline["target"].iloc[i])
    }
    assert newly_null == set(
        range(_BLACKOUT_JUMP_AT - TARGET_HORIZON, _BLACKOUT_JUMP_AT)
    )
    # The flagged session's own target, and the targets throughout the
    # blackout, stay computed — they span closes on one side of the step only.
    assert not pd.isna(flagged["target"].iloc[_BLACKOUT_JUMP_AT])
    assert not pd.isna(flagged["target"].iloc[_BLACKOUT_JUMP_AT + 30])


def test_near_gap_is_not_altered_by_the_blackout():
    """`near_gap` describes calendar gaps, not price discontinuities. It is
    the blackout's model, not its subject."""
    df = _step_ohlcv(_BLACKOUT_ROWS, _BLACKOUT_JUMP_AT)
    plain = compute_features_for_ticker(df)
    flagged = compute_features_for_ticker(df, {df["date"].iloc[_BLACKOUT_JUMP_AT]})
    pd.testing.assert_series_equal(plain["near_gap"], flagged["near_gap"])


def test_a_flag_near_the_end_blacks_out_only_the_rows_that_exist():
    df = _step_ohlcv(40, 35)
    features = compute_features_for_ticker(df, {df["date"].iloc[35]})
    assert len(features) == 40
    assert features["bb_middle"].iloc[35:].isna().all()
    assert not pd.isna(features["bb_middle"].iloc[34])


def test_obv_widens_to_hold_the_null_rather_than_rejecting_it():
    """`obv` is an integer cumulative sum; the blackout must not fail on it,
    and its nulls have to survive the upsert to `features`."""
    df = _step_ohlcv(_BLACKOUT_ROWS, _BLACKOUT_JUMP_AT)
    features = compute_features_for_ticker(df, {df["date"].iloc[_BLACKOUT_JUMP_AT]})
    assert pd.isna(features["obv"].iloc[_BLACKOUT_JUMP_AT])
    assert not pd.isna(features["obv"].iloc[0])


def test_recompute_features_persists_the_indicator_blackout(monkeypatch, tmp_path):
    """End to end: a hard flag in the sidecar has to reach the stored
    indicator columns, not just the in-memory frame."""
    ticker = "VHM"
    df = _step_ohlcv(_BLACKOUT_ROWS, _BLACKOUT_JUMP_AT)
    flagged_date = df["date"].iloc[_BLACKOUT_JUMP_AT]

    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.executemany(
        "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (ticker, r.date, r.open, r.high, r.low, r.close, r.volume)
            for r in df.itertuples()
        ],
    )
    conn.execute(
        "INSERT INTO ohlcv_quality_flags (ticker, date, flag_tier, log_return, "
        "limit_is_unverified_fallback, flagged_at) "
        "VALUES (?, ?, 'hard', ?, 0, '2026-08-28T00:00:00')",
        (ticker, flagged_date, -0.6931),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        feature_engineering, "get_connection", lambda: sqlite3.connect(db_path)
    )
    assert recompute_features_for_ticker(ticker) == _BLACKOUT_ROWS

    dates = df["date"].tolist()
    first_clear = _BLACKOUT_JUMP_AT + HARD_FLAG_BLACKOUT_SESSIONS
    conn = sqlite3.connect(db_path)
    try:
        stored = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT date, senkou_span_b, bb_middle, kijun_sen, macd_line, "
                "rsi, atr, obv FROM features WHERE ticker = ?",
                (ticker,),
            )
        }
    finally:
        conn.close()

    for position in (_BLACKOUT_JUMP_AT, _BLACKOUT_JUMP_AT + 40, first_clear - 1):
        assert all(value is None for value in stored[dates[position]]), (
            f"row {position} is inside the blackout and must store nulls"
        )
    assert all(value is not None for value in stored[dates[first_clear]])


def test_recompute_features_reads_persisted_hard_flags(monkeypatch, tmp_path):
    """End to end: a flag written to the sidecar must reach the target column,
    through the same connection the caller redirected."""
    ticker = "VHM"
    rows = 40
    jump_at = 20
    df = _step_ohlcv(rows, jump_at)
    flagged_date = df["date"].iloc[jump_at]

    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.executemany(
        "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (ticker, r.date, r.open, r.high, r.low, r.close, r.volume)
            for r in df.itertuples()
        ],
    )
    conn.execute(
        "INSERT INTO ohlcv_quality_flags (ticker, date, flag_tier, log_return, "
        "limit_is_unverified_fallback, flagged_at) "
        "VALUES (?, ?, 'hard', ?, 0, '2026-08-28T00:00:00')",
        (ticker, flagged_date, -0.6931),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        feature_engineering, "get_connection", lambda: sqlite3.connect(db_path)
    )
    assert recompute_features_for_ticker(ticker) == rows

    conn = sqlite3.connect(db_path)
    try:
        targets = dict(
            conn.execute(
                "SELECT date, target FROM features WHERE ticker = ? ORDER BY date",
                (ticker,),
            )
        )
    finally:
        conn.close()

    dates = df["date"].tolist()
    for offset in range(1, TARGET_HORIZON + 1):
        assert targets[dates[jump_at - offset]] is None, (
            f"target {offset} sessions before the flagged step should be null"
        )
    assert targets[dates[jump_at]] is not None
    assert targets[dates[jump_at - TARGET_HORIZON - 1]] is not None


# --- non-priced rows and invalid-close flags (task 9.1 follow-up) ---


def test_non_priced_sessions_are_dropped_before_indicators_are_computed(
    monkeypatch, tmp_path
):
    """Zero closes arrive in long runs on suspended and delisted symbols —
    37 symbols and 1,122 rows in the first full ingest, `AUM` alone with 120
    consecutive. A close of zero is not a price, so it cannot take part in an
    indicator: the rows stay in `ohlcv` as a faithful record and never reach
    `features`.
    """
    ticker = "SUSP"
    dates = _dates(120)
    db_path = _seed_ohlcv_db(tmp_path, ticker, dates)

    # A 30-session run of zeros in the middle, as the real data has.
    zeroed = dates[40:70]
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "UPDATE ohlcv SET open=0, high=0, low=0, close=0 WHERE ticker=? AND date=?",
        [(ticker, d) for d in zeroed],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        feature_engineering, "get_connection", lambda: sqlite3.connect(db_path)
    )

    count = recompute_features_for_ticker(ticker)

    assert count == len(dates) - len(zeroed)
    conn = sqlite3.connect(db_path)
    try:
        feature_dates = {row[0] for row in conn.execute(
            "SELECT date FROM features WHERE ticker = ?", (ticker,)
        )}
        stored = conn.execute(
            "SELECT COUNT(*) FROM ohlcv WHERE ticker = ?", (ticker,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert feature_dates.isdisjoint(zeroed)
    # `ohlcv` keeps every row the source returned.
    assert stored == len(dates)

    # The run leaves a 30-day hole, which is a calendar gap by any measure —
    # so `near_gap` excludes the sessions whose lookback spans it, through
    # machinery that already existed rather than a quality-gate blackout.
    conn = sqlite3.connect(db_path)
    try:
        after_gap = conn.execute(
            "SELECT near_gap FROM features WHERE ticker = ? AND date = ?",
            (ticker, dates[75]),
        ).fetchone()
    finally:
        conn.close()
    assert after_gap[0] == 1


def test_an_invalid_close_flag_does_not_black_out_or_segment(monkeypatch, tmp_path):
    """A hard flag has two consequences and only one of them applies here.
    An invalid close is absent data, not a change of price scale, so it must
    not trigger the 78-session blackout or a segment boundary — otherwise a
    120-row run of zeros would shred the series into 120 one-row segments
    and void 78 sessions apiece.
    """
    ticker = "SUSP"
    dates = _dates(200)
    db_path = _seed_ohlcv_db(tmp_path, ticker, dates)

    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE ohlcv SET open=0, high=0, low=0, close=0 WHERE ticker=? AND date=?",
        (ticker, dates[100]),
    )
    # The gate records it as hard, with the reason that distinguishes it.
    conn.execute(
        "INSERT INTO ohlcv_quality_flags (ticker, date, flag_tier, flag_reason, "
        "log_return, limit_is_unverified_fallback, flagged_at) "
        "VALUES (?, ?, 'hard', 'invalid_close', 0.0, 0, '2026-09-07T00:00:00')",
        (ticker, dates[100]),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        feature_engineering, "get_connection", lambda: sqlite3.connect(db_path)
    )
    recompute_features_for_ticker(ticker)

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT date, senkou_span_b, near_gap FROM features "
            "WHERE ticker = ? ORDER BY date", (ticker,)
        ).fetchall()
    finally:
        conn.close()

    by_date = {date_: (span_b, near_gap) for date_, span_b, near_gap in rows}
    # The zero row itself is gone, not blacked out.
    assert dates[100] not in by_date
    # And the sessions after it are computed normally. Under the old
    # treatment this flag blacked out the next 78 of them, so a non-null
    # indicator here is the whole point.
    assert by_date[dates[130]][0] is not None
    assert by_date[dates[150]][0] is not None
    # A single absent session is not a calendar gap — it is one day, well
    # inside `GAP_THRESHOLD_DAYS`. A *run* of them is, which is what the
    # test above covers.
    assert by_date[dates[130]][1] == 0
