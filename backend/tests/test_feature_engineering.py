import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest

import numpy as np

import app.ml.feature_engineering as feature_engineering
from app.db.schema import CREATE_FEATURES_TABLE, CREATE_OHLCV_TABLE
from app.ml.feature_engineering import (
    CHIKOU_PERIOD,
    LONGEST_LOOKBACK_END_OFFSET,
    LONGEST_LOOKBACK_WINDOW,
    TARGET_HORIZON,
    _wilder_smooth,
    compute_atr,
    compute_bollinger_bands,
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
