import numpy as np
import pandas as pd
import xgboost as xgb

from app.ml import training
from app.ml.training import (
    FEATURE_COLUMNS,
    TARGET_HORIZON,
    TRAINING_TICKERS,
    assemble_feature_matrix,
    compute_fold_boundaries,
    filter_clean_labeled,
    load_training_features,
    purge_training_rows,
    train_xgb_model,
)


def test_assemble_feature_matrix_excludes_ticker_identity():
    # design.md Decision 3: no ticker column or ticker-derived encoding
    # may appear among the model's input features, in any form.
    df = pd.DataFrame(
        {
            "ticker": ["TCB", "VIB"],
            "date": ["2024-01-01", "2024-01-02"],
            "tenkan_sen": [1.0, 2.0],
            "kijun_sen": [1.0, 2.0],
            "senkou_span_a": [1.0, 2.0],
            "senkou_span_b": [1.0, 2.0],
            "chikou_signal": [1.0, 2.0],
            "rsi": [50.0, 51.0],
            "macd_line": [0.1, 0.2],
            "macd_signal": [0.1, 0.2],
            "macd_histogram": [0.0, 0.0],
            "bb_upper": [1.0, 2.0],
            "bb_middle": [1.0, 2.0],
            "bb_lower": [1.0, 2.0],
            "atr": [1.0, 2.0],
            "obv": [1000.0, 1100.0],
            "target": [0.01, -0.02],
            "near_gap": [0, 0],
            "computed_at": ["2024-01-03T00:00:00", "2024-01-03T00:00:00"],
        }
    )

    matrix = assemble_feature_matrix(df)

    assert "ticker" not in matrix.columns
    assert not any("ticker" in col.lower() for col in matrix.columns)
    assert list(matrix.columns) == FEATURE_COLUMNS


def test_filter_clean_labeled_excludes_near_gap_and_null_target_rows():
    # design.md Decision 2: "clean+labeled" rows exclude near_gap=1 (unknown-
    # quality lookback) and null target (insufficient future data), checked
    # against the current app.db (~11,480 rows expected pooled across the 9
    # training tickers) rather than a synthetic fixture, since this is a
    # data-quality assertion, not a pure-function unit test.
    raw = load_training_features()

    assert set(raw["ticker"].unique()) <= set(TRAINING_TICKERS)

    clean = filter_clean_labeled(raw)

    assert not (clean["near_gap"] == 1).any()
    assert not clean["target"].isna().any()

    # Sane range, not an exact literal (design.md: ~11,480 rows; ticker
    # histories grow over time as more data is ingested).
    assert 10_000 <= len(clean) <= 20_000


def _make_full_df(n_dates_per_ticker: int) -> pd.DataFrame:
    # Two tickers, one calendar-date sequence each, every row clean+labeled
    # except the trailing TARGET_HORIZON rows (mirrors real `features`:
    # target is null once the horizon runs past the ticker's last row).
    dates = pd.date_range("2024-01-01", periods=n_dates_per_ticker, freq="D").strftime("%Y-%m-%d")
    frames = []
    for ticker in ["AAA", "BBB"]:
        frames.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": dates,
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


def test_saved_model_reloads_from_disk_and_predicts(monkeypatch, tmp_path):
    # tasks.md 4.3: a trained model artifact must be reloadable from disk
    # and able to produce a prediction for a sample feature row. Uses
    # synthetic data and an isolated tmp_path model file (matching this
    # suite's monkeypatch/tmp_path convention for filesystem side effects)
    # since this is a mechanics check, not a data-quality assertion.
    model_path = tmp_path / "model.json"
    monkeypatch.setattr(training, "MODEL_PATH", model_path)

    rng = np.random.default_rng(0)
    n = 100
    X = pd.DataFrame(rng.normal(size=(n, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS)
    y = pd.Series(rng.normal(scale=0.01, size=n))

    model = train_xgb_model(X.iloc[:80], y.iloc[:80], X.iloc[80:], y.iloc[80:])
    model.save_model(training.MODEL_PATH)

    assert model_path.exists()

    reloaded = xgb.Booster()
    reloaded.load_model(training.MODEL_PATH)

    sample = X.iloc[[0]]
    prediction = reloaded.predict(xgb.DMatrix(sample))

    assert prediction.shape == (1,)
    assert np.isfinite(prediction[0])
