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
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Literal

from app.services.debate.prompt_safety import withhold_advice

logger = logging.getLogger(__name__)

Stance = Literal["bull", "bear", "neutral"]
Verdict = Literal[
    "STRONG_BUY_SIGNAL",
    "BUY_SIGNAL",
    "OBSERVE",
    "CAUTION_SIGNAL",
    "STRONG_CAUTION_SIGNAL",
    "SPLIT",
    "INSUFFICIENT_DATA",
]
AgreementLevel = Literal["unanimous", "majority", "split", "none"]
# Why an agent has no vote: it raised (agent_error), had nothing to read
# (no_input), its LLM-only stance failed in Round 1 (llm_failed), or its Round 2
# call failed (round2_failed).
DegradedReason = Literal["agent_error", "no_input", "llm_failed", "round2_failed"]

AGENT_ORDER = ("technical", "news", "macro")
AGENT_UNAVAILABLE_REASONING = ["Agent unavailable — analysis could not be completed."]
ROUND2_UNAVAILABLE_NOTE = "Round 2 unavailable — Round 1 position kept, not counted in the vote."


@dataclass
class AgentPosition:
    agent_id: str  # "technical" | "news" | "macro"
    stance: Stance  # a degraded agent's stance is a placeholder and never votes
    reasoning: list[str]  # 3-5 plain-language bullets
    # Typical 5-session move and its inputs; only set by TechnicalAgent (volatility-range capability).
    range_5s_pct: float | None = None
    sigma_daily_pct: float | None = None  # daily, never labelled "5 sessions"
    range_coverage: float | None = None  # None: not measured for this stock
    degraded_reason: DegradedReason | None = None  # None = live
    # Round 1 only: what the agent actually read, for the outcome log (no re-fetch later).
    evidence: dict | None = None


@dataclass
class SynthesisResult:
    verdict: Verdict
    agreement_level: AgreementLevel
    key_tension: str | None  # None: the call failed or its reply was unusable ("unavailable")
    reasoning: str


@dataclass
class DebateResult:
    ticker: str
    as_of: str | None
    verdict: Verdict
    agreement_level: AgreementLevel
    round1: dict[str, AgentPosition]  # keyed by agent_id
    round2: dict[str, AgentPosition]
    synthesis: SynthesisResult
    duration_ms: int
    range_5s_pct: float | None = None
    sigma_daily_pct: float | None = None
    range_coverage: float | None = None
    data_as_of: str | None = None  # == as_of; the shared contract's name
    data_age_sessions: int | None = None
    agents_degraded: list[str] = field(default_factory=list)  # in AGENT_ORDER
    eligibility: dict = field(default_factory=lambda: {"eligible": True, "reasons": []})


def insufficient_data_result(ticker: str, eligibility: dict, duration_ms: int = 0) -> DebateResult:
    """The abstention shape: no agent ran, so none is "degraded" (design Decision 3)."""
    return DebateResult(
        ticker=ticker,
        as_of=eligibility["as_of"],
        verdict="INSUFFICIENT_DATA",
        agreement_level="none",
        round1={},
        round2={},
        synthesis=SynthesisResult("INSUFFICIENT_DATA", "none", "", ""),
        duration_ms=duration_ms,
        data_as_of=eligibility["as_of"],
        data_age_sessions=eligibility["age_sessions"],
        agents_degraded=[],
        eligibility={"eligible": eligibility["eligible"], "reasons": list(eligibility["reasons"])},
    )


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

    async def run(
        self,
        ticker: str,
        eligibility: dict | None = None,
        on_stage: Callable[[str], None] | None = None,
    ) -> DebateResult:
        """Run the debate on the features row dated `eligibility["as_of"]`.

        `eligibility` is `assess_eligibility(ticker)`; it is fetched when absent.
        An ineligible ticker abstains without running any agent. A degraded agent
        (one whose stance cannot be trusted) is excluded from Round 2 and the vote.
        `on_stage` is called with `round1`, `round2` (only when Round 2 runs) and
        `synthesis` as each stage starts: the runner's progress and timing.
        """
        t0 = time.monotonic()
        if eligibility is None:
            from app.services.data_eligibility import assess_eligibility

            eligibility = assess_eligibility(ticker)
        if not eligibility["eligible"]:
            return insufficient_data_result(ticker, eligibility)
        as_of = eligibility["as_of"]

        # ------------------------------------------------------------------
        # Round 1 — all three agents in parallel
        # ------------------------------------------------------------------
        if on_stage:
            on_stage("round1")
        r1_technical, r1_news, r1_macro = await asyncio.gather(
            self._safe_run(self._technical.run, ticker, "technical", as_of),
            self._safe_run(self._news.run, ticker, "news"),
            self._safe_run(self._macro.run, ticker, "macro"),
        )
        round1 = dict(zip(AGENT_ORDER, (r1_technical, r1_news, r1_macro)))

        # ------------------------------------------------------------------
        # Round 2 — live agents only, and they see only live positions: a
        # degraded agent's placeholder is not evidence. With fewer than two
        # live agents there is nothing to debate.
        # ------------------------------------------------------------------
        live = {agent_id: pos for agent_id, pos in round1.items() if pos.degraded_reason is None}
        round2 = dict(round1)
        if len(live) >= 2:
            if on_stage:
                on_stage("round2")
            agents = {"technical": self._technical, "news": self._news, "macro": self._macro}
            responses = await asyncio.gather(*(
                self._safe_run(agents[agent_id].respond, ticker, agent_id, live, fallback=live[agent_id])
                for agent_id in live
            ))
            round2.update(zip(live, responses))

        # ------------------------------------------------------------------
        # Synthesis
        # ------------------------------------------------------------------
        if on_stage:
            on_stage("synthesis")
        synthesis = await self._synthesiser.run(ticker, round1, round2)

        duration_ms = int((time.monotonic() - t0) * 1000)
        abstained = synthesis.verdict == "INSUFFICIENT_DATA"
        technical = None if abstained else round1["technical"]

        return DebateResult(
            ticker=ticker,
            as_of=as_of,
            verdict=synthesis.verdict,
            agreement_level=synthesis.agreement_level,
            round1=round1,
            round2=round2,
            synthesis=synthesis,
            duration_ms=duration_ms,
            range_5s_pct=technical and technical.range_5s_pct,
            sigma_daily_pct=technical and technical.sigma_daily_pct,
            range_coverage=technical and technical.range_coverage,
            data_as_of=as_of,
            data_age_sessions=eligibility["age_sessions"],
            agents_degraded=[a for a in AGENT_ORDER if round2[a].degraded_reason is not None],
            eligibility={"eligible": True, "reasons": []},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _safe_run(
        fn, ticker: str, agent_id: str, *args, fallback: AgentPosition | None = None
    ) -> AgentPosition:
        """Run an agent coroutine; on any exception return a degraded position.

        Round 1 (no `fallback`): a neutral placeholder with `agent_error`.
        Round 2: the agent's Round 1 position, shown but marked `round2_failed`
        so it is not counted in the vote. A reply with no stance line also lands
        here: the parser raises (`StanceNotRecognised`) instead of guessing.

        A position that returns is checked for recommendation-style wording here,
        before anything uses it: a withheld bullet is a placeholder in Round 2, the
        synthesiser, the panel and the export alike (the stance is not touched).
        """
        try:
            position = await fn(ticker, *args)
            reasoning = [withhold_advice(bullet, agent_id) for bullet in position.reasoning]
            return position if reasoning == position.reasoning else replace(position, reasoning=reasoning)
        except Exception as exc:
            logger.warning("Agent '%s' failed: %s", agent_id, exc, exc_info=True)
            if fallback is not None:
                return replace(
                    fallback,
                    reasoning=[*fallback.reasoning, ROUND2_UNAVAILABLE_NOTE],
                    degraded_reason="round2_failed",
                )
            return AgentPosition(
                agent_id=agent_id,
                stance="neutral",
                reasoning=list(AGENT_UNAVAILABLE_REASONING),
                degraded_reason="agent_error",
            )
