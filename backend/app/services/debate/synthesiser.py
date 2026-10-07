"""Debate Synthesiser — maps Round 2 stances to a verdict and identifies key tension.

Verdict mapping (design.md Decision 2):
    3/3 bull  → STRONG_BUY_SIGNAL  / unanimous
    2/3 bull  → BUY_SIGNAL         / majority
    3/3 neutral → OBSERVE          / unanimous
    2 neutral + 1 directional → OBSERVE / majority
    1 bull + 1 neutral + 1 bear → SPLIT / split
    2/3 bear  → CAUTION_SIGNAL     / majority
    3/3 bear  → STRONG_CAUTION_SIGNAL / unanimous

A degraded agent (degraded_reason set) never votes. Two live agents agree →
BUY_SIGNAL / CAUTION_SIGNAL / OBSERVE with `majority` (never STRONG_*, never
`unanimous`); two live disagree → SPLIT; fewer than two → INSUFFICIENT_DATA / none
with no LLM call (debate-data-guards, design Decision 4).

Rule 6: prompts and fallback text describe the vote as stance counts, never as a verdict
label (`_vote_summary`); display labels live in export.py and the panel.
"""

from __future__ import annotations

import asyncio
import logging
import re

from app.services.debate.engine import (
    AGENT_ORDER,
    AgentPosition,
    AgreementLevel,
    SynthesisResult,
    Verdict,
)
from app.services.debate.llm_client import LLMClient
from app.services.debate.prompt_safety import DESCRIBE_ONLY, fence, withhold_advice

logger = logging.getLogger(__name__)


def _map_verdict(stances: list[str]) -> tuple[Verdict, AgreementLevel]:
    """Deterministic mapping from three stance strings to verdict + agreement."""
    bulls = stances.count("bull")
    bears = stances.count("bear")
    neutrals = stances.count("neutral")

    if bulls == 3:
        return "STRONG_BUY_SIGNAL", "unanimous"
    if bears == 3:
        return "STRONG_CAUTION_SIGNAL", "unanimous"
    if neutrals == 3:
        return "OBSERVE", "unanimous"

    if bulls == 2:
        return "BUY_SIGNAL", "majority"
    if bears == 2:
        return "CAUTION_SIGNAL", "majority"

    # Remaining cases involve no 2-of-a-kind directional stance
    if neutrals == 2:
        # 2 neutral + 1 directional → OBSERVE (directional insufficient)
        return "OBSERVE", "majority"

    # 1 bull + 1 bear + 1 neutral  OR  any other 1-1-1 split
    return "SPLIT", "split"


_TWO_LIVE_AGREE: dict[str, Verdict] = {
    "bull": "BUY_SIGNAL", "bear": "CAUTION_SIGNAL", "neutral": "OBSERVE",
}


def _vote(stances: list[str]) -> tuple[Verdict, AgreementLevel]:
    """Verdict over the LIVE agents' Round 2 stances (a degraded agent never votes).

    Three live: the existing mapping. Two live: agreement is `majority` at most
    (a strong or unanimous verdict needs three agreeing agents); disagreement is
    a SPLIT. Fewer than two: abstain.
    """
    if len(stances) == 3:
        return _map_verdict(stances)
    if len(stances) == 2:
        first, second = stances
        return (_TWO_LIVE_AGREE[first], "majority") if first == second else ("SPLIT", "split")
    return "INSUFFICIENT_DATA", "none"


_TENSION_PROMPT = """\
You are a financial debate synthesiser. The agents below have analysed the stock
{ticker} and reached the following positions after two rounds of debate (an agent
marked unavailable produced no usable position and is not part of the vote):

{positions}

Vote: {vote}

Write a single paragraph (2-4 sentences) identifying the KEY TENSION in this
debate: the most important disagreement or uncertainty, even if agents agreed.
If there is a dissenting agent, state specifically what they argued and why it
matters. If unanimous, identify the most significant risk the analysis did not
resolve. Be concise and specific. Write in English. {describe_only}
"""

_SYNTHESIS_SUMMARY_PROMPT = """\
You are a financial debate synthesiser. Summarise the overall reasoning that
led to this vote ({vote}) for stock {ticker} in 2-3 sentences. Reference
the key points from the agents that took part (an agent marked unavailable is
not part of the vote). Write in English, concisely. {describe_only}

{positions}
"""

# The agents' stances and bullets, laid out per prompt. They go in fenced: a bullet can quote a
# scraped headline.
_TENSION_POSITIONS = """\
Technical Signal agent (Round 2): {tech_stance}
  Reasoning: {tech_reasoning}

News Context agent (Round 2): {news_stance}
  Reasoning: {news_reasoning}

Macro agent (Round 2): {macro_stance}
  Reasoning: {macro_reasoning}"""

_SUMMARY_POSITIONS = """\
Technical Signal: {tech_stance} — {tech_reasoning}
News Context: {news_stance} — {news_reasoning}
Macro: {macro_stance} — {macro_reasoning}"""

# A reply shorter than this, or opening with a refusal inside the window, is not analysis.
MIN_USABLE_CHARS = 20
REFUSAL_WINDOW_CHARS = 40
_REFUSAL = re.compile(r"\b(?:I can't|I cannot|I'm sorry|I am sorry|I am unable|As an AI)\b", re.IGNORECASE)


def _usable(reply: str | None) -> str | None:
    """The trimmed reply with recommendation wording withheld, or None when it is blank,
    too short or opens with a refusal (it would otherwise be shown as the analysis)."""
    text = (reply or "").strip()
    if len(text) < MIN_USABLE_CHARS:
        return None
    if _REFUSAL.search(text[:REFUSAL_WINDOW_CHARS].replace("\u2019", "'")):  # curly apostrophe
        return None
    return withhold_advice(text, "synthesiser")


def _vote_summary(round2: dict[str, AgentPosition], agreement_level: AgreementLevel | None = None) -> str:
    """The vote as live stance counts, e.g. `2 bullish, 1 neutral, 0 bearish (majority)`.

    Prompts get this instead of the verdict enum so the model cannot echo a label as advice.
    """
    live = [p.stance for p in round2.values() if p.degraded_reason is None]
    counts = f"{live.count('bull')} bullish, {live.count('neutral')} neutral, {live.count('bear')} bearish"
    return f"{counts} ({agreement_level})" if agreement_level else counts


def _agent_fields(round2: dict[str, AgentPosition]) -> dict[str, str]:
    """Prompt placeholders for every agent's Round 2 stance and ALL its bullets
    (slicing to the first two once dropped the signal that decided a vote).
    A degraded agent is named unavailable: its placeholder is not a position."""
    fields: dict[str, str] = {}
    for key, agent_id in (("tech", "technical"), ("news", "news"), ("macro", "macro")):
        pos = round2.get(agent_id)
        if pos is not None and pos.degraded_reason is not None:
            fields[f"{key}_stance"] = "unavailable"
            fields[f"{key}_reasoning"] = "none (this agent produced no usable position)"
        else:
            fields[f"{key}_stance"] = pos.stance if pos else "N/A"
            fields[f"{key}_reasoning"] = "; ".join(pos.reasoning) if pos else "N/A"
    return fields


def _positions(template: str, round2: dict[str, AgentPosition]) -> str:
    return fence("AGENTS", template.format(**_agent_fields(round2)))


class Synthesiser:
    def __init__(self) -> None:
        self._llm = LLMClient()

    async def run(
        self,
        ticker: str,
        round1: dict[str, AgentPosition],
        round2: dict[str, AgentPosition],
    ) -> SynthesisResult:
        # Round 2 stances of live agents decide the verdict
        live = [round2[a].stance for a in AGENT_ORDER if round2[a].degraded_reason is None]
        verdict, agreement_level = _vote(live)
        if verdict == "INSUFFICIENT_DATA":
            return SynthesisResult(verdict, agreement_level, key_tension="", reasoning="")

        # Independent calls: one stage of the run takes one call's time, not two. Each
        # catches its own failure, so one failing leaves the other intact.
        key_tension, synthesis_reasoning = await asyncio.gather(
            self._generate_key_tension(ticker, verdict, agreement_level, round2),
            self._generate_synthesis_reasoning(ticker, verdict, round2),
        )

        return SynthesisResult(
            verdict=verdict,
            agreement_level=agreement_level,
            key_tension=key_tension,
            reasoning=synthesis_reasoning,
        )

    async def _generate_key_tension(
        self,
        ticker: str,
        verdict: Verdict,
        agreement_level: AgreementLevel,
        round2: dict[str, AgentPosition],
    ) -> str | None:
        """The model's key tension, or None when the call failed or the reply is unusable."""
        prompt = _TENSION_PROMPT.format(
            ticker=ticker,
            positions=_positions(_TENSION_POSITIONS, round2),
            vote=_vote_summary(round2, agreement_level),
            describe_only=DESCRIBE_ONLY,
        )
        try:
            reply = await self._llm.chat([
                {"role": "system", "content": "You are a concise financial debate synthesiser."},
                {"role": "user", "content": prompt},
            ])
        except Exception as exc:
            logger.warning("Synthesiser key_tension LLM call failed: %s", exc)
            return None
        return _usable(reply)

    async def _generate_synthesis_reasoning(
        self,
        ticker: str,
        verdict: Verdict,
        round2: dict[str, AgentPosition],
    ) -> str:
        """The model's summary, or the deterministic vote line when the call failed or the reply is unusable."""
        fallback = f"Vote: {_vote_summary(round2)}."
        prompt = _SYNTHESIS_SUMMARY_PROMPT.format(
            ticker=ticker,
            vote=_vote_summary(round2),
            positions=_positions(_SUMMARY_POSITIONS, round2),
            describe_only=DESCRIBE_ONLY,
        )
        try:
            reply = await self._llm.chat([
                {"role": "system", "content": "You are a concise financial debate synthesiser."},
                {"role": "user", "content": prompt},
            ])
        except Exception as exc:
            logger.warning("Synthesiser reasoning LLM call failed: %s", exc)
            return fallback
        return _usable(reply) or fallback
