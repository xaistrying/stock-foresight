"""
Reproduce the sample-size figures `debate-outcome-log` relies on (design
Decision 12, tasks 6.1-6.2), from `backend/data/app.db` opened READ-ONLY.

  (a) mean pairwise correlation of daily log returns over the modelling
      universe and the effective breadth `n / (1 + (n-1) * rho`, to compare
      with Finding 9 of docs/DISCUSSION_model_direction.md (3.2 of 203);
  (b) random daily 25-ticker baskets over the last 250 sessions before the data
      ends. Stand-ins for the debate: the technical vote's hit-rate (the
      technical agent's own RSI / MACD histogram / Tenkan-Kijun vote) and a
      trailing-volatility band hit (|r5| <= sqrt(5) * rv20). For each, the
      block-bootstrap half-width and implied effective n at block lengths 5,
      20 and 60 sessions, over several seeds;
  (c) the review's planning arithmetic, 1.96 * sqrt(0.25 / 150).

Writes nothing. DATABASE-DEPENDENT. Run from the project root:
    backend/.venv/bin/python backend/scripts/verify_log_sample_size.py
"""

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
from app.db.connection import DB_PATH, open_readonly  # noqa: E402
from app.services.debate.technical import _compute_stance_from_indicators  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


momentum = _load("evaluate_cross_sectional_momentum")  # compute_rho_bar, effective_breadth
scorer = _load("score_debates")  # wilson, block_bootstrap

SESSIONS = 250
BASKET = 25
SEEDS = (0, 1, 2, 3, 4)
BLOCK_LENGTHS = (5, 20, 60)
HORIZON = 5  # Rule 1
RV_WINDOW = 20
MIN_BLOCKS_HERE = 4  # 250 sessions give only 4 blocks of 60; shown, flagged as thin
REVIEW_N_EFFECTIVE = 150  # the review's "about 150 effective observations a year"


def part_a(conn) -> None:
    universe = momentum.load_universe(conn)
    closes = momentum.load_close_history(universe, conn)
    rho = momentum.compute_rho_bar(closes)
    breadth = momentum.effective_breadth(rho["symbols_used"], rho["rho_bar"])
    print("(a) Effective breadth of daily log returns")
    print(f"    {rho['symbols_used']} symbols, rho_bar {rho['rho_bar']:.3f}, effective breadth {breadth:.1f} "
          f"(Finding 9: 0.310 and 3.2 of 203)")
    return closes


def wide_closes(closes: pd.DataFrame) -> pd.DataFrame:
    """date x ticker closes. Built by hand: DataFrame.pivot / unstack returned an index with
    14 distinct labels for 2522 dates on Python 3.14.6 + NumPy 2.2.6 (values intact, labels
    wrong), while factorize is right. Asserted rather than trusted."""
    rows, dates = pd.factorize(closes["date"], sort=True)
    cols, tickers = pd.factorize(closes["ticker"], sort=True)
    grid = np.full((len(dates), len(tickers)), np.nan)
    grid[rows, cols] = closes["close"].to_numpy()
    wide = pd.DataFrame(grid, index=dates, columns=tickers)
    assert wide.index.is_unique and wide.index.is_monotonic_increasing, "date index is corrupt"
    return wide


def stand_ins(conn, closes: pd.DataFrame):
    """Wide frames (date x ticker) of vote hits and band hits; NaN where there is no call/outcome."""
    wide = wide_closes(closes)
    wide = wide.where(wide > 0)
    log_ret = np.log(wide / wide.shift(1))
    rv20 = log_ret.rolling(RV_WINDOW).std()
    r5 = np.log(wide.shift(-HORIZON) / wide)  # the fifth MARKET session: NaN across a gap
    dates = list(wide.index[-(SESSIONS + HORIZON):-HORIZON])  # last 250 as_of dates with an outcome

    marks = ", ".join("?" for _ in dates)
    features = pd.read_sql_query(
        "SELECT ticker, date, rsi, macd_histogram, tenkan_sen, kijun_sen FROM features "
        f"WHERE date IN ({marks})", conn, params=dates,
    )
    vote = pd.DataFrame(np.nan, index=dates, columns=wide.columns)
    for row in features.to_dict("records"):
        if row["ticker"] not in vote.columns:
            continue
        stance, _, _ = _compute_stance_from_indicators(row)
        move = r5.at[row["date"], row["ticker"]]
        if stance != "neutral" and not np.isnan(move):
            vote.at[row["date"], row["ticker"]] = float(move > 0 if stance == "bull" else move < 0)
    band_limit = rv20.loc[dates].mul(math.sqrt(HORIZON))
    band = (r5.loc[dates].abs() <= band_limit).astype(float).where(r5.loc[dates].notna() & band_limit.notna())
    return dates, wide.index, vote, band


def basket_series(frame: pd.DataFrame, calendar_index: dict, seed: int):
    """Hits of a random 25-ticker basket per date, with each row's calendar position."""
    rng = np.random.default_rng(seed)
    hits, positions = [], []
    for date, row in frame.iterrows():
        valid = row.dropna()
        if len(valid) < BASKET:
            continue
        chosen = rng.choice(valid.index.to_numpy(), size=BASKET, replace=False)
        hits += [int(valid[t]) for t in chosen]
        positions += [calendar_index[date]] * BASKET
    return hits, positions


def part_b(conn, closes: pd.DataFrame) -> None:
    dates, calendar, vote, band = stand_ins(conn, closes)
    calendar_index = {d: i for i, d in enumerate(calendar)}
    print(f"\n(b) Random {BASKET}-ticker daily baskets, last {len(dates)} sessions "
          f"({dates[0]} to {dates[-1]}), seeds {SEEDS}")
    for name, frame in (("technical vote hit-rate", vote), ("volatility-band hit", band)):
        print(f"  {name}")
        for length in BLOCK_LENGTHS:
            halves, effective, rates, naive = [], [], [], []
            for seed in SEEDS:
                hits, positions = basket_series(frame, calendar_index, seed)
                boot = scorer.block_bootstrap(hits, [p // length for p in positions], min_blocks=MIN_BLOCKS_HERE)
                low, high = scorer.wilson(sum(hits), len(hits))
                rates.append(sum(hits) / len(hits))
                naive.append((high - low) / 2)
                if boot:
                    halves.append(boot[0])
                    effective.append(boot[1])
            blocks = len({p // length for p in positions})
            if halves:
                note = " (thin: under 8 blocks)" if blocks < scorer.MIN_BLOCKS else ""
                print(f"    blocks of {length:>2}: {blocks} blocks{note}; rate {np.mean(rates) * 100:.1f}%; "
                      f"clustered half-width {np.mean(halves) * 100:.1f} points "
                      f"(range {min(halves) * 100:.1f} to {max(halves) * 100:.1f}); "
                      f"implied effective n {np.mean(effective):.0f}; naive Wilson half-width "
                      f"{np.mean(naive) * 100:.1f} points; n rows {len(hits)}")
            else:
                print(f"    blocks of {length:>2}: not estimable ({blocks} blocks)")


def part_c() -> None:
    half = scorer.Z_95 * math.sqrt(0.25 / REVIEW_N_EFFECTIVE)
    print(f"\n(c) The review's planning arithmetic: 1.96 * sqrt(0.25 / {REVIEW_N_EFFECTIVE}) = "
          f"{half:.3f} ({half * 100:.1f} points)")


def main() -> int:
    if not DB_PATH.exists():
        print(f"FAIL: no database at {DB_PATH}")
        return 1
    conn = open_readonly(DB_PATH)
    try:
        closes = part_a(conn)
        part_b(conn, closes)
    finally:
        conn.close()
    part_c()
    return 0


if __name__ == "__main__":
    sys.exit(main())
