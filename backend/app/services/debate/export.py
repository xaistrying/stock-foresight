"""Debate report export service.

Writes YYYY-MM-DD_<TICKER>.md to the reports/ directory at the repo root.
Structure is optimised for NotebookLM ingestion (design.md Decision 10).

Rule 6: every exported file ends with the full disclaimer unconditionally.
Rule 5: agent labels are "Technical Signal", "News Context", "Macro".
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from app.services.debate.engine import AgentPosition, DebateResult
from app.services.range import coverage_phrase

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "reports"

# Verbatim copy of the "Full disclaimer" in docs/DISCLAIMER.md; a test fails on drift.
DISCLAIMER_FULL = (
    "This analysis shows technical observations, not investment advice. The verdict comes from "
    "three automated agents: one reads price indicators (RSI, MACD, Ichimoku), one reads recent "
    "Vietnamese financial headlines, and one reads market-wide data (VN-Index, USD/VND, foreign "
    "flows). A language model writes the agents' reasoning and revises their positions in a second "
    "round, so wording and positions can be wrong or incomplete. The range is a statistical "
    "estimate of typical 5-session movement, sized so that about 2 in 3 past moves stayed inside "
    "it; larger moves are possible. Nothing here is a recommendation to buy, sell or hold any "
    "security."
)

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

# Display labels are non-transactional (Rule 6); keys are the API enum, which does not change.
VERDICT_DESCRIPTIONS = {
    "STRONG_BUY_SIGNAL": "Strong bullish lean",
    "BUY_SIGNAL": "Bullish lean",
    "OBSERVE": "Observe",
    "CAUTION_SIGNAL": "Bearish lean",
    "STRONG_CAUTION_SIGNAL": "Strong bearish lean",
    "SPLIT": "Split — no consensus",
    "INSUFFICIENT_DATA": "Insufficient data",
}

# Rule 5: same sentence the panel shows above LLM-written text (frontend/src/lib/disclaimer.js).
LM_NOTE = "Reasoning, key tension and synthesis are written by a language model."

# The synthesiser's key-tension call failed or its reply was unusable (blank, too short, a refusal).
KEY_TENSION_UNAVAILABLE = "Key tension unavailable: the synthesiser returned no usable text."


# Plain-language reasons, worded as the panel words them (debate-panel-ui).
DEGRADED_REASON_TEXT = {
    "agent_error": "The agent failed to run.",
    "no_input": "No usable input data.",
    "llm_failed": "The language-model analysis failed.",
    "round2_failed": "Round 2 failed; its Round 1 position is shown but not counted.",
}


def _agent_label(agent_id: str) -> str:
    return AGENT_LABELS.get(agent_id, agent_id.capitalize())


def _stance_icon(stance: str) -> str:
    return STANCE_ICONS.get(stance, "→")


def _range_coverage_note(result: DebateResult) -> str:
    """The parenthetical of the typical-move line: the measured coverage, or that there is none."""
    if result.range_coverage is None:
        return "coverage not established for this stock"
    return f"{coverage_phrase(result.range_coverage)} recent 5-session moves stayed within this range"


def _stance_cell(pos: AgentPosition) -> str:
    """A degraded agent's stance is a placeholder (or a kept Round 1 stance) that
    does not vote: it is never printed as a stance."""
    if pos.degraded_reason is not None:
        return "Unavailable"
    return f"{_stance_icon(pos.stance)} {pos.stance.capitalize()}"


def _format_agent_position(pos: AgentPosition, round_label: str) -> str:
    label = _agent_label(pos.agent_id)
    bullets = "\n".join(f"- {r}" for r in pos.reasoning)
    if pos.degraded_reason is not None:
        reason = DEGRADED_REASON_TEXT.get(pos.degraded_reason, pos.degraded_reason)
        return f"#### {label} (Unavailable — not counted)\n{bullets}\n- {reason}\n"
    return f"#### {label} ({_stance_cell(pos)})\n{bullets}\n"


def _data_age(age: int | None) -> str:
    if age is None:
        return ""
    return " (current)" if age == 0 else f" ({age} session{'s' if age != 1 else ''} old)"


def _agreement(result: DebateResult) -> str:
    """The Agreement text, over live agents only once any is degraded."""
    live = [pos for pos in result.round2.values() if pos.degraded_reason is None]
    unavailable = len(result.round2) - len(live)
    if unavailable == 0:
        if result.agreement_level == "split":
            # Three different stances: there is no group of agreeing agents to count
            # ("Split (0 of 3 agents)" read as if nobody agreed). Same wording as the panel.
            return "Split (3 different positions)"
        n_agree = Counter(pos.stance for pos in live).most_common(1)[0][1]
        return f"{result.agreement_level.capitalize()} ({n_agree} of 3 agents)"
    if result.agreement_level == "split":
        return f"Split ({len(live)} different positions, {unavailable} unavailable)"
    n_agree = Counter(pos.stance for pos in live).most_common(1)[0][1]
    return f"{n_agree} of {len(live)} live agents ({unavailable} unavailable)"


def export_debate_report(result: DebateResult) -> Path | None:
    """Serialise a DebateResult to a structured markdown file.

    Returns the Path of the written file, or None for an INSUFFICIENT_DATA result:
    a refusal is not a report, and its as_of-based filename would overwrite a real
    one. Overwrites any existing file for the same ticker+date (re-run replaces).
    """
    if result.verdict == "INSUFFICIENT_DATA":
        return None
    if not result.as_of:
        # The filename and title are the date of the DATA; never guess it from the clock.
        raise ValueError("cannot export a debate result without as_of")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    report_date = result.as_of
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
    lines.append(f"**Data as of**: {result.data_as_of or report_date}{_data_age(result.data_age_sessions)}")
    lines.append(f"**Agreement**: {_agreement(result)}")

    stance_row = " · ".join(
        f"{_agent_label(aid)} {'Unavailable' if pos.degraded_reason else _stance_icon(pos.stance)}"
        for aid, pos in result.round2.items()
    )
    lines.append(f"**Agents**: {stance_row}")
    if result.agents_degraded:
        unavailable = ", ".join(
            f"{_agent_label(aid)} ({DEGRADED_REASON_TEXT.get(result.round2[aid].degraded_reason, '')})"
            for aid in result.agents_degraded
        )
        lines.append(f"**Unavailable agents**: {unavailable}")

    if result.range_5s_pct is not None:
        lines.append(f"**Typical 5-session move**: ±{result.range_5s_pct:.1f}% ({_range_coverage_note(result)})")
    lines.append("")

    # ------------------------------------------------------------------ #
    # Agent Positions table (Level 2)
    # ------------------------------------------------------------------ #
    lines.append("## Agent Positions\n")
    lines.append(f"{LM_NOTE}\n")
    lines.append("| Agent | Stance | Key reasoning |")
    lines.append("|-------|--------|---------------|")
    for aid, pos in result.round2.items():
        key_reason = pos.reasoning[0] if pos.reasoning else "—"
        if pos.degraded_reason is not None:
            key_reason += " (not counted in the vote)"
        lines.append(f"| {_agent_label(aid)} | {_stance_cell(pos)} | {key_reason} |")
    lines.append("")

    # ------------------------------------------------------------------ #
    # Key Tension
    # ------------------------------------------------------------------ #
    lines.append("## Key Tension\n")
    lines.append(result.synthesis.key_tension or KEY_TENSION_UNAVAILABLE)
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
    lines.append(DISCLAIMER_FULL)

    content = "\n".join(lines)
    output_path.write_text(content, encoding="utf-8")
    logger.info("Debate report written: %s", output_path)
    return output_path

