"""
Build (or refresh) the ticker universe from the exchange listing
(hose-universe-ingestion, task group 2 / design Migration Plan step 2).

The 634 rows currently in `ticker_universe` were produced by calling
`construct_universe` ad hoc. This script exists so that is repeatable — after
the batch ingest, when a new symbol lists, or on a fresh database — the same
way `backfill_loaded_tickers.py` made the backfill repeatable.

NETWORK-BOUND (one listing call) and WRITING to `ticker_universe`. It touches
only the listing-sourced columns: exchange, `icb_code2`, listing status. The
observed session ranges, quality measurements, filter flags and ingestion
state are owned by ingestion and survive a re-run, so re-running this does
not undo an ingest.

Fetches no OHLCV — verifiable on its own, which is the point of it being its
own migration step.

Run from the project root:
    python backend/scripts/construct_universe.py [--dry-run]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db.connection import init_db  # noqa: E402
from app.services.ticker_universe import (  # noqa: E402
    UniverseConstructionError,
    build_universe_entries,
    construct_universe,
    fetch_listing,
)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


def _current_counts() -> dict:
    if not DB_PATH.exists():
        return {}
    conn = sqlite3.connect(DB_PATH)
    try:
        return {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT listing_status, COUNT(*) FROM ticker_universe "
                "GROUP BY listing_status"
            )
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and report what would be persisted, without writing",
    )
    args = parser.parse_args()

    before = _current_counts()
    if before:
        print(f"Universe before: {before}")

    try:
        if args.dry_run:
            entries = build_universe_entries(fetch_listing())
            listed = sum(1 for e in entries if e["listing_status"] == "listed")
            summary = {
                "total": len(entries),
                "listed": listed,
                "delisted": len(entries) - listed,
                "missing_icb_code2": sum(1 for e in entries if e["icb_code2"] is None),
            }
            print("DRY RUN — no writes")
        else:
            # Creates the table on a fresh database, and applies the additive
            # migrations, so this script works as a first step too.
            init_db()
            summary = construct_universe()
    except UniverseConstructionError as exc:
        # The previous universe is left in place: every later step reads it,
        # so a bad listing must not be allowed to shrink it.
        print(f"FAIL: {exc}")
        return 1

    print(f"Universe {'would be' if args.dry_run else ''} constructed: {summary}")
    if not args.dry_run:
        print(f"Universe after:  {_current_counts()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
