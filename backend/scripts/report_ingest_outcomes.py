"""
Record what the batch ingest actually produced (hose-universe-ingestion,
task 9.1).

READ-ONLY over `backend/data/app.db`. Reports:

- symbols ingested, by listing status and ingestion state, and every failure
  with its recorded reason
- hard/soft flag counts, and the gate-trigger *rate* against the 0.08%
  measured on the original 15 tickers before the expansion
- **hard flags classified into three categories, not two** — task 9.1 is
  explicit that conflating them would skew Decision 9's reopening trigger:
    * `missed_split`      a persistent level step, like `VHM` 2018-08-14:
                          the close moves and *stays* moved, so every price
                          either side is correct and only the crossing
                          return is spurious
    * `bad_print`         a spike that reverts, where the row's own price is
                          wrong and neutralising the return is not enough
    * `post_halt`         trading resumed after a gap longer than
                          `HALT_GAP_DAYS`, so the daily limit never applied
                          across it (recorded by the gate as its own reason)
    * `invalid_close`     the close is not a positive finite price at all
- liquidity and minimum-history exclusions, and the resulting modelling
  universe size

Run from the project root:
    python backend/scripts/report_ingest_outcomes.py
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.ohlcv_quality_gate import (  # noqa: E402
    FLAG_REASON_INVALID_CLOSE,
    FLAG_REASON_POST_HALT_RESUMPTION,
    STALE_CLOSE_FRACTION_THRESHOLD,
)
from app.services.ticker_universe import MINIMUM_HISTORY_SESSIONS  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

# Measured before the expansion, over the 15 originally-loaded tickers: 25
# flagged rows in ~30,000 sessions. Decision 9 names a rate far above this as
# the trigger to reconsider detect-and-repair.
BASELINE_FLAG_RATE = 0.0008

# A step is "persistent" if the closes over the following few sessions stay
# near the post-step level. Same test as verify_quality_gate.py's, which
# established that VHM 2018-08-14 is a missed split rather than a bad print.
STEP_TOLERANCE = 0.10
STEP_SESSIONS = 3


def classify_hard_flag(closes: pd.DataFrame, session: str) -> str:
    """Which of the three shapes this hard-flagged session is."""
    index = closes.index[closes["date"] == session]
    if len(index) == 0:
        return "unknown"
    position = int(index[0])
    level = float(closes["close"].iloc[position])
    if level <= 0:
        return "invalid_close"
    after = closes["close"].iloc[position : position + 1 + STEP_SESSIONS]
    stays = bool(((after - level).abs() / level < STEP_TOLERANCE).all())
    return "missed_split" if stays else "bad_print"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-failures", action="store_true",
        help="print every failed symbol rather than a count per reason",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"FAIL: no database at {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 20000")
    try:
        universe = pd.read_sql_query("SELECT * FROM ticker_universe", conn)
        flags = pd.read_sql_query("SELECT * FROM ohlcv_quality_flags", conn)
        ohlcv_rows = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
        closes = pd.read_sql_query(
            "SELECT ticker, date, close FROM ohlcv ORDER BY ticker, date", conn
        )
    finally:
        conn.close()

    print("=" * 66)
    print("INGEST OUTCOMES (task 9.1)")
    print("=" * 66)

    ingested = universe[universe["ingestion_state"] == "ok"]
    print(f"\nUniverse:                {len(universe)} symbols")
    print(f"Ingested (state ok):     {len(ingested)}")
    print(f"  listed                 {(ingested['listing_status'] == 'listed').sum()}")
    print(f"  delisted               {(ingested['listing_status'] == 'delisted').sum()}")
    print(f"OHLCV rows stored:       {ohlcv_rows:,}")

    print("\n-- ingestion state --")
    for state, count in universe["ingestion_state"].value_counts().items():
        print(f"  {state:<18} {count}")
    failures = universe[~universe["ingestion_state"].isin(["ok", "pending"])]
    if len(failures) and args.list_failures:
        print("\n  failed symbols:")
        for _, row in failures.sort_values("symbol").iterrows():
            print(f"    {row['symbol']:<8} {row['ingestion_state']:<16} "
                  f"{row['ingestion_last_error'] or ''}")

    print("\n-- quality gate --")
    hard = flags[flags["flag_tier"] == "hard"]
    soft = flags[flags["flag_tier"] == "soft"]
    print(f"  hard flags             {len(hard)} across "
          f"{hard['ticker'].nunique()} symbol(s)")
    print(f"  soft flags             {len(soft)} across "
          f"{soft['ticker'].nunique()} symbol(s)")
    if ohlcv_rows:
        rate = len(flags) / ohlcv_rows
        print(f"  flagged-row rate       {rate:.4%} "
              f"(pre-expansion baseline {BASELINE_FLAG_RATE:.2%} over the "
              f"original 15)")
        print(f"  vs baseline            {rate / BASELINE_FLAG_RATE:.1f}x")

    print("\n-- hard flags by shape (three categories, not two) --")
    by_ticker = {t: g.reset_index(drop=True) for t, g in closes.groupby("ticker")}
    categories: dict[str, list[str]] = {}
    for _, flag in hard.iterrows():
        if flag.get("flag_reason") == FLAG_REASON_INVALID_CLOSE:
            category = "invalid_close"
        elif flag.get("flag_reason") == FLAG_REASON_POST_HALT_RESUMPTION:
            category = "post_halt"
        else:
            frame = by_ticker.get(flag["ticker"])
            category = (
                classify_hard_flag(frame, flag["date"]) if frame is not None
                else "unknown"
            )
        categories.setdefault(category, []).append(f"{flag['ticker']} {flag['date']}")
    for category, entries in sorted(categories.items(), key=lambda kv: -len(kv[1])):
        print(f"  {category:<16} {len(entries):>5}   "
              f"e.g. {', '.join(entries[:3])}")
    if not categories:
        print("  none")

    print("\n  A missed split is a persistent level shift: the return across "
          "it is\n  spurious but every price either side is correct. A bad "
          "print is a spike\n  that reverts — the price itself is wrong. "
          "Decision 9's reopening trigger\n  is the missed-split rate, so "
          "the other categories must not inflate it.")

    print("\n-- filters --")
    # `to_numeric` before `fillna`: these columns come back as object dtype
    # when they hold a mix of NULL and integer, and filling an object column
    # is deprecated.
    liquidity_flag = pd.to_numeric(
        ingested["fails_liquidity_filter"], errors="coerce"
    ).fillna(0)
    history_flag = pd.to_numeric(
        ingested["below_minimum_history"], errors="coerce"
    ).fillna(0)
    liquidity_failures = int(liquidity_flag.sum())
    short_history = int(history_flag.sum())
    print(f"  fails liquidity        {liquidity_failures} of {len(ingested)} "
          f"(threshold {STALE_CLOSE_FRACTION_THRESHOLD})")
    print(f"  below minimum history  {short_history} of {len(ingested)} "
          f"(threshold {MINIMUM_HISTORY_SESSIONS} sessions)")
    excluded = ingested[
        (ingested["fails_liquidity_filter"].fillna(0) == 1)
        | (ingested["below_minimum_history"].fillna(0) == 1)
    ]
    modelling = len(ingested) - len(excluded)
    print(f"  modelling universe     {modelling} of {len(ingested)} ingested "
          f"({modelling / max(len(ingested), 1):.0%})")

    if not ingested["stale_close_fraction"].isna().all():
        stale = ingested["stale_close_fraction"].dropna()
        print("\n  stale-close fraction distribution:")
        for label, value in (
            ("min", stale.min()), ("p25", stale.quantile(0.25)),
            ("median", stale.median()), ("p75", stale.quantile(0.75)),
            ("max", stale.max()),
        ):
            print(f"    {label:<8} {value:.3f}")

    if not ingested["observed_session_count"].isna().all():
        counts = ingested["observed_session_count"].dropna()
        print("\n  observed session-count distribution:")
        for label, value in (
            ("min", counts.min()), ("p10", counts.quantile(0.10)),
            ("median", counts.median()), ("max", counts.max()),
        ):
            print(f"    {label:<8} {int(value)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
