"""
Backfill universe metadata and quality flags for the already-loaded tickers
(hose-universe-ingestion, task group 5 / design Migration Plan step 4).

The 15 tickers in `tickers` were loaded before the universe table and the
quality gate existed, so their universe rows carry listing data only:
`first_observed_session`, `observed_session_count`, `stale_close_fraction`
and `ingestion_state` are all null or 'pending', and `ohlcv_quality_flags` is
empty. Groups 1-3 left the exclusion machinery wired but inert; this is the
first thing that actually exercises it.

NO RE-FETCHING. Every measurement here is derived from the `ohlcv` rows
already stored, through the same `run_quality_gate` /
`persist_quality_gate_result` / `record_ingestion_result` functions
`load_ticker` calls. That is the point: a backfill that re-fetched would be a
second ingestion path, and would also spend ~15 rate-limited calls to
recompute what is already on disk.

DATABASE-DEPENDENT and WRITING — updates `ticker_universe`, inserts into
`ohlcv_quality_flags`, and (unless --skip-features) rewrites `features` for
each ticker. Run manually, not in CI. `backend/scripts/verify_backfill.py`
checks the result against the known-answer expectations afterwards.

Run from the project root:
    python backend/scripts/backfill_loaded_tickers.py [--dry-run] [--skip-features]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.ml.feature_engineering import (  # noqa: E402
    recompute_features_for_ticker,
)
from app.services.ohlcv_quality_gate import (  # noqa: E402
    persist_quality_gate_result,
    run_quality_gate,
)
from app.services.ticker_universe import (  # noqa: E402
    INGESTION_STATE_OK,
    record_ingestion_result,
    universe_entry,
)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


def loaded_tickers(conn: sqlite3.Connection) -> list[str]:
    """Tickers with a `tickers` row — the "something we have loaded" set that
    design Decision 1 keeps distinct from the universe."""
    return [row[0] for row in conn.execute("SELECT ticker FROM tickers ORDER BY ticker")]


def stored_ohlcv(conn: sqlite3.Connection, ticker: str) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM ohlcv "
        "WHERE ticker = ? ORDER BY date ASC",
        conn,
        params=(ticker,),
    )


def backfill_ticker(conn: sqlite3.Connection, ticker: str, dry_run: bool) -> dict:
    ohlcv = stored_ohlcv(conn, ticker)
    entry = universe_entry(ticker, conn)

    # A backfilled ticker with no universe row would be a universe/listing
    # problem, not a backfill problem — report it rather than inventing a row,
    # for the same reason `record_ingestion_result` refuses to insert one.
    if entry is None:
        return {"ticker": ticker, "rows": len(ohlcv), "in_universe": False}

    result = run_quality_gate(
        ticker,
        ohlcv,
        exchange=entry["exchange"],
        exchange_is_unverified_fallback=bool(
            entry["exchange_is_unverified_fallback"]
        ),
    )
    summary = {
        "ticker": ticker,
        "rows": len(ohlcv),
        "in_universe": True,
        "exchange": entry["exchange"],
        "first": ohlcv["date"].iloc[0] if len(ohlcv) else None,
        "last": ohlcv["date"].iloc[-1] if len(ohlcv) else None,
        "hard": result["hard_flag_count"],
        "soft": result["soft_flag_count"],
        "stale": result["stale_close_fraction"],
        "fails_liquidity": result["fails_liquidity_filter"],
    }
    if dry_run:
        return summary

    persist_quality_gate_result(result)
    record_ingestion_result(
        ticker,
        first_observed_session=summary["first"],
        last_observed_session=summary["last"],
        observed_session_count=len(ohlcv),
        ingestion_state=INGESTION_STATE_OK,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="measure and report without writing anything",
    )
    parser.add_argument(
        "--skip-features",
        action="store_true",
        help="skip the feature recomputation step (task 5.3)",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"FAIL: no database at {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    try:
        tickers = loaded_tickers(conn)
        if not tickers:
            print("FAIL: no rows in `tickers`; nothing to backfill")
            return 1
        print(f"Backfilling {len(tickers)} loaded ticker(s) from stored ohlcv")
        if args.dry_run:
            print("DRY RUN — no writes")
        print()
        summaries = [backfill_ticker(conn, t, args.dry_run) for t in tickers]
    finally:
        conn.close()

    missing = [s["ticker"] for s in summaries if not s["in_universe"]]
    present = [s for s in summaries if s["in_universe"]]

    print(
        f"{'ticker':<8}{'rows':>6}{'first':>13}{'last':>13}"
        f"{'hard':>6}{'soft':>6}{'stale':>9}"
    )
    for s in present:
        print(
            f"{s['ticker']:<8}{s['rows']:>6}{s['first']:>13}{s['last']:>13}"
            f"{s['hard']:>6}{s['soft']:>6}{s['stale']:>9.4f}"
            + ("  FAILS LIQUIDITY" if s["fails_liquidity"] else "")
        )
    print()
    print(f"hard flags:            {sum(s['hard'] for s in present)}")
    print(f"soft flags:            {sum(s['soft'] for s in present)}")
    print(f"stale fractions:       {len(present)}")
    print(f"clean tickers:         {sum(1 for s in present if not s['hard'] and not s['soft'])}")
    print(f"fails liquidity:       {sum(1 for s in present if s['fails_liquidity'])}")
    if missing:
        print(f"NOT IN UNIVERSE:       {', '.join(missing)}")

    if args.dry_run:
        return 0

    if args.skip_features:
        print("\nFeature recomputation skipped (--skip-features).")
        return 0

    # Task 5.3. Recomputed per ticker, from each one's earliest stored row —
    # the flags only take effect through this path, since
    # `recompute_features_for_ticker` is what reads the sidecar back.
    print("\nRecomputing features so the flags take effect:")
    for s in present:
        rows = recompute_features_for_ticker(s["ticker"])
        print(f"  {s['ticker']:<8}{rows:>6} feature rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
