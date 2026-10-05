"""Debate report export service.

Writes YYYY-MM-DD_<TICKER>.md to the reports/ directory at the repo root.
Structure is optimised for NotebookLM ingestion (design.md Decision 10).

Rule 6: every exported file ends with the disclaimer unconditionally.
Rule 5: agent labels are "Technical Signal", "News Context", "Macro".
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app.services.debate.engine import AgentPosition, DebateResult

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "reports"

DISCLAIMER = "*Technical observation — not investment advice. See docs/DISCLAIMER.md.*"

AGENT_LABELS = {
    "technical": "Technical Signal",
    "news": "News Context",
    "macro": "Macro",
}

STANCE_ICONS = {
    "bull": "↑",
    "bear": "↓",
    "neutral": "→",
}

VERDICT_DESCRIPTIONS = {
    "STRONG_BUY_SIGNAL": "Strong Buy Signal",
    "BUY_SIGNAL": "Buy Signal",
    "OBSERVE": "Observe",
    "CAUTION_SIGNAL": "Caution Signal",
    "STRONG_CAUTION_SIGNAL": "Strong Caution Signal",
    "SPLIT": "Split (No Consensus)",
}


def _agent_label(agent_id: str) -> str:
    return AGENT_LABELS.get(agent_id, agent_id.capitalize())


def _stance_icon(stance: str) -> str:
    return STANCE_ICONS.get(stance, "→")


def _format_agent_position(pos: AgentPosition, round_label: str) -> str:
    label = _agent_label(pos.agent_id)
    icon = _stance_icon(pos.stance)
    bullets = "\n".join(f"- {r}" for r in pos.reasoning)
    return f"#### {label} ({icon} {pos.stance.capitalize()})\n{bullets}\n"


def export_debate_report(result: DebateResult) -> Path:
    """Serialise a DebateResult to a structured markdown file.

    Returns the Path of the written file.
    Overwrites any existing file for the same ticker+date (re-run replaces).
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    report_date = result.as_of or date.today().isoformat()
    filename = f"{report_date}_{result.ticker}.md"
    output_path = REPORTS_DIR / filename

    lines: list[str] = []

    # ------------------------------------------------------------------ #
    # Title
    # ------------------------------------------------------------------ #
    lines.append(f"# {result.ticker} · {report_date}\n")

    # ------------------------------------------------------------------ #
    # Summary (Level 1 — glanceable)
    # ------------------------------------------------------------------ #
    lines.append("## Summary\n")
    lines.append(f"**Verdict**: {VERDICT_DESCRIPTIONS.get(result.verdict, result.verdict)}")
    if result.agreement_level == "split":
        # Three different stances: there is no group of agreeing agents to count
        # ("Split (0 of 3 agents)" read as if nobody agreed). Same wording as the panel.
        agreement = "Split (3 different positions)"
    else:
        majority = _majority_stance(result.round2)
        n_agree = sum(1 for pos in result.round2.values() if pos.stance == majority)
        agreement = f"{result.agreement_level.capitalize()} ({n_agree} of 3 agents)"
    lines.append(f"**Agreement**: {agreement}")

    stance_row = " · ".join(
        f"{_agent_label(aid)} {_stance_icon(pos.stance)}"
        for aid, pos in result.round2.items()
    )
    lines.append(f"**Agents**: {stance_row}")

    if result.volatility_range_pct is not None:
        lines.append(f"**Volatility range**: ±{result.volatility_range_pct:.2f}% (5 trading sessions)")
    lines.append("")

    # ------------------------------------------------------------------ #
    # Agent Positions table (Level 2)
    # ------------------------------------------------------------------ #
    lines.append("## Agent Positions\n")
    lines.append("| Agent | Stance | Key reasoning |")
    lines.append("|-------|--------|---------------|")
    for aid, pos in result.round2.items():
        label = _agent_label(aid)
        icon = _stance_icon(pos.stance)
        key_reason = pos.reasoning[0] if pos.reasoning else "—"
        lines.append(f"| {label} | {icon} {pos.stance.capitalize()} | {key_reason} |")
    lines.append("")

    # ------------------------------------------------------------------ #
    # Key Tension
    # ------------------------------------------------------------------ #
    lines.append("## Key Tension\n")
    lines.append(result.synthesis.key_tension)
    lines.append("")

    # ------------------------------------------------------------------ #
    # Full Debate (Level 3)
    # ------------------------------------------------------------------ #
    lines.append("## Full Debate\n")

    lines.append("### Round 1 — Initial Positions\n")
    for aid, pos in result.round1.items():
        lines.append(_format_agent_position(pos, "Round 1"))

    lines.append("### Round 2 — Responses\n")
    for aid, pos in result.round2.items():
        lines.append(_format_agent_position(pos, "Round 2"))

    lines.append("### Synthesis\n")
    lines.append(result.synthesis.reasoning)
    lines.append("")

    # ------------------------------------------------------------------ #
    # Disclaimer — Rule 6: unconditional, always last
    # ------------------------------------------------------------------ #
    lines.append("---")
    lines.append(DISCLAIMER)

    content = "\n".join(lines)
    output_path.write_text(content, encoding="utf-8")
    logger.info("Debate report written: %s", output_path)
    return output_path


def _majority_stance(round2: dict) -> str:
    from collections import Counter
    counts = Counter(pos.stance for pos in round2.values())
    return counts.most_common(1)[0][0]
