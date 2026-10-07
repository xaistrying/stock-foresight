import numpy as np
import pandas as pd

from app.ml.training import (
    FEATURE_COLUMNS,
    TARGET_HORIZON,
    compute_fold_boundaries,
    filter_clean_labeled,
    purge_training_rows,
)


def test_filter_clean_labeled_excludes_near_gap_and_null_target_rows():
    # design.md Decision 2: "clean+labeled" rows exclude near_gap=1 (unknown-
    # quality lookback) and null target (insufficient future data).
    df = pd.DataFrame(
        {
            "ticker": ["AAA"] * 4,
            "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
            **{column: [1.0] * 4 for column in FEATURE_COLUMNS},
            "target": [0.01, 0.02, None, 0.04],
            "near_gap": [0, 1, 0, 0],
        }
    )

    clean = filter_clean_labeled(df)

    assert clean["date"].tolist() == ["2024-01-01", "2024-01-04"]


def test_filter_clean_labeled_does_not_rely_on_near_gap_for_null_indicators():
    # ohlcv-quality-gate: "Exclusion does not depend on the calendar-gap
    # flag." A hard-flag blackout (tasks.md 4.7) nulls indicator columns and
    # deliberately leaves `near_gap` alone, so such a row arrives here with
    # near_gap = 0 and a valid label — and XGBoost would fit it as an
    # all-missing feature vector rather than erroring (tasks.md 5.4).
    df = pd.DataFrame(
        {
            "ticker": ["VHM", "VHM"],
            "date": ["2024-01-01", "2024-01-02"],
            **{column: [1.0, np.nan] for column in FEATURE_COLUMNS},
            "target": [0.01, 0.02],
            "near_gap": [0, 0],
        }
    )

    clean = filter_clean_labeled(df)

    assert clean["date"].tolist() == ["2024-01-01"]


def test_filter_clean_labeled_excludes_blackout_rows_whatever_near_gap_says():
    # tasks.md 5.5: a hard-flag blackout nulls the indicators of labelled rows that `near_gap`
    # may not cover (its tail). None of them may reach a fold. The known-answer case, VHM's
    # 2018-08-14 blackout (11 rows, 2018-11-16 to 2018-11-30), is checked against the real
    # database by `scripts/verify_quality_gate.py`.
    dates = pd.date_range("2024-01-01", periods=6, freq="D").strftime("%Y-%m-%d")
    indicators = {column: [1.0, 1.0, np.nan, np.nan, np.nan, 1.0] for column in FEATURE_COLUMNS}
    df = pd.DataFrame(
        {
            "ticker": "VHM",
            "date": dates,
            **indicators,
            "target": [0.01] * 6,
            "near_gap": [0, 0, 1, 1, 0, 0],  # covers all but the blackout's tail (row 5)
        }
    )

    clean = filter_clean_labeled(df)

    assert clean["date"].tolist() == [dates[0], dates[1], dates[5]]
    assert not clean[FEATURE_COLUMNS].isna().any().any()


def _make_full_df(n_dates_per_ticker: int) -> pd.DataFrame:
    # Two tickers, one calendar-date sequence each, every row clean+labeled
    # except the trailing TARGET_HORIZON rows (mirrors real `features`:
    # target is null once the horizon runs past the ticker's last row).
    # Indicator columns are populated because `filter_clean_labeled` reads
    # them — a real `features` frame always carries all of them.
    dates = pd.date_range("2024-01-01", periods=n_dates_per_ticker, freq="D").strftime("%Y-%m-%d")
    frames = []
    for ticker in ["AAA", "BBB"]:
        frames.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": dates,
                    **{column: 1.0 for column in FEATURE_COLUMNS},
                    "near_gap": 0,
                    "target": [0.01] * (n_dates_per_ticker - TARGET_HORIZON) + [None] * TARGET_HORIZON,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_purge_training_rows_removes_all_leaking_rows():
    # Leakage guard (tasks.md 3.3): for every fold, no training row's
    # underlying close[t+5] date (its true label date, computed
    # independently here via plain row-position indexing, matching M2's
    # own compute_target semantics) may be >= that fold's test start date.
    full_df = _make_full_df(n_dates_per_ticker=30)
    clean_df = filter_clean_labeled(full_df)
    boundaries = compute_fold_boundaries(clean_df)

    for ticker, ticker_df in full_df.groupby("ticker"):
        ordered = ticker_df.sort_values("date").reset_index(drop=True)
        expected_label_date = {
            ordered["date"][i]: ordered["date"][i + TARGET_HORIZON]
            for i in range(len(ordered) - TARGET_HORIZON)
        }

        for boundary in boundaries:
            purged = purge_training_rows(full_df, clean_df, boundary)
            train_rows = purged[(purged["ticker"] == ticker) & (purged["date"] < boundary)]

            for row_date in train_rows["date"]:
                label_date = expected_label_date.get(row_date)
                if label_date is not None:
                    assert label_date < boundary, (
                        f"row {ticker}/{row_date} leaks: label date {label_date} "
                        f">= boundary {boundary}"
                    )


def test_folds_are_time_ordered_not_shuffled():
    # tasks.md 3.4: folds must come from a time-ordered walk-forward split,
    # not shuffled k-fold cross-validation (design.md Decision 4) — assert
    # row dates within each fold's train/test split are monotonically
    # non-decreasing per ticker, and that every train date precedes every
    # test date for that fold (a property random shuffling would break).
    full_df = _make_full_df(n_dates_per_ticker=30)
    clean_df = filter_clean_labeled(full_df)
    boundaries = compute_fold_boundaries(clean_df)

    test_windows = list(zip(boundaries, boundaries[1:] + [None]))

    for boundary, next_boundary in test_windows:
        train_df = purge_training_rows(full_df, clean_df, boundary)
        train_df = train_df[train_df["date"] < boundary]

        test_df = clean_df[clean_df["date"] >= boundary]
        if next_boundary is not None:
            test_df = test_df[test_df["date"] < next_boundary]

        for _, ticker_dates in train_df.groupby("ticker")["date"]:
            ordered = ticker_dates.tolist()
            assert ordered == sorted(ordered), (
                f"boundary {boundary} train dates not monotonically ordered: {ordered}"
            )
        for _, ticker_dates in test_df.groupby("ticker")["date"]:
            ordered = ticker_dates.tolist()
            assert ordered == sorted(ordered), (
                f"boundary {boundary} test dates not monotonically ordered: {ordered}"
            )

        if len(train_df) and len(test_df):
            assert train_df["date"].max() < test_df["date"].min(), (
                f"boundary {boundary}: train dates overlap or follow test dates "
                "-- inconsistent with a time-ordered (non-shuffled) split"
            )
