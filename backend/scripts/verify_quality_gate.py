"""
Verification script for the OHLCV quality gate (hose-universe-ingestion,
task 3.7).

Runs the real gate over the 15 tickers already in `ohlcv` — the known-answer
case the design establishes — and asserts EXACT counts. This is a
known-answer test, not a fixture test: the expected numbers were measured
from this data before the gate existed, so a gate that reproduces them is
being checked against reality rather than against its own assumptions.

Expected result (design.md Decision 3 and Migration Plan step 3):
- `VHM` 2018-08-14 is the only hard-flagged row in the entire dataset.
- 24 rows across `ACB`, `VIB`, and `VND` are soft-flagged and never hard —
  legitimate moves under the wider limit of the exchange each traded on
  before migrating to HOSE.
- The other 11 tickers are entirely clean, at both tiers.

WHY THE DESIGN'S "-69%" IS NOT A PERCENTAGE. The design describes the `VHM`
2018-08-14 row as "approximately -69%". Measured, that session is a -49.87%
*simple* return, whose *log* return is -0.6905. The design's figure is the
log return; both describe the same row. The row itself is a missed 2:1 split
adjustment (60.30 -> 30.23 across all four OHLC fields), not a bad print.

DATABASE-DEPENDENT — reads backend/data/app.db. Writes nothing. Run manually,
not in CI; the unit-level equivalents live in
backend/tests/test_ohlcv_quality_gate.py.

Run from the project root: python backend/scripts/verify_quality_gate.py
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.ohlcv_quality_gate import (  # noqa: E402
    FLAG_TIER_HARD,
    FLAG_TIER_SOFT,
    HARD_GATE_LIMIT,
    PRICE_LIMIT_TOLERANCE,
    log_return_bounds,
    run_quality_gate,
)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

# All 15 currently trade on HOSE, so the soft tier evaluates every one of them
# against HOSE's +/-7% limit — which is what makes the pre-migration rows of
# the three migrated names show up as soft flags.
CURRENT_EXCHANGE = "HSX"

EXPECTED_HARD = {("VHM", "2018-08-14")}
MIGRATED = ("ACB", "VIB", "VND")
EXPECTED_SOFT_TOTAL_MIGRATED = 24
EXPECTED_CLEAN_TICKERS = 11

# The known-answer expectations above hold for exactly these 15 tickers, whose
# flags were established by hand. Once the batch ingest adds hundreds more,
# every check has to stay scoped to this set or the script reports scope drift
# as failure and stops being a usable regression check — which is precisely
# what it is needed for at task 9.1. Newly ingested symbols are still measured
# and printed, just not asserted against.
KNOWN_ANSWER_TICKERS = (
    "ACB", "BID", "CTG", "FPT", "GAS", "HPG", "MSN", "MWG", "PNJ", "SAB",
    "TCB", "VHM", "VIB", "VND", "VNM",
)


def main() -> int:
    if not DB_PATH.exists():
        print(f"!! {DB_PATH} not found — load some tickers first")
        return 2

    conn = sqlite3.connect(DB_PATH)
    try:
        tickers = [r[0] for r in conn.execute("SELECT ticker FROM tickers ORDER BY ticker")]
        histories = {
            ticker: pd.read_sql(
                "SELECT date, close FROM ohlcv WHERE ticker = ? ORDER BY date ASC",
                conn,
                params=(ticker,),
            )
            for ticker in tickers
        }
    finally:
        conn.close()

    lower, upper = log_return_bounds(HARD_GATE_LIMIT)
    print(f"Hard gate: log return outside [{lower:.5f}, {upper:.5f}] "
          f"(limit {HARD_GATE_LIMIT:.0%}, tolerance {PRICE_LIMIT_TOLERANCE})")
    print(f"Soft tier: evaluated against {CURRENT_EXCHANGE}\n")

    results = {
        ticker: run_quality_gate(ticker, df, CURRENT_EXCHANGE)
        for ticker, df in histories.items()
    }

    total_rows = sum(len(df) for df in histories.values())
    hard = {
        (ticker, flag["date"])
        for ticker, result in results.items()
        for flag in result["flags"]
        if flag["flag_tier"] == FLAG_TIER_HARD
    }
    soft_by_ticker = {
        ticker: result["soft_flag_count"] for ticker, result in results.items()
    }
    clean = [t for t, r in results.items() if not r["flags"]]

    header = f"{'ticker':8} {'rows':>6} {'hard':>5} {'soft':>5} {'stale':>7}"
    print(header)
    print("-" * len(header))
    for ticker in tickers:
        r = results[ticker]
        print(f"{ticker:8} {len(histories[ticker]):6} {r['hard_flag_count']:5} "
              f"{r['soft_flag_count']:5} {r['stale_close_fraction']:7.4f}")
    print("-" * len(header))
    flagged = len(hard) + sum(soft_by_ticker.values())
    print(f"{'TOTAL':8} {total_rows:6} {len(hard):5} "
          f"{sum(soft_by_ticker.values()):5}")
    print(f"\nflagged rows: {flagged} / {total_rows} = {flagged / total_rows:.4%}")

    checks = []

    # Every assertion below is scoped to the known-answer set; symbols the
    # batch has since added are measured and printed above, not asserted.
    known = [t for t in tickers if t in KNOWN_ANSWER_TICKERS]
    other = [t for t in tickers if t not in KNOWN_ANSWER_TICKERS]
    if other:
        print(f"\nmeasured but not asserted ({len(other)}): {', '.join(other)}")
    hard_known = {pair for pair in hard if pair[0] in KNOWN_ANSWER_TICKERS}

    checks.append((
        f"hard-flagged rows among the known-answer {len(known)} are exactly "
        f"{sorted(EXPECTED_HARD)}",
        hard_known == EXPECTED_HARD,
        f"got {sorted(hard_known)}",
    ))

    migrated_soft = sum(soft_by_ticker.get(t, 0) for t in MIGRATED)
    checks.append((
        f"soft flags across {'/'.join(MIGRATED)} total {EXPECTED_SOFT_TOTAL_MIGRATED}",
        migrated_soft == EXPECTED_SOFT_TOTAL_MIGRATED,
        f"got {migrated_soft} ("
        + ", ".join(f"{t}={soft_by_ticker.get(t, 0)}" for t in MIGRATED) + ")",
    ))

    migrated_hard = sorted(t for t, _ in hard_known if t in MIGRATED)
    checks.append((
        f"no {'/'.join(MIGRATED)} row is ever hard-flagged",
        migrated_hard == [],
        f"got hard flags for {migrated_hard}",
    ))

    others = [t for t in known if t not in MIGRATED and t != "VHM"]
    dirty_others = {t: results[t]["flags"] for t in others if results[t]["flags"]}
    checks.append((
        f"the other {EXPECTED_CLEAN_TICKERS} tickers are entirely clean",
        len(others) == EXPECTED_CLEAN_TICKERS and not dirty_others,
        f"{len(others)} such tickers, flagged: "
        + (", ".join(f"{t}({len(f)})" for t, f in dirty_others.items()) or "none"),
    ))

    is_step = _is_step_not_spike(histories["VHM"], "2018-08-14")
    checks.append((
        "VHM's own hard-flagged row is a single-session step, not a spike",
        is_step,
        "close stays near its post-jump level (missed split adjustment)"
        if is_step
        else "close reverts after the jump — this is a bad print, and "
             "neutralising the return alone is the wrong repair",
    ))

    print()
    failures = 0
    for description, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {description}")
        if not ok:
            print(f"         {detail}")
            failures += 1
        else:
            print(f"         {detail}")

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{failures} CHECK(S) FAILED'}")
    print(f"clean tickers ({len(clean)}): {', '.join(sorted(clean))}")
    return 1 if failures else 0


def _is_step_not_spike(df: pd.DataFrame, session: str, sessions: int = 3) -> bool:
    """True if the close stays near its post-jump level rather than reverting.

    Distinguishes a missed corporate-action adjustment (a step — the levels on
    each side are self-consistent and only the crossing return is spurious)
    from a bad print (a spike that reverts). Which one it is determines
    whether neutralising the return is the right repair, or whether the row's
    price itself needs replacing.
    """
    index = df.index[df["date"] == session]
    if len(index) == 0:
        return False
    position = int(index[0])
    after = df["close"].iloc[position : position + 1 + sessions]
    level = float(df["close"].iloc[position])
    return bool(((after - level).abs() / level < 0.10).all())


if __name__ == "__main__":
    raise SystemExit(main())
