"""
Reproduce the figures `retire-direction-model` relies on (design.md Context):
the `GET /tickers` catalog size, the page-load request count it implies, the
`backtest_predictions` rows nothing may touch, and which files import xgboost.

READ-ONLY: the database is opened `mode=ro`; nothing is written.

Exit status is non-zero when a figure differs from its expected value. The
defaults are the pre-change expectations (commit e77986e); re-run after the
change with the post-change ones:

    python backend/scripts/verify_retirement_claims.py
    python backend/scripts/verify_retirement_claims.py --expect-xgboost-files none

Run from the project root.
"""

import argparse
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.api.tickers import CATALOG_UNIVERSE_ROWS  # noqa: E402
from app.db.connection import DB_PATH, open_readonly  # noqa: E402
from app.ml.training import TRAINING_TICKERS  # noqa: E402
from app.services.ticker_universe import INGESTION_STATE_OK  # noqa: E402

REQUESTS_PER_CHIP = 3  # /prediction, /history, /insight, before this change
XGBOOST_IMPORT = re.compile(r"^\s*(?:import|from)\s+xgboost\b", re.MULTILINE)
SKIPPED_DIRS = {".venv", "__pycache__", "node_modules"}
EXPECTED_XGBOOST_FILES = (
    "app/api/insight.py",
    "app/api/predictions.py",
    "app/main.py",
    "app/ml/backtest.py",
    "app/ml/training.py",
    "scripts/baseline_model_diagnostics.py",
    "tests/test_training.py",
)


def xgboost_importers() -> list[str]:
    found = []
    for path in sorted(BACKEND.rglob("*.py")):
        if SKIPPED_DIRS & set(path.parts):
            continue
        if XGBOOST_IMPORT.search(path.read_text(encoding="utf-8")):
            found.append(path.relative_to(BACKEND).as_posix())
    return found


def catalog_figures(conn) -> dict:
    universe = {row[0] for row in conn.execute(CATALOG_UNIVERSE_ROWS, (INGESTION_STATE_OK,))}
    catalog = universe | set(TRAINING_TICKERS)
    loaded = {row[0]: row[1] for row in conn.execute("SELECT ticker, features_computed FROM tickers")}
    return {
        "catalog": len(catalog),
        "loaded": len(catalog & loaded.keys()),
        "features_failed": sum(1 for symbol in catalog if loaded.get(symbol) == 0),
    }


def backtest_figures(conn) -> dict:
    rows, tickers, last_date = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT ticker), MAX(date) FROM backtest_predictions"
    ).fetchone()
    return {"rows": rows, "tickers": tickers, "last_date": last_date}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--expect-catalog", type=int, default=208)
    parser.add_argument("--expect-rows", type=int, default=10191)
    parser.add_argument(
        "--expect-xgboost-files",
        default=",".join(EXPECTED_XGBOOST_FILES),
        help="comma-separated backend-relative paths, or 'none'",
    )
    args = parser.parse_args()

    conn = open_readonly(DB_PATH)
    try:
        catalog = catalog_figures(conn)
        backtest = backtest_figures(conn)
    finally:
        conn.close()
    importers = xgboost_importers()
    expected_importers = [] if args.expect_xgboost_files == "none" else sorted(args.expect_xgboost_files.split(","))

    print(f"GET /tickers catalog entries: {catalog['catalog']} (expected {args.expect_catalog})")
    print(f"  loaded: {catalog['loaded']}, features_computed = 0: {catalog['features_failed']}")
    print(f"page-load requests derived from the old per-chip prefetch: 1 + {REQUESTS_PER_CHIP} x {catalog['catalog']} = "
          f"{1 + REQUESTS_PER_CHIP * catalog['catalog']}")
    print(f"backtest_predictions: {backtest['rows']} rows (expected {args.expect_rows}), "
          f"{backtest['tickers']} tickers, max date {backtest['last_date']}")
    print(f"files importing xgboost: {importers or 'none'}")

    problems = []
    if catalog["catalog"] != args.expect_catalog:
        problems.append("catalog size differs")
    if backtest["rows"] != args.expect_rows:
        problems.append("backtest_predictions row count differs")
    if importers != expected_importers:
        problems.append(f"xgboost importers differ from {expected_importers or 'none'}")
    for problem in problems:
        print(f"MISMATCH: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
