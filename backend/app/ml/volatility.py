"""HAR-RV (Heterogeneous Autoregressive Realized Volatility) linear model and the 5-session band.

The model predicts the log of the standard deviation of the next five DAILY log returns from
the trailing 5-, 20- and 60-session standard deviations. Its output, `sigma_daily_pct`, is a
daily figure and is never labelled "5 sessions". The displayed band is

    range_5s_pct = range_k * sqrt(5) * sigma_daily_pct

(Rule 1: 5 trading sessions; Rule 2: a percentage, never a raw log value). `range_k` is one global
multiplier stored in the model artifact, fitted out of time so the band contains
|ln(close[t+5]/close[t])| with the artifact's nominal coverage (design.md Decisions 1-4).

The artifact is `data/models/har_rv_model.json` (Decision 11): written atomically by
scripts/train_har_rv.py and loaded once into memory by `load_model()`, which re-reads only when the
file changes. Serving needs numpy only: no pickle, no scikit-learn.

Public API: load_model, sigma_daily_pct_from_closes, band_from_sigma, sigma_out_of_bounds,
read_recent_closes, range_hit_rate. Training helpers: build_window_frame, build_training_dataset,
sigma_pct, fit_range_k.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from app.db.connection import get_connection

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "har_rv_model.json"
SCHEMA_VERSION = 1

# Minimum sessions needed to compute all three HAR windows + target
MIN_SESSIONS = 65  # 60 for longest window + 5 for forward target


def _load_ohlcv(ticker: str) -> pd.DataFrame:
    """Load close prices for a ticker from the OHLCV table, ascending date."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT date, close FROM ohlcv WHERE ticker = ? ORDER BY date ASC",
            (ticker,),
        ).fetchall()
    finally:
        conn.close()
    return pd.DataFrame(rows, columns=["date", "close"])


def _build_har_features(closes: pd.Series) -> pd.DataFrame:
    """Compute HAR-RV features from a close price series.

    Returns a DataFrame with columns: rv5, rv20, rv60
    where rvN = trailing N-session realized volatility (std of log returns).
    Index aligns with the closes index.
    """
    log_returns = np.log(closes / closes.shift(1))

    def rolling_vol(n: int) -> pd.Series:
        return log_returns.rolling(n).std()

    return pd.DataFrame(
        {
            "rv5": rolling_vol(5),
            "rv20": rolling_vol(20),
            "rv60": rolling_vol(60),
        }
    )


HORIZON_SESSIONS = 5  # Rule 1: rows ahead, as in compute_target
FEATURE_NAMES = ("rv5", "rv20", "rv60")
# HOSE daily price limit (DAILY_PRICE_LIMITS["HSX"]): a sustained daily sigma above it is an
# artefact, not a market state. New threshold, covered by no domain rule.
SIGMA_DAILY_MAX_PCT = 7.0


def build_window_frame(dates: pd.Series, closes: pd.Series) -> pd.DataFrame:
    """One row per session t whose features and 5-session outcome all exist.

    Columns: pos (row position of t), date, outcome_date (date at t+5), rv5/rv20/rv60,
    realised_std (std of the next five daily log returns, the HAR target) and
    r5 = ln(close[t+5] / close[t]) (Rule 1's outcome). `closes` must be positive.
    """
    close = closes.reset_index(drop=True).astype(float)
    date = dates.reset_index(drop=True)
    log_returns = np.log(close / close.shift(1))
    rolling = {name: log_returns.rolling(int(name[2:])).std() for name in FEATURE_NAMES}
    frame = pd.DataFrame(
        {
            "pos": np.arange(len(close)),
            "date": date,
            "outcome_date": date.shift(-HORIZON_SESSIONS),
            **rolling,
            "realised_std": rolling["rv5"].shift(-HORIZON_SESSIONS),
            "r5": np.log(close.shift(-HORIZON_SESSIONS) / close),
        }
    )
    return frame.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)


def sigma_pct(rv: np.ndarray, intercept: float, coef: np.ndarray) -> np.ndarray:
    """Daily sigma in percent, exp(intercept + coef·rv) × 100, for rows of (rv5, rv20, rv60)."""
    return np.exp(intercept + rv @ coef) * 100.0


def log_realised(frame: pd.DataFrame) -> pd.Series:
    """ln of the HAR target (std of the next five daily log returns), floored as in training."""
    return np.log(frame["realised_std"].clip(lower=1e-10))


def fit_har_ols(frame: pd.DataFrame) -> tuple[float, np.ndarray]:
    """OLS of ln(realised_std) on rv5, rv20, rv60: (intercept, coef). Same fit as LinearRegression."""
    design = np.column_stack([np.ones(len(frame)), frame[list(FEATURE_NAMES)].to_numpy()])
    beta, *_ = np.linalg.lstsq(design, log_realised(frame).to_numpy(), rcond=None)
    return float(beta[0]), beta[1:]


def fit_range_k(z: np.ndarray, coverage: float) -> float:
    """Empirical `coverage`-quantile of z = |r5| / (√5 · sigma), the band multiplier."""
    return float(np.quantile(z, coverage))


def build_training_dataset(ticker: str) -> tuple[pd.DataFrame, pd.Series] | None:
    """Build (X, y) for a single ticker.

    y = forward 5-session realized volatility (Rule 1).
    X = rv5, rv20, rv60 at each session.
    Returns None if the ticker has fewer than MIN_SESSIONS rows or
    insufficient valid rows after cleaning.
    """
    df = _load_ohlcv(ticker)
    if len(df) < MIN_SESSIONS:
        return None

    # Drop zero / negative closes (stale-price / delisted artefacts)
    df = df[df["close"] > 0].copy()
    if len(df) < MIN_SESSIONS:
        return None

    features = _build_har_features(df["close"])
    log_returns = np.log(df["close"] / df["close"].shift(1))

    # Forward 5-session realized volatility as target
    target_vals: list[float | None] = []
    for i in range(len(df)):
        window = log_returns.iloc[i + 1 : i + 6]
        if len(window) < 5:
            target_vals.append(None)
        else:
            val = window.std()
            target_vals.append(float(val) if np.isfinite(val) else None)

    target = pd.Series(target_vals, index=df.index)

    combined = features.copy()
    combined["target"] = target
    combined = combined.dropna()
    # Also drop any remaining inf/-inf from extreme log-return spikes
    combined = combined.replace([np.inf, -np.inf], np.nan).dropna()

    # Remove last 5 rows where forward target cannot be computed
    combined = combined.iloc[:-5]
    if len(combined) < 10:
        return None

    X = combined[["rv5", "rv20", "rv60"]]
    # log-volatility as target (Finding 5: linear model on log-vol)
    y = np.log(combined["target"].clip(lower=1e-10))
    # Drop any remaining NaN/inf in y
    mask = np.isfinite(y)
    return X[mask], y[mask]


# ---------------------------------------------------------------------------
# Serving: artifact, sigma, band, hit-rate
# ---------------------------------------------------------------------------

# Closes needed for rv60: 60 log returns.
MIN_CLOSES = 61
# range_hit_rate scores at most 50 non-overlapping windows (about a year) and needs 20 for a rate.
# New thresholds (design.md Decision 10), covered by no domain rule.
HIT_RATE_MAX_WINDOWS = 50
HIT_RATE_MIN_WINDOWS = 20
HISTORY_ROWS = MIN_CLOSES + HORIZON_SESSIONS * (HIT_RATE_MAX_WINDOWS - 1) + HORIZON_SESSIONS  # 311
_SQRT_HORIZON = math.sqrt(HORIZON_SESSIONS)


@dataclass(frozen=True)
class HarModel:
    model_version: str
    trained_at: str
    data_through: str
    intercept: float
    coef: tuple[float, float, float]  # rv5, rv20, rv60
    range_k: float
    range_coverage: float
    universe: frozenset[str]
    n_rows: int
    validation: dict  # read-only by convention


_model_cache: tuple[tuple, HarModel | None] | None = None  # (file signature, parsed model)


def parse_artifact(raw: dict) -> HarModel:
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version {raw['schema_version']!r}")
    if list(raw["features"]) != list(FEATURE_NAMES):
        raise ValueError("unexpected features")
    coef = tuple(float(raw["coef"][name]) for name in FEATURE_NAMES)
    intercept, range_k = float(raw["intercept"]), float(raw["range_k"])
    range_coverage = float(raw["range_coverage"])
    if not all(math.isfinite(x) for x in (*coef, intercept, range_k, range_coverage)):
        raise ValueError("non-finite number")
    if range_k <= 0 or not 0 < range_coverage < 1:
        raise ValueError("range_k or range_coverage out of range")
    return HarModel(
        model_version=str(raw["model_version"]),
        trained_at=str(raw["trained_at"]),
        data_through=str(raw["data_through"]),
        intercept=intercept,
        coef=coef,
        range_k=range_k,
        range_coverage=range_coverage,
        universe=frozenset(str(s) for s in raw["universe"]["symbols"]),
        n_rows=int(raw["n_rows"]),
        validation=dict(raw["validation"]),
    )


def load_model() -> HarModel | None:
    """The served model, or None (never raises) if the artifact is missing or unusable.

    Cached on the file's (mtime, inode, size): a retrain, which replaces the file atomically,
    is picked up without a restart for the cost of one stat per call. A bad file is logged once
    per change, not once per request.
    """
    global _model_cache
    try:
        stat = MODEL_PATH.stat()
        signature = (str(MODEL_PATH), stat.st_mtime_ns, stat.st_ino, stat.st_size)
    except OSError:
        signature = (str(MODEL_PATH), None)
    if _model_cache is not None and _model_cache[0] == signature:
        return _model_cache[1]

    model = None
    if signature[1] is None:
        logger.warning("HAR-RV model not found at %s: run scripts/train_har_rv.py", MODEL_PATH)
    else:
        try:
            with open(MODEL_PATH, encoding="utf-8") as f:
                model = parse_artifact(json.load(f))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.error("HAR-RV model at %s is unusable: %s", MODEL_PATH, exc)
    _model_cache = (signature, model)
    return model


def _rolling_std(log_returns: np.ndarray, window: int) -> np.ndarray:
    """Std (ddof=1) of the `window` log returns ending at each day; NaN until enough exist."""
    out = np.full(len(log_returns), np.nan)
    if len(log_returns) >= window:
        out[window - 1 :] = sliding_window_view(log_returns, window).std(axis=1, ddof=1)
    return out


def _features(closes: np.ndarray) -> np.ndarray:
    """Rows (rv5, rv20, rv60) indexed like `closes` (NaN where undefined)."""
    log_returns = np.concatenate([[np.nan], np.diff(np.log(closes))])
    # Day i's return is log_returns[i]; its trailing window ends at i, so rolling over the
    # returns from day 1 on and shifting by one puts rv(t) at index t.
    rv = [np.concatenate([[np.nan], _rolling_std(log_returns[1:], w)]) for w in (5, 20, 60)]
    return np.column_stack(rv)


def sigma_daily_pct_from_closes(closes: np.ndarray, model: HarModel) -> float | None:
    """exp(intercept + coef·[rv5, rv20, rv60]) × 100 at the last close; None under 61 closes."""
    if len(closes) < MIN_CLOSES:
        return None
    rv = _features(np.asarray(closes, dtype=float)[-MIN_CLOSES:])[-1]
    if not np.all(np.isfinite(rv)):
        return None
    return float(sigma_pct(rv[None, :], model.intercept, np.array(model.coef))[0])


def scaled_band(sigma_daily_pct, range_k: float):
    """range_k × √5 × sigma for a float or an array, never in place.

    np.multiply on purpose: with NumPy 2.2.6 on CPython 3.14, `scalar * local_array` can reuse the
    local's buffer once the array exceeds 256 KiB (32,768 doubles) and silently overwrite it.
    """
    return np.multiply(sigma_daily_pct, range_k * _SQRT_HORIZON)


def band_from_sigma(sigma_daily_pct: float, model: HarModel) -> float:
    """Half-width of the typical 5-session move, in percent: range_k × √5 × sigma."""
    return float(scaled_band(sigma_daily_pct, model.range_k))


def sigma_out_of_bounds(sigma_daily_pct: float) -> bool:
    return not math.isfinite(sigma_daily_pct) or sigma_daily_pct > SIGMA_DAILY_MAX_PCT


def read_recent_closes(ticker: str, limit: int = HISTORY_ROWS) -> tuple[list[str], np.ndarray]:
    """The ticker's latest `limit` positive closes as (dates, closes), ascending by date."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT date, close FROM ohlcv WHERE ticker = ? AND close > 0 "
            "ORDER BY date DESC LIMIT ?",
            (ticker, limit),
        ).fetchall()
    finally:
        conn.close()
    rows.reverse()
    return [r[0] for r in rows], np.array([r[1] for r in rows], dtype=float)


def _window_hits(closes: np.ndarray, model: HarModel) -> tuple[np.ndarray, np.ndarray]:
    """(window start rows, hit flags) ascending, over the newest <= 50 non-overlapping windows.

    The newest window starts at the latest row t that has a t+5 row; the rest step back 5 rows.
    sigma(t) uses closes up to t only; the one later close read is the outcome close t+5. A window
    whose sigma is out of bounds or not finite is dropped (the slot is not refilled).
    """
    closes = np.asarray(closes, dtype=float)[-HISTORY_ROWS:]
    newest = len(closes) - 1 - HORIZON_SESSIONS
    starts = newest - HORIZON_SESSIONS * np.arange(HIT_RATE_MAX_WINDOWS)
    starts = starts[starts >= MIN_CLOSES - 1][::-1]
    if len(starts) == 0:
        return starts, np.array([], dtype=bool)
    sigma = sigma_pct(_features(closes)[starts], model.intercept, np.array(model.coef))
    keep = np.isfinite(sigma) & (sigma <= SIGMA_DAILY_MAX_PCT)
    starts, sigma = starts[keep], sigma[keep]
    move = np.abs(np.log(closes[starts + HORIZON_SESSIONS] / closes[starts])) * 100.0
    return starts, move <= scaled_band(sigma, model.range_k)


def range_hit_rate(closes: np.ndarray, model: HarModel) -> dict:
    """{rate, n}: share of the last n five-session moves that stayed inside the band at the time.

    Descriptive, not a probability or Confidence: 50 windows leave a sd of about 0.07, and
    `range_k` was fitted on history that includes these windows. rate is None under 20 windows.
    """
    _, hits = _window_hits(closes, model)
    n = int(len(hits))
    return {"rate": float(hits.mean()) if n >= HIT_RATE_MIN_WINDOWS else None, "n": n}
