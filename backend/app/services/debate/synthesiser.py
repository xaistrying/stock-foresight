"""Debate Synthesiser — maps Round 2 stances to a verdict and identifies key tension.

Verdict mapping (design.md Decision 2):
    3/3 bull  → STRONG_BUY_SIGNAL  / unanimous
    2/3 bull  → BUY_SIGNAL         / majority
    3/3 neutral → OBSERVE          / unanimous
    2 neutral + 1 directional → OBSERVE / majority
    1 bull + 1 neutral + 1 bear → SPLIT / split
    2/3 bear  → CAUTION_SIGNAL     / majority
    3/3 bear  → STRONG_CAUTION_SIGNAL / unanimous

Rule 6: verdict labels are signals/observations, never "BUY"/"SELL".
"""

from __future__ import annotations

import logging

from app.services.debate.engine import (
    AgentPosition,
    AgreementLevel,
    SynthesisResult,
    Verdict,
)
from app.services.debate.llm_client import LLMClient

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


_TENSION_PROMPT = """\
You are a financial debate synthesiser. Three agents have analysed the stock
{ticker} and reached the following positions after two rounds of debate:

Technical Signal agent (Round 2): {tech_stance}
  Reasoning: {tech_reasoning}

News Context agent (Round 2): {news_stance}
  Reasoning: {news_reasoning}

Macro agent (Round 2): {macro_stance}
  Reasoning: {macro_reasoning}

Verdict: {verdict} ({agreement_level})

Write a single paragraph (2-4 sentences) identifying the KEY TENSION in this
debate: the most important disagreement or uncertainty, even if agents agreed.
If there is a dissenting agent, state specifically what they argued and why it
matters. If unanimous, identify the most significant risk the analysis did not
resolve. Be concise and specific. Write in English.
"""

_SYNTHESIS_SUMMARY_PROMPT = """\
You are a financial debate synthesiser. Summarise the overall reasoning that
led to the verdict "{verdict}" for stock {ticker} in 2-3 sentences. Reference
the key points from all three agents. Write in English, concisely.

Technical Signal: {tech_stance} — {tech_reasoning}
News Context: {news_stance} — {news_reasoning}
Macro: {macro_stance} — {macro_reasoning}
"""


def _agent_fields(round2: dict[str, AgentPosition]) -> dict[str, str]:
    """Prompt placeholders for every agent's Round 2 stance and ALL its bullets
    (slicing to the first two once dropped the signal that decided a vote)."""
    fields: dict[str, str] = {}
    for key, agent_id in (("tech", "technical"), ("news", "news"), ("macro", "macro")):
        pos = round2.get(agent_id)
        fields[f"{key}_stance"] = pos.stance if pos else "N/A"
        fields[f"{key}_reasoning"] = "; ".join(pos.reasoning) if pos else "N/A"
    return fields


class Synthesiser:
    def __init__(self) -> None:
        self._llm = LLMClient()

    async def run(
        self,
        ticker: str,
        round1: dict[str, AgentPosition],
        round2: dict[str, AgentPosition],
    ) -> SynthesisResult:
        # Use Round 2 stances for verdict
        r2_stances = [round2[a].stance for a in ("technical", "news", "macro")]
        verdict, agreement_level = _map_verdict(r2_stances)

        key_tension = await self._generate_key_tension(ticker, verdict, agreement_level, round2)
        synthesis_reasoning = await self._generate_synthesis_reasoning(
            ticker, verdict, round2
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
    ) -> str:
        prompt = _TENSION_PROMPT.format(
            ticker=ticker,
            **_agent_fields(round2),
            verdict=verdict,
            agreement_level=agreement_level,
        )
        try:
            return await self._llm.chat([
                {"role": "system", "content": "You are a concise financial debate synthesiser."},
                {"role": "user", "content": prompt},
            ])
        except Exception as exc:
            logger.warning("Synthesiser key_tension LLM call failed: %s", exc)
            return "Unable to generate key tension analysis."

    async def _generate_synthesis_reasoning(
        self,
        ticker: str,
        verdict: Verdict,
        round2: dict[str, AgentPosition],
    ) -> str:
        prompt = _SYNTHESIS_SUMMARY_PROMPT.format(
            ticker=ticker,
            verdict=verdict,
            **_agent_fields(round2),
        )
        try:
            return await self._llm.chat([
                {"role": "system", "content": "You are a concise financial debate synthesiser."},
                {"role": "user", "content": prompt},
            ])
        except Exception as exc:
            logger.warning("Synthesiser reasoning LLM call failed: %s", exc)
            r2_stances = [p.stance for p in round2.values()]
            return f"Verdict: {verdict} ({'; '.join(r2_stances)})"
