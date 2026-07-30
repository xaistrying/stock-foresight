import sqlite3

import pandas as pd

import app.ml.backtest as backtest
from app.ml.backtest import compute_rolling_hit_rate, is_hit, persist_backtest_predictions


def test_is_hit_matching_sign_is_a_hit():
    # design.md Decision 6 / specs/model-backtest: matching-sign prediction
    # (both positive or both negative) is a hit.
    predicted = pd.Series([0.01, -0.01])
    actual = pd.Series([0.02, -0.03])

    assert is_hit(predicted, actual).tolist() == [True, True]


def test_is_hit_opposite_sign_is_a_miss():
    # Opposite-sign prediction is a miss.
    predicted = pd.Series([0.01, -0.01])
    actual = pd.Series([-0.02, 0.03])

    assert is_hit(predicted, actual).tolist() == [False, False]


def test_is_hit_zero_actual_is_a_miss_regardless_of_predicted_sign():
    # Zero actual target is a miss regardless of the predicted value's
    # sign (sign is undefined at exactly zero) — checked against both a
    # positive and a negative predicted value.
    predicted = pd.Series([0.01, -0.01])
    actual = pd.Series([0.0, 0.0])

    assert is_hit(predicted, actual).tolist() == [False, False]


def _isolated_db(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    monkeypatch.setattr(backtest, "get_connection", lambda: sqlite3.connect(db_path))


def test_compute_rolling_hit_rate_against_synthetic_persisted_predictions(
    monkeypatch, tmp_path
):
    # tasks.md 6.4: rolling hit-rate computed from a small synthetic set of
    # persisted predictions with known hits (matching sign), misses
    # (opposite sign), and the zero-actual-is-always-a-miss edge case
    # (design.md Decision 6).
    _isolated_db(monkeypatch, tmp_path)

    results = pd.DataFrame(
        {
            "ticker": ["TCB"] * 4,
            "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
            "fold": [0, 0, 0, 0],
            "predicted": [0.01, -0.01, 0.02, 0.01],
            "actual": [0.02, -0.03, -0.01, 0.0],
        }
    )
    # hits: 01-01 (match), 01-02 (match), 01-03 (opposite), 01-04 (zero actual)
    # -> 2 hits out of 4

    persist_backtest_predictions(results)

    assert compute_rolling_hit_rate("TCB", window=60) == 0.5


def test_compute_rolling_hit_rate_uses_only_the_most_recent_window(
    monkeypatch, tmp_path
):
    # A window smaller than the persisted row count must select the most
    # recent dates only, not the earliest or an arbitrary subset.
    _isolated_db(monkeypatch, tmp_path)

    results = pd.DataFrame(
        {
            "ticker": ["TCB"] * 3,
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "fold": [0, 0, 0],
            "predicted": [0.01, 0.01, 0.01],
            "actual": [-0.02, -0.02, 0.02],
        }
    )
    # oldest two dates are misses, most recent date is a hit

    persist_backtest_predictions(results)

    assert compute_rolling_hit_rate("TCB", window=1) == 1.0


def test_compute_rolling_hit_rate_returns_none_for_unknown_ticker(
    monkeypatch, tmp_path
):
    # No persisted predictions for a ticker must return None, not 0.0, so
    # callers can distinguish "no data" from a real 0% hit-rate.
    _isolated_db(monkeypatch, tmp_path)

    assert compute_rolling_hit_rate("UNKNOWN") is None
