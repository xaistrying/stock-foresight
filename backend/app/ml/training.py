"""Walk-forward split helpers over the `features` table. Holds no model.

The XGBoost direction model that these helpers were written for is retired. What stays is the
leakage-safe split machinery (`compute_fold_boundaries`, `purge_training_rows`) and the clean-row
filter, which `scripts/evaluate_cross_sectional_momentum.py` and its tests still use.
"""

import pandas as pd

TRAINING_TICKERS = ["TCB", "VIB", "VHM", "VND", "MWG", "HPG", "MSN", "VNM", "SAB"]

N_FOLDS = 5

TARGET_HORIZON = 5

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


def filter_clean_labeled(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only "clean+labeled" rows per design.md Decision 2: exclude
    `near_gap = 1` (unknown-quality indicator lookback), rows with a
    null `target` (insufficient future data per M2), and rows with any null
    indicator column.

    The last condition catches a hard-flag blackout
    (`blackout_indicators_after_hard_flags` in feature_engineering.py,
    tasks.md 4.7/5.4) whose tail can fall outside the `near_gap` window that
    happened to cover the rest of it — `near_gap` describes calendar gaps,
    not price discontinuities, so it must not be the only gate. Checked
    directly against `FEATURE_COLUMNS` rather than a separate flag column,
    so it can't drift out of sync with the actual nulls.
    """
    indicators_present = df[FEATURE_COLUMNS].notna().all(axis=1)
    return df[
        (df["near_gap"] == 0) & (df["target"].notna()) & indicators_present
    ].reset_index(drop=True)


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
