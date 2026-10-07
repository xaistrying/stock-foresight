"""
Probe for the recommendation-wording check of `harden-debate-runtime`
(design.md Decision 9, spec "Recommendation-style wording is withheld").

Shows why a bare word match is useless and what the narrow pattern does:
- NAIVE: how often buy / sell / bought / sold / accumulat* appear in the model
  text of the exported reports in `reports/` (all descriptive, as the reports
  show);
- PATTERN: how many sentences of that same text the recommendation pattern
  flags (expected 0), and how many of the hand-written positive and negative
  samples it gets right (expected: every positive flagged, no negative flagged).

Model text = every line of a report except headings, bold summary lines, table
separators and the final fixed disclaimer. Writes nothing; no network. Run from
the project root:
    backend/.venv/bin/python backend/scripts/probe_advice_language.py

Exit code 1 if the pattern flags a report sentence or misjudges a sample.
"""

import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.debate.prompt_safety import withhold_advice  # noqa: E402  what the engine uses

logging.disable(logging.WARNING)  # the engine logs every withheld sentence; here that is noise

REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"

NAIVE = re.compile(r"\b(?:buy|sell|bought|sold|accumulat\w*)", re.IGNORECASE)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")

POSITIVE = [
    "Investors should consider buying on weakness",
    "We advise investors to sell",
    "Investors should consider selling",
    "Buy the dip",
    "Nên mua cổ phiếu này",
    "You should buy before the earnings release.",
    "It is time to take profit.",
    "I recommend accumulating on dips.",
    "Traders must sell now.",
    "Hãy bán ngay hôm nay",
    "Nên chốt lời ở vùng giá này",
    "Nên cắt lỗ nếu thủng hỗ trợ",
    "Consider buying the stock ahead of results.",
    "Investors ought to go short.",
    "You should **buy** now.",
    "You should buy from the dip.",
    "You should\nbuy",
    "Buy.",
]
NEGATIVE = [
    "the small magnitude suggests the selling pressure is mild",
    "A sell-off in large caps weighed on the index",
    "Selling by foreigners dominates the session",
    "Buy-side demand rose",
    "Áp lực chốt lời gia tăng",
    "Foreign investors net sold 245B VND and sellers hold control",
    "Buyers are in control",
    "an investor accumulating over 11% of the shares",
    "Foreign investors net bought 120B VND",
    "Analysts suggest the rally may be overextended",
    "The index must hold above 1,200 to keep the uptrend intact",
    "Buy orders outnumbered sell orders",
    "RSI at 72 suggests overbought conditions",
    "Selling pressure is mild",
]


def model_text_lines(report: Path) -> list[str]:
    lines = [l.strip() for l in report.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines = lines[:-1]  # the fixed disclaimer, always last
    return [l for l in lines if not l.startswith(("#", "**", "---", "|--"))]


def main() -> int:
    reports = sorted(REPORTS_DIR.glob("*.md")) if REPORTS_DIR.is_dir() else []
    lines = [line for report in reports for line in model_text_lines(report)]
    if reports:
        sentences = [s for line in lines for s in SENTENCE_BREAK.split(line)]
        naive = sum(len(NAIVE.findall(line)) for line in lines)
        flagged = [s for s in sentences if withhold_advice(s) != s]
        print(f"reports: {len(reports)} files, {len(lines)} model-text lines")
        print(f"naive word hits: {naive}")
        print(f"pattern hits:    {len(flagged)}")
        for sentence in flagged:
            print(f"  FLAGGED: {sentence}")
    else:
        print("reports/ is empty or missing: report scan skipped")
        flagged = []

    missed = [s for s in POSITIVE if withhold_advice(s) == s]
    wrong = [s for s in NEGATIVE if withhold_advice(s) != s]
    print(f"positive samples flagged: {len(POSITIVE) - len(missed)}/{len(POSITIVE)}")
    print(f"negative samples flagged: {len(wrong)}/{len(NEGATIVE)} (expected 0)")
    for sample in missed:
        print(f"  MISSED: {sample}")
    for sample in wrong:
        print(f"  FALSE POSITIVE: {sample}")
    return 1 if (flagged or missed or wrong) else 0


if __name__ == "__main__":
    sys.exit(main())
