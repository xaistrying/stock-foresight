"""Debate engine — orchestrates the two-round multi-agent debate.

Round 1: TechnicalAgent, NewsAgent, MacroAgent run concurrently.
Round 2: Each agent receives all Round 1 positions and responds concurrently.
Synthesis: Synthesiser maps stances to verdict + key_tension.

Shared data models live here so all sub-modules can import without cycles.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, replace
from typing import Literal

logger = logging.getLogger(__name__)

Stance = Literal["bull", "bear", "neutral"]
Verdict = Literal[
    "STRONG_BUY_SIGNAL",
    "BUY_SIGNAL",
    "OBSERVE",
    "CAUTION_SIGNAL",
    "STRONG_CAUTION_SIGNAL",
    "SPLIT",
]
AgreementLevel = Literal["unanimous", "majority", "split"]

ROUND2_UNAVAILABLE_NOTE = "Round 2 unavailable — Round 1 position kept."


@dataclass
class AgentPosition:
    agent_id: str  # "technical" | "news" | "macro"
    stance: Stance
    reasoning: list[str]  # 3-5 plain-language bullets
    volatility_range_pct: float | None = None  # only set by TechnicalAgent


@dataclass
class SynthesisResult:
    verdict: Verdict
    agreement_level: AgreementLevel
    key_tension: str
    reasoning: str


@dataclass
class DebateResult:
    ticker: str
    as_of: str
    verdict: Verdict
    agreement_level: AgreementLevel
    round1: dict[str, AgentPosition]  # keyed by agent_id
    round2: dict[str, AgentPosition]
    synthesis: SynthesisResult
    volatility_range_pct: float | None
    duration_ms: int


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DebateEngine:
    """Runs the full two-round debate for a given ticker."""

    def __init__(self) -> None:
        # Agents imported here to avoid circular imports at module load time
        from app.services.debate.macro import MacroAgent
        from app.services.debate.news import NewsAgent
        from app.services.debate.synthesiser import Synthesiser
        from app.services.debate.technical import TechnicalAgent

        self._technical = TechnicalAgent()
        self._news = NewsAgent()
        self._macro = MacroAgent()
        self._synthesiser = Synthesiser()

    async def run(self, ticker: str) -> DebateResult:
        t0 = time.monotonic()

        # ------------------------------------------------------------------
        # Round 1 — all three agents in parallel
        # ------------------------------------------------------------------
        r1_technical, r1_news, r1_macro = await asyncio.gather(
            self._safe_run(self._technical.run, ticker, "technical"),
            self._safe_run(self._news.run, ticker, "news"),
            self._safe_run(self._macro.run, ticker, "macro"),
        )
        round1 = {
            "technical": r1_technical,
            "news": r1_news,
            "macro": r1_macro,
        }

        # ------------------------------------------------------------------
        # Round 2 — each agent receives all Round 1 positions
        # ------------------------------------------------------------------
        r2_technical, r2_news, r2_macro = await asyncio.gather(
            self._safe_run(self._technical.respond, ticker, "technical", round1, fallback=round1["technical"]),
            self._safe_run(self._news.respond, ticker, "news", round1, fallback=round1["news"]),
            self._safe_run(self._macro.respond, ticker, "macro", round1, fallback=round1["macro"]),
        )
        round2 = {
            "technical": r2_technical,
            "news": r2_news,
            "macro": r2_macro,
        }

        # ------------------------------------------------------------------
        # Synthesis
        # ------------------------------------------------------------------
        synthesis = await self._synthesiser.run(ticker, round1, round2)

        duration_ms = int((time.monotonic() - t0) * 1000)

        return DebateResult(
            ticker=ticker,
            as_of=self._get_as_of(round1),
            verdict=synthesis.verdict,
            agreement_level=synthesis.agreement_level,
            round1=round1,
            round2=round2,
            synthesis=synthesis,
            volatility_range_pct=round1["technical"].volatility_range_pct,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _safe_run(
        fn, ticker: str, agent_id: str, *args, fallback: AgentPosition | None = None
    ) -> AgentPosition:
        """Run an agent coroutine; on any exception return `fallback` (Round 2: the
        agent's Round 1 position, so one failed call can't flip it to neutral) or,
        with none, a neutral "unavailable" position (Round 1)."""
        try:
            return await fn(ticker, *args)
        except Exception as exc:
            logger.warning("Agent '%s' failed: %s", agent_id, exc, exc_info=True)
            if fallback is not None:
                return replace(fallback, reasoning=[*fallback.reasoning, ROUND2_UNAVAILABLE_NOTE])
            return AgentPosition(
                agent_id=agent_id,
                stance="neutral",
                reasoning=["Agent unavailable — analysis could not be completed."],
            )

    @staticmethod
    def _get_as_of(round1: dict[str, AgentPosition]) -> str:
        """Best-effort date from the technical agent (has DB access)."""
        tech = round1.get("technical")
        if tech and hasattr(tech, "_as_of"):
            return tech._as_of  # type: ignore[attr-defined]
        from datetime import date
        return date.today().isoformat()
