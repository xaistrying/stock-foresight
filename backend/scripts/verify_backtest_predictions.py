"""
Spot-check backtest_predictions against an independent recomputation of
`actual` and `hit` — same "trust but verify against real data" pattern as
verify_feature_engineering.py. Does NOT recompute `predicted` (would
require reloading the trained model) — only checks that `actual`/`hit` are
consistent with an independent row-position-based recomputation from raw
ohlcv. That's enough to catch a join/alignment/off-by-one bug in how
predictions got matched to actual outcomes, independent of model quality.

Run: python backend/scripts/verify_backtest_predictions.py
"""

import sqlite3
import numpy as np
import pandas as pd

DB_PATH = "backend/data/app.db"
SAMPLE_SIZE = 20
TOLERANCE = 1e-6

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)

    preds = pd.read_sql(
        "SELECT ticker, date, fold, predicted, actual, hit FROM backtest_predictions "
        "ORDER BY RANDOM() LIMIT ?",
        conn, params=(SAMPLE_SIZE,),
    )

    mismatches = 0
    for _, row in preds.iterrows():
        ohlcv = pd.read_sql(
            "SELECT date, close FROM ohlcv WHERE ticker=? ORDER BY date ASC",
            conn, params=(row.ticker,),
        ).reset_index(drop=True)

        idx_matches = ohlcv.index[ohlcv["date"] == row.date]
        if len(idx_matches) == 0:
            print(f"!!  {row.ticker} {row.date}: date not found in ohlcv at all")
            mismatches += 1
            continue

        t = idx_matches[0]
        if t + 5 >= len(ohlcv):
            print(f"!!  {row.ticker} {row.date}: no row 5 sessions ahead in ohlcv "
                  f"(t={t}, len={len(ohlcv)}) — this row shouldn't have a "
                  f"target/prediction at all")
            mismatches += 1
            continue

        close = ohlcv["close"]
        close_t = float(close.iloc[t])
        close_t5 = float(close.iloc[t + 5])
        recomputed_actual = np.log(close_t5 / close_t)

        actual_diff = abs(recomputed_actual - row.actual)
        if actual_diff > TOLERANCE:
            print(f"!!  {row.ticker} {row.date}: ACTUAL MISMATCH — "
                  f"stored={row.actual}, recomputed={recomputed_actual} "
                  f"(diff={actual_diff}) — possible join/alignment bug")
            mismatches += 1
            continue

        # Zero-crossing rule: actual == 0 is always a miss, regardless of predicted sign
        if recomputed_actual == 0:
            expected_hit = 0
        else:
            expected_hit = int(np.sign(row.predicted) == np.sign(recomputed_actual))

        if int(row.hit) != expected_hit:
            print(f"!!  {row.ticker} {row.date}: HIT MISMATCH — "
                  f"stored hit={row.hit}, expected={expected_hit} "
                  f"(predicted={row.predicted}, actual={recomputed_actual})")
            mismatches += 1
            continue

        print(f"OK  {row.ticker} {row.date} (fold {row.fold}): "
              f"actual matches independent recomputation, hit correctly derived")

    print(f"\n{SAMPLE_SIZE - mismatches}/{SAMPLE_SIZE} rows fully consistent")
    conn.close()
