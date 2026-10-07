"""
Reproduce the figures and stale-doc claims behind `align-rules-and-disclaimer`
(`docs/DISCUSSION_post_pivot_review.md`, Findings 6 and 7).

PART A (default): prints the `backtest_predictions` / `ohlcv` figures that
design Decision 4 relies on ("Confidence cannot be shown for most tickers"),
next to the numbers the 2026-10-06 review reported. A mismatch is printed, not
edited away: report it to the owner.

PART B (`--docs --expect present|absent`): checks the stale-claim table of
design Decision 12 as (file, regex) pairs. Run `--expect present` before the
doc edits (each claim must still be there, so the edit is needed) and
`--expect absent` after (none may remain). Claims already removed by the rule
rewrite itself (`CLAUDE.md` "created M6, not before") and appended updates
(the outcome-tracking discussion, new MODEL_CARD sections) are not tracked here.

READ-ONLY: the database is opened `mode=ro`; nothing is written; no randomness.

Run from the project root:
    python backend/scripts/verify_rules_alignment_claims.py
    python backend/scripts/verify_rules_alignment_claims.py --docs --expect present
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "backend" / "data" / "app.db"

# (label, query, value reported by the 2026-10-06 review)
FIGURES = (
    ("backtest_predictions rows", "SELECT COUNT(*) FROM backtest_predictions", 10191),
    ("backtest_predictions distinct tickers", "SELECT COUNT(DISTINCT ticker) FROM backtest_predictions", 10),
    ("backtest_predictions last date", "SELECT MAX(date) FROM backtest_predictions", "2026-08-05"),
    ("pooled hit-rate", "SELECT ROUND(AVG(hit), 3) FROM backtest_predictions", 0.477),
    ("ohlcv distinct tickers", "SELECT COUNT(DISTINCT ticker) FROM ohlcv", 599),
    (
        "ohlcv tickers with no backtest row",
        "SELECT COUNT(DISTINCT ticker) FROM ohlcv WHERE ticker NOT IN (SELECT ticker FROM backtest_predictions)",
        589,
    ),
)

# Decision 12: claims that are stale at HEAD e77986e and must be gone after group 5.5 / 6.
STALE_CLAIMS = (
    ("openspec/config.yaml", r"AI insight\s+panel \(Confidence, Market Sentiment, Advice\)"),
    ("openspec/config.yaml", r"single XGBoost\s+regressor"),
    ("openspec/config.yaml", r"DATA_DICTIONARY\.md doesn't exist yet"),
    ("openspec/config.yaml", r"DISCLAIMER\.md doesn't exist yet"),
    ("openspec/config.yaml", r"not the stubbed contract below"),
    ("openspec/config.yaml", r"Current focus: no active milestone"),
    ("openspec/config.yaml", r"single most consequential open item"),
    ("openspec/config.yaml", r"Confidence \(rule 4\) is\s+backtest-only"),
    ("openspec/config.yaml", r"M8 - Real news-based sentiment - idea only, not discussed, not\s+started"),
    ("openspec/config.yaml", r"Any task that renders Confidence, Sentiment, or Advice"),
    ("CLAUDE.md", r"AI insight panel response contract"),
    ("docs/MODEL_CARD.md", r"openspec/changes/xgboost-training-pipeline/"),
    ("docs/DISCUSSION_model_direction.md", r"still serving predictions"),
    ("docs/DISCUSSION_calendar_staleness.md", r"openspec/changes/ticker-manual-refresh/"),
    ("docs/DISCUSSION_calendar_staleness.md", r"still active/unarchived"),
    (
        "docs/DATA_DICTIONARY.md",
        r"openspec/changes/(data-ingestion-vnstock|feature-engineering-ta|hose-universe-ingestion)/",
    ),
)


def part_a() -> int:
    if not DB_PATH.exists():
        print(f"no database at {DB_PATH}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        mismatches = 0
        print(f"{'figure':42} {'measured':>12} {'review':>12}")
        for label, query, reported in FIGURES:
            measured = conn.execute(query).fetchone()[0]
            flag = "" if measured == reported else "  <- differs"
            mismatches += measured != reported
            print(f"{label:42} {measured!s:>12} {reported!s:>12}{flag}")
    finally:
        conn.close()
    print(f"\n{mismatches} figure(s) differ from the review (report them to the owner, do not edit them away)")
    return 0


def part_b(expect: str) -> int:
    wrong = 0
    for rel_path, pattern in STALE_CLAIMS:
        found = re.search(pattern, (ROOT / rel_path).read_text(encoding="utf-8")) is not None
        ok = found == (expect == "present")
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'} {rel_path}: {'present' if found else 'absent'}  /{pattern}/")
    print(f"\n{wrong} claim(s) not {expect}")
    return 1 if wrong else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--docs", action="store_true", help="Part B: check the stale-claim table")
    parser.add_argument("--expect", choices=("present", "absent"), default="present")
    args = parser.parse_args()
    return part_b(args.expect) if args.docs else part_a()


if __name__ == "__main__":
    sys.exit(main())
