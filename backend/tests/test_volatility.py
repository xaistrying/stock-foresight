"""Unit tests for backend/app/ml/volatility.py"""

from __future__ import annotations

import pickle
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv_df(n: int, close_start: float = 10.0, noise: float = 0.01) -> pd.DataFrame:
    """Create a synthetic OHLCV close-price DataFrame with n rows."""
    rng = np.random.default_rng(42)
    closes = close_start * np.cumprod(1 + rng.normal(0, noise, n))
    return pd.DataFrame({"date": [f"2024-{i:04d}" for i in range(n)], "close": closes})


# ---------------------------------------------------------------------------
# _build_har_features
# ---------------------------------------------------------------------------

def test_build_har_features_shape():
    from app.ml.volatility import _build_har_features

    closes = pd.Series(range(1, 71), dtype="float64")
    features = _build_har_features(closes)
    assert set(features.columns) == {"rv5", "rv20", "rv60"}
    assert len(features) == 70


def test_build_har_features_nans_at_start():
    """The first 59 rows should have NaN rv60 (warm-up period)."""
    from app.ml.volatility import _build_har_features

    df = _make_ohlcv_df(100)
    features = _build_har_features(df["close"])
    assert features["rv60"].iloc[:59].isna().all()
    assert not features["rv60"].iloc[60:].isna().any()


# ---------------------------------------------------------------------------
# predict_volatility_range
# ---------------------------------------------------------------------------

def test_predict_volatility_range_returns_none_for_too_few_rows(tmp_path, monkeypatch):
    """Returns None when fewer than 60 OHLCV sessions exist."""
    from app.ml import volatility as vol_mod
    from sklearn.linear_model import LinearRegression

    short_df = _make_ohlcv_df(30)

    def fake_load(ticker):
        return short_df

    monkeypatch.setattr(vol_mod, "_load_ohlcv", fake_load)
    # Real sklearn model (picklable)
    X_dummy = pd.DataFrame({"rv5": [0.01], "rv20": [0.012], "rv60": [0.011]})
    y_dummy = np.array([-5.0])
    fake_model = LinearRegression().fit(X_dummy, y_dummy)
    model_path = tmp_path / "har_rv_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(fake_model, f)
    monkeypatch.setattr(vol_mod, "MODEL_PATH", model_path)

    result = vol_mod.predict_volatility_range("TEST")
    assert result is None


def test_predict_volatility_range_returns_positive_float(tmp_path, monkeypatch):
    """Returns a positive float percentage for a ticker with sufficient history."""
    from app.ml import volatility as vol_mod

    df = _make_ohlcv_df(100)

    def fake_load(ticker):
        return df

    monkeypatch.setattr(vol_mod, "_load_ohlcv", fake_load)

    # Train a real micro-model to avoid mocking sklearn internals
    from sklearn.linear_model import LinearRegression
    X = pd.DataFrame({"rv5": [0.01], "rv20": [0.012], "rv60": [0.011]})
    y = np.array([-5.0])  # log-vol value
    model = LinearRegression().fit(X, y)
    model_path = tmp_path / "har_rv_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    monkeypatch.setattr(vol_mod, "MODEL_PATH", model_path)

    result = vol_mod.predict_volatility_range("TEST")
    assert result is not None
    assert isinstance(result, float)
    assert result >= 0.0  # must be non-negative (Rule 2: percentage, not log)


def test_predict_volatility_range_no_raw_log_return(tmp_path, monkeypatch):
    """Output must be a percentage (≥ 0), never a raw log return (which would be near 0 or negative)."""
    from app.ml import volatility as vol_mod

    df = _make_ohlcv_df(100, noise=0.02)

    monkeypatch.setattr(vol_mod, "_load_ohlcv", lambda t: df)

    from sklearn.linear_model import LinearRegression
    from app.ml.volatility import build_training_dataset, _build_har_features
    features = _build_har_features(df["close"]).dropna()
    y_raw = np.log(df["close"].pct_change().rolling(5).std().dropna().clip(lower=1e-10))
    # Fit on dummy data
    X_dummy = pd.DataFrame({"rv5": [0.01, 0.015], "rv20": [0.012, 0.014], "rv60": [0.011, 0.013]})
    y_dummy = np.array([-4.5, -4.2])
    model = LinearRegression().fit(X_dummy, y_dummy)
    model_path = tmp_path / "har_rv_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    monkeypatch.setattr(vol_mod, "MODEL_PATH", model_path)

    result = vol_mod.predict_volatility_range("TEST")
    # A percentage should be > 0.001 (raw log-vol would be near -5 to -3, never a positive percentage)
    assert result is not None
    assert result > 0.0


def test_predict_volatility_range_returns_none_when_model_missing(tmp_path, monkeypatch):
    """Returns None gracefully when the model file does not exist."""
    from app.ml import volatility as vol_mod

    monkeypatch.setattr(vol_mod, "MODEL_PATH", tmp_path / "nonexistent.pkl")

    result = vol_mod.predict_volatility_range("VCB")
    assert result is None
