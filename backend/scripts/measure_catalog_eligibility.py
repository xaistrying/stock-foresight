"""
Times and checks the batched eligibility pass behind `GET /tickers`'s `eligibility`
field (openspec change `dashboard-rail-stage-verdict`, design Decision 3).

Lists the catalog with the SQL of `CATALOG_UNIVERSE_ROWS`, then
- times `assess_eligibility` over the first --sample loaded tickers and extrapolates
  to the whole catalog (the cost of one call per ticker);
- when `assess_eligibility_many` is importable, times it cold and warm for the whole
  catalog and compares every result with `assess_eligibility` at one clock;
- prints counts per reason and per age.

Exits non-zero on any mismatch. Reads only: the database is opened with
`open_readonly` and no write is issued.

DATABASE-DEPENDENT. Run from the project root:
    backend/.venv/bin/python backend/scripts/measure_catalog_eligibility.py [--sample 20]
"""

import argparse
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.tickers import CATALOG_UNIVERSE_ROWS  # noqa: E402
from app.db import connection  # noqa: E402
from app.services import data_eligibility  # noqa: E402
from app.services.ticker_universe import INGESTION_STATE_OK  # noqa: E402


def loaded_catalog_symbols() -> list[str]:
    conn = connection.open_readonly()
    try:
        catalog = [row[0] for row in conn.execute(CATALOG_UNIVERSE_ROWS, (INGESTION_STATE_OK,))]
        loaded = {row[0] for row in conn.execute("SELECT ticker FROM tickers")}
    finally:
        conn.close()
    return [symbol for symbol in catalog if symbol in loaded]


def timed(call):
    started = time.perf_counter()
    result = call()
    return result, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=20)
    args = parser.parse_args()

    # Every read in this script goes through a read-only connection.
    data_eligibility.get_connection = connection.open_readonly
    now = datetime.now(timezone.utc)
    symbols = loaded_catalog_symbols()
    print(f"loaded catalog tickers: {len(symbols)}")

    sample = symbols[: args.sample]
    singles, single_seconds = timed(
        lambda: {s: data_eligibility.assess_eligibility(s, now) for s in sample}
    )
    per_ticker = single_seconds / max(len(sample), 1)
    print(
        f"assess_eligibility x{len(sample)}: {single_seconds:.2f} s "
        f"({per_ticker * 1000:.0f} ms each), about {per_ticker * len(symbols):.1f} s for {len(symbols)}"
    )

    many_fn = getattr(data_eligibility, "assess_eligibility_many", None)
    if many_fn is None:
        print("assess_eligibility_many: not importable yet")
        return 0

    many, cold = timed(lambda: many_fn(symbols, now))
    _, warm = timed(lambda: many_fn(symbols, now))
    print(f"assess_eligibility_many x{len(symbols)}: cold {cold:.2f} s, warm {warm:.2f} s")

    full = {s: data_eligibility.assess_eligibility(s, now) for s in symbols}
    mismatches = [s for s in symbols if many[s] != full[s]]
    print(f"mismatches against assess_eligibility: {len(mismatches)} {mismatches[:10]}")

    reasons = Counter(reason for result in many.values() for reason in result["reasons"])
    ages = Counter(result["age_sessions"] for result in many.values())
    print(f"eligible: {sum(r['eligible'] for r in many.values())} of {len(many)}")
    print(f"reasons: {dict(reasons)}")
    print(f"ages (sessions): {dict(sorted(ages.items(), key=lambda kv: (kv[0] is None, kv[0])))}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
