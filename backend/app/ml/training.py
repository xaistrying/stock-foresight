from pathlib import Path

import pandas as pd
import xgboost as xgb

from app.db.connection import get_connection

MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "pooled_xgb_model.json"

TRAINING_TICKERS = ["TCB", "VIB", "VHM", "VND", "MWG", "HPG", "MSN", "VNM", "SAB"]

N_FOLDS = 5

TARGET_HORIZON = 5

# design.md Decision 5: conservative, untuned posture — shallow trees, a
# moderate learning rate relying on early stopping rather than a large
# fixed n_estimators, subsample/colsample_bytree < 1.0 for regularization,
# and a min_child_weight above the library default (1). Chosen for the
# sample-size ceiling documented there (row count overstates the
# effective independent sample size, since labels overlap 4-of-5 days
# with their neighbors under Rule 1's 5-session horizon), not tuned
# against any validation metric.
XGB_PARAMS = {
    "objective": "reg:squarederror",
    "max_depth": 3,
    "eta": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "seed": 0,
}
MAX_BOOST_ROUNDS = 500
EARLY_STOPPING_ROUNDS = 20

FEATURE_COLUMNS = [
    "tenkan_sen",
    "kijun_sen",
    "senkou_span_a",
    "senkou_span_b",
    "chikou_signal",
    "rsi",
    "macd_line",
    "macd_signal",
    "macd_histogram",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "atr",
    "obv",
]


def load_training_features() -> pd.DataFrame:
    """Read `features` rows for `TRAINING_TICKERS` (design.md Decision 1),
    ordered by ticker then date ascending. No filtering or feature-matrix
    assembly here — see tasks 2.2/2.3.
    """
    placeholders = ", ".join("?" for _ in TRAINING_TICKERS)
    conn = get_connection()
    try:
        return pd.read_sql_query(
            f"SELECT * FROM features WHERE ticker IN ({placeholders}) "
            "ORDER BY ticker ASC, date ASC",
            conn,
            params=tuple(TRAINING_TICKERS),
        )
    finally:
        conn.close()


def filter_clean_labeled(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only "clean+labeled" rows per design.md Decision 2: exclude
    `near_gap = 1` (unknown-quality indicator lookback) and rows with a
    null `target` (insufficient future data per M2).
    """
    return df[(df["near_gap"] == 0) & (df["target"].notna())].reset_index(drop=True)


def assemble_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Assemble the model input feature matrix from the existing indicator
    columns only (design.md Decision 3) — no `ticker` or other
    ticker-derived column is included, so the model can't memorize
    per-ticker base rates.
    """
    return df[FEATURE_COLUMNS]


def compute_fold_boundaries(df: pd.DataFrame, n_folds: int = N_FOLDS) -> list[str]:
    """Compute pooled, shared calendar-date fold boundaries (design.md
    Decision 4): every ticker's rows are partitioned using the same set of
    date cutoffs, not independent per-ticker cutoffs. Boundaries split the
    pooled set of distinct dates into `n_folds` expanding-window folds —
    each boundary date is the first test-period date for its fold; a
    boundary at index i has all dates before it as candidate training data
    (subject to task 3.2's purge) and dates from it up to (exclusive of)
    the next boundary as that fold's test period.

    Returns a list of `n_folds - 1` boundary dates (the split points
    between successive folds' test periods) — fold 1's training set uses
    everything before boundaries[0], fold 2's test set runs from
    boundaries[0] up to boundaries[1], etc. This is boundary computation
    only; row-level train/test assignment and the purge happen in 3.2.
    """
    if not (4 <= n_folds <= 6):
        raise ValueError("design.md Decision 4 requires 4-6 folds")

    dates = sorted(df["date"].unique())
    if len(dates) < n_folds:
        raise ValueError("not enough distinct dates to form the requested folds")

    chunk_size = len(dates) / n_folds
    boundaries = []
    for fold_index in range(1, n_folds):
        cutoff = int(round(fold_index * chunk_size))
        boundaries.append(dates[cutoff])
    return boundaries


def _label_dates_by_ticker(full_df: pd.DataFrame) -> pd.DataFrame:
    """Map each `(ticker, date)` row to its true label date — the date of
    the row `TARGET_HORIZON` positions ahead in that ticker's *full*,
    unfiltered stored sequence (matching how `compute_target` in
    feature_engineering.py derives `target` via `close.shift(-5)` on the
    complete per-ticker row order). Counting 5 rows ahead within a
    near_gap-filtered subset would systematically overshoot near the
    ~78-row-wide near_gap bands (design.md Decision 2), so this must run
    against `full_df` (all rows for the ticker, not the clean+labeled
    subset) before any near_gap/target filtering is applied.

    Returns a `(ticker, date, label_date)` frame, meant to be joined back
    onto a filtered set by `(ticker, date)` rather than by index — callers
    like `filter_clean_labeled` reset their index, so positional alignment
    can't be relied on.
    """
    parts = []
    for ticker, ticker_df in full_df.groupby("ticker", sort=False):
        ordered = ticker_df.sort_values("date")
        parts.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": ordered["date"].values,
                    "label_date": ordered["date"].shift(-TARGET_HORIZON).values,
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def purge_training_rows(full_df: pd.DataFrame, clean_df: pd.DataFrame, boundary: str) -> pd.DataFrame:
    """Apply the training-side purge for a single fold boundary (design.md
    Decision 4 / tasks.md 3.2): drop any candidate training row (from
    `clean_df`, the near_gap=0/target-not-null set) whose true label date
    — looked up via `full_df`'s unfiltered per-ticker sequence — falls at
    or after `boundary`. This removes exactly the rows whose label window
    extends into or past the test period, per ticker, regardless of how
    many raw rows before the boundary that ends up being (not always
    exactly 5 *clean* rows, since near_gap rows in between are already
    excluded from `clean_df` on their own terms).

    `full_df` must contain the ticker's complete stored row sequence
    (unfiltered) so label dates reflect the same row-offset semantics
    `compute_target` used originally; `clean_df` is the set the purge is
    applied to.
    """
    label_dates = _label_dates_by_ticker(full_df)
    merged = clean_df.merge(label_dates, on=["ticker", "date"], how="left")
    keep = (merged["label_date"].isna() | (merged["label_date"] < boundary)).to_numpy()
    return clean_df[keep]


def train_xgb_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
) -> xgb.Booster:
    """Train an XGBoost regressor against `target` using the fixed
    conservative configuration in `XGB_PARAMS` (design.md Decision 5): no
    hyperparameter search — early stopping against the supplied validation
    fold (`X_val`/`y_val`) is the only thing that determines the actual
    number of boosting rounds used.
    """
    dtrain = xgb.DMatrix(X_train, label=y_train)
    dval = xgb.DMatrix(X_val, label=y_val)
    return xgb.train(
        XGB_PARAMS,
        dtrain,
        num_boost_round=MAX_BOOST_ROUNDS,
        evals=[(dval, "validation")],
        early_stopping_rounds=EARLY_STOPPING_ROUNDS,
        verbose_eval=False,
    )


def train_final_model(full_df: pd.DataFrame, clean_df: pd.DataFrame) -> xgb.Booster:
    """Train the final pooled model (tasks.md 4.2) on the full clean+labeled
    dataset, following the same purge discipline (design.md Decision 4) as
    the walk-forward backtest folds: the most recent fold boundary's test
    window is held out as the early-stopping validation set, and the
    training side is purged against that same boundary so no training
    row's label overlaps the held-out period. This mirrors backtesting's
    per-fold train/validation split rather than introducing a separate,
    undocumented held-out scheme just for the final model.

    `full_df` is the unfiltered per-ticker sequence (needed for the purge's
    label-date lookup); `clean_df` is the near_gap=0/target-not-null set to
    train on.
    """
    boundaries = compute_fold_boundaries(clean_df)
    final_boundary = boundaries[-1]

    train_df = purge_training_rows(full_df, clean_df, final_boundary)
    train_df = train_df[train_df["date"] < final_boundary]
    val_df = clean_df[clean_df["date"] >= final_boundary]

    model = train_xgb_model(
        assemble_feature_matrix(train_df),
        train_df["target"],
        assemble_feature_matrix(val_df),
        val_df["target"],
    )

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(MODEL_PATH)
    return model
