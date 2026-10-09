"""Do Fibonacci levels hold more often than nearby non-Fibonacci levels?

READ-ONLY over `backend/data/app.db`: writes no table and no model file.

Per ticker and per scale m, a causal zigzag (a reversal of m x the trailing 60-session daily sigma
confirms a pivot) gives the leg that just ended. Its retracement and extension levels that price has
not yet reached are followed for TOUCH_SESSIONS. At the first touch, within POST_SESSIONS after it,
does the close move b = daily sigma x sqrt(5) back to the side price came from (HOLD) before b through
the level (BREAK)? Closes only, so there is no intrabar-order ambiguity.

Fibonacci ratios are compared with a dense grid of non-Fibonacci ratios: each ratio's hold rate minus the
mean hold rate of non-Fibonacci ratios 0.03-0.10 away from it (its excess). The p-value is the share of
random same-size sets of non-Fibonacci ratios whose mean excess is at least the Fibonacci set's. Results
are split at SPLIT_DATE so a scale chosen on the early period is checked on the late one.

Result (2026-10-08, 208 modelling-universe tickers, 1,598 ticker-years): no scale stands out. Excess hold
rates are within about +-2 points and change sign between periods; 2 of 20 testable cells reach one-sided
p < 0.05 (about 1 is expected by chance), both late-period extensions, and neither replicates in the
early period. Scales of 16 x sigma and more have too few legs to test. Fibonacci levels are therefore
shown, if at all, as descriptive reference levels with no reliability figure (Rule 4).

Every threshold below that Rules 1-6 do not cover is provisional.

Run from the project root:
    python backend/scripts/evaluate_fibonacci_levels.py [--tickers N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db.connection import DB_PATH, open_readonly  # noqa: E402

SCALES = (2, 3, 4, 6, 8, 12, 16, 24)  # zigzag reversal, in daily sigmas
SPLIT_DATE = "2023-01-01"  # legs confirmed before it are "early"
SIGMA_WINDOW = 60  # sessions of daily log returns behind sigma
TOUCH_SESSIONS = 20  # how long a level is followed after its leg is confirmed
POST_SESSIONS = 10  # how long after the touch hold-or-break is decided
HORIZON_SESSIONS = 5  # Rule 1: b is one typical 5-session move
MIN_HISTORY_SESSIONS = 300
MIN_EVENTS_PER_RATIO = 100  # below this mean count a cell is not reported
NEAR_FIB = 0.03  # non-Fibonacci ratios must be at least this far from every Fibonacci one
BASELINE_NEAR, BASELINE_FAR = 0.03, 0.10  # neighbours used for a ratio's local baseline
NULL_DRAWS = 5000
SEED = 0

FIB_RETRACEMENT = (0.236, 0.382, 0.5, 0.618, 0.786)
FIB_EXTENSION = (1.272, 1.618, 2.0, 2.618)
# The placebo grid; the Fibonacci ratios are appended so they are columns of the same matrix.
RETRACEMENT = np.concatenate([np.round(np.arange(0.20, 0.901, 0.01), 3), FIB_RETRACEMENT])
EXTENSION = np.concatenate([np.round(np.arange(1.10, 2.701, 0.01), 3), FIB_EXTENSION])
KINDS = (("ret", RETRACEMENT, FIB_RETRACEMENT), ("ext", EXTENSION, FIB_EXTENSION))


def zigzag(high: np.ndarray, low: np.ndarray, sigma: np.ndarray, m: float) -> list[tuple[int, float, str, int]]:
    """Causal pivots as (pivot_bar, price, "H"|"L", confirm_bar).

    A pivot is confirmed on the first bar whose extreme lies `m * sigma[bar]` (as a fraction of price)
    beyond the running extreme, so `confirm_bar > pivot_bar` always and nothing after it is used.
    """
    pivots: list[tuple[int, float, str, int]] = []
    hi = lo = 0
    trend = 0
    for i in range(1, len(high)):
        if not np.isfinite(sigma[i]):
            hi = lo = i
            continue
        threshold = m * sigma[i]
        if high[i] > high[hi]:
            hi = i
        if low[i] < low[lo]:
            lo = i
        if trend >= 0 and hi != i and low[i] <= high[hi] * (1 - threshold):
            pivots.append((hi, high[hi], "H", i))
            trend, hi, lo = -1, i, i
        elif trend <= 0 and lo != i and high[i] >= low[lo] * (1 + threshold):
            pivots.append((lo, low[lo], "L", i))
            trend, hi, lo = 1, i, i
    return pivots


def evaluate_leg(
    confirm: int,
    start: float,
    end: float,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    sigma: float,
    ratios: np.ndarray,
    kind: str,
) -> tuple[np.ndarray, np.ndarray]:
    """(valid, hold) per ratio for the leg start -> end confirmed at bar `confirm`.

    A retracement level counts only if price has not already passed it; an extension level always
    lies beyond the leg's end. `valid`: touched within TOUCH_SESSIONS and decided within POST_SESSIONS.
    """
    leg = end - start
    if kind == "ret":
        levels = end - ratios * leg
        ahead = levels < close[confirm] if leg > 0 else levels > close[confirm]
        levels = np.where(ahead, levels, np.nan)
    else:
        levels = start + ratios * leg
    usable = np.where(np.isfinite(levels) & (levels > 0))[0]
    valid = np.zeros(len(ratios), bool)
    hold = np.zeros(len(ratios), bool)
    if len(usable) == 0:
        return valid, hold

    lv = levels[usable]
    above = lv > close[confirm]  # approached from below
    after = slice(confirm + 1, confirm + 1 + TOUCH_SESSIONS)
    touched = np.where(above[:, None], high[after][None, :] >= lv[:, None], low[after][None, :] <= lv[:, None])
    first_touch = touched.argmax(1)
    post = confirm + 2 + first_touch[:, None] + np.arange(POST_SESSIONS)[None, :]
    # Moves toward the side price came from are positive.
    away = -np.where(above, 1.0, -1.0)[:, None] * np.log(close[post] / lv[:, None])
    decided = np.abs(away) >= sigma * np.sqrt(HORIZON_SESSIONS)
    first_decided = decided.argmax(1)
    held = away[np.arange(len(usable)), first_decided] > 0
    ok = touched.any(1) & decided.any(1)
    valid[usable], hold[usable] = ok, ok & held
    return valid, hold


def collect(conn, symbols: list[str]) -> tuple[dict, dict, float]:
    """Counts of valid and held events per (scale, kind, period, ratio), and leg sizes per scale."""
    counts = {m: {(k, p): [np.zeros(len(r)), np.zeros(len(r))] for k, r, _ in KINDS for p in ("early", "late")} for m in SCALES}
    legs: dict[int, list[float]] = {m: [] for m in SCALES}
    years = 0.0
    last_leg_session = TOUCH_SESSIONS + POST_SESSIONS + 2
    for symbol in symbols:
        frame = pd.read_sql(
            "SELECT date, high, low, close FROM ohlcv WHERE ticker = ? AND high > 0 AND low > 0 AND close > 0 ORDER BY date",
            conn,
            params=(symbol,),
        )
        if len(frame) < MIN_HISTORY_SESSIONS:
            continue
        years += len(frame) / 250
        high, low, close = (frame[c].to_numpy(float) for c in ("high", "low", "close"))
        dates = frame["date"].to_numpy()
        sigma = pd.Series(np.log(close)).diff().rolling(SIGMA_WINDOW).std().to_numpy()
        for m in SCALES:
            pivots = zigzag(high, low, sigma, m)
            for (_, start, _, _), (_, end, _, confirm) in zip(pivots[:-1], pivots[1:]):
                if confirm + last_leg_session >= len(close):
                    continue  # its outcome window runs past the data
                period = "early" if dates[confirm] < SPLIT_DATE else "late"
                legs[m].append(abs(end / start - 1) * 100)
                for kind, ratios, _ in KINDS:
                    valid, hold = evaluate_leg(confirm, start, end, close, high, low, sigma[confirm], ratios, kind)
                    counts[m][(kind, period)][0] += valid
                    counts[m][(kind, period)][1] += hold
    return counts, legs, years


def excess_over_baseline(valid: np.ndarray, held: np.ndarray, ratios: np.ndarray, fib: tuple, rng) -> dict:
    """Mean excess hold rate of the Fibonacci ratios, its placebo p-values and context.

    Returns an empty-result dict (`reported` False) when the events are too few to say anything.
    """
    fib_at = [int(np.where(np.isclose(ratios, f))[0][-1]) for f in fib]
    near_fib = np.abs(ratios[:, None] - np.array(fib)[None, :]).min(1) < NEAR_FIB
    rate = np.where(valid > 0, held / np.maximum(valid, 1), np.nan)
    excess = np.full(len(ratios), np.nan)
    for i, ratio in enumerate(ratios):
        distance = np.abs(ratios - ratio)
        neighbours = ~near_fib & (distance >= BASELINE_NEAR) & (distance <= BASELINE_FAR) & np.isfinite(rate)
        if neighbours.sum() >= 4 and np.isfinite(rate[i]):
            excess[i] = rate[i] - rate[neighbours].mean()
    placebo = np.where(~near_fib & np.isfinite(excess))[0]
    events = float(valid[fib_at].mean())
    if events < MIN_EVENTS_PER_RATIO or len(placebo) < 20 or np.isnan(excess[fib_at]).any():
        return {"reported": False, "events": events}
    observed = float(excess[fib_at].mean())
    null = np.array([excess[rng.choice(placebo, len(fib), replace=False)].mean() for _ in range(NULL_DRAWS)])
    return {
        "reported": True,
        "events": events,
        "excess_pp": observed * 100,
        "p_higher": float((null >= observed).mean()),
        "p_either": float((np.abs(null) >= abs(observed)).mean()),
        "baseline_hold_pct": float(held[~near_fib].sum() / max(valid[~near_fib].sum(), 1) * 100),
    }


def _cell(result: dict) -> str:
    if not result["reported"]:
        return f"too few events ({result['events']:.0f}/ratio)"
    return f"{result['excess_pp']:+6.2f} pp  p>={result['p_higher']:.3f}  p~{result['p_either']:.3f}"


def report(counts: dict, legs: dict, years: float, n_tickers: int) -> None:
    rng = np.random.default_rng(SEED)
    print(f"tickers={n_tickers}  ticker-years={years:.0f}  early/late split={SPLIT_DATE}")
    print("\nscale (x daily sigma): legs per ticker-year, median leg size")
    for m in SCALES:
        print(f"  {m:>2}: {len(legs[m]) / years:5.1f}   {np.median(legs[m]) if legs[m] else float('nan'):5.1f}%")
    print("\nexcess hold rate of Fibonacci ratios over a local non-Fibonacci baseline;")
    print("p>= : share of random non-Fibonacci sets at least as high, p~ : at least as far from zero")
    for kind, ratios, fib in KINDS:
        print(f"\n=== {'retracement' if kind == 'ret' else 'extension'} levels ===")
        for m in SCALES:
            cells = [_cell(excess_over_baseline(*counts[m][(kind, period)], ratios, fib, rng)) for period in ("early", "late")]
            print(f"  {m:>2} | early {cells[0]:<44} | late {cells[1]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tickers", type=int, default=None, help="only the first N tickers (a quick look)")
    args = parser.parse_args()
    with open_readonly(DB_PATH) as conn:
        symbols = [
            row[0]
            for row in conn.execute(
                "SELECT symbol FROM ticker_universe WHERE ingestion_state = 'ok' AND fails_liquidity_filter = 0 "
                "AND below_minimum_history = 0 ORDER BY symbol"
            )
        ][: args.tickers]
        counts, legs, years = collect(conn, symbols)
    report(counts, legs, years, len(symbols))


if __name__ == "__main__":
    main()
