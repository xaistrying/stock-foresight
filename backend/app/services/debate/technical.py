"""Technical Agent for the debate engine.

Reads the ticker's latest feature row, computes a stance from RSI/MACD/Ichimoku
(Rule 5: technical proxy, labeled "Technical Signal" in the UI), adds a
HAR-RV volatility range estimate, then uses the LLM to produce readable
bullet reasoning.

Rule 5: stance is derived from RSI, MACD histogram, Ichimoku Tenkan/Kijun —
never from real news or NLP sentiment. Labeled "Technical Signal" in the UI.
Rule 1: volatility range is for the next 5 trading sessions.
Rule 2: volatility_range_pct is a percentage, never a raw log return.
"""

from __future__ import annotations

import logging
import re

from app.api.predictions import get_latest_features_row
from app.ml.volatility import predict_volatility_range
from app.services.debate.engine import AgentPosition, Stance
from app.services.debate.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Indicator thresholds (same as insight.py _compute_sentiment)
RSI_BULL_THRESHOLD = 55
RSI_BEAR_THRESHOLD = 45


def _compute_stance_from_indicators(row: dict) -> tuple[Stance, list[str], dict]:
    """Majority vote from RSI, MACD histogram, Ichimoku Tenkan/Kijun.

    Returns (stance, available_indicators, indicator_values).
    Mirrors the logic in app.api.insight._compute_sentiment so both surfaces
    are consistent (Rule 5).
    """
    bull = 0
    bear = 0
    available: list[str] = []
    values: dict = {}

    rsi = row.get("rsi")
    if rsi is not None:
        available.append("RSI")
        values["rsi"] = round(float(rsi), 1)
        if rsi >= RSI_BULL_THRESHOLD:
            bull += 1
        elif rsi <= RSI_BEAR_THRESHOLD:
            bear += 1

    macd_hist = row.get("macd_histogram")
    if macd_hist is not None:
        available.append("MACD")
        values["macd_histogram"] = round(float(macd_hist), 4)
        if macd_hist > 0:
            bull += 1
        elif macd_hist < 0:
            bear += 1

    tenkan = row.get("tenkan_sen")
    kijun = row.get("kijun_sen")
    if tenkan is not None and kijun is not None:
        available.append("Ichimoku")
        values["tenkan_sen"] = round(float(tenkan), 2)
        values["kijun_sen"] = round(float(kijun), 2)
        if tenkan > kijun:
            bull += 1
        elif tenkan < kijun:
            bear += 1

    if not available:
        return "neutral", [], {}

    if bull > bear:
        stance: Stance = "bull"
    elif bear > bull:
        stance = "bear"
    else:
        stance = "neutral"

    return stance, available, values


_REASONING_PROMPT = """\
You are a technical analysis assistant for Vietnamese stocks. Given the
indicator values below, produce 3-5 concise plain-language bullet points
(each starting with "- ") explaining the technical picture. Each bullet MUST
reference a specific indicator name and value. Use English. Do not add any
information beyond what is given.

Ticker: {ticker}
Date: {date}
Stance: {stance}

Indicator values:
{indicator_lines}
Volatility range: ±{vol_range}% expected over next 5 trading sessions
"""

_FALLBACK_REASONING = ["Indicator data unavailable for this session."]


class TechnicalAgent:
    def __init__(self) -> None:
        self._llm = LLMClient()

    async def run(self, ticker: str) -> AgentPosition:
        """Round 1: compute stance + volatility range, generate LLM reasoning."""
        row = get_latest_features_row(ticker)
        if row is None:
            return AgentPosition(
                agent_id="technical",
                stance="neutral",
                reasoning=["No feature data available for this ticker."],
            )

        stance, available, values = _compute_stance_from_indicators(row)
        vol_range = predict_volatility_range(ticker)

        if not available:
            return AgentPosition(
                agent_id="technical",
                stance="neutral",
                reasoning=_FALLBACK_REASONING,
                volatility_range_pct=vol_range,
            )

        reasoning = await self._generate_reasoning(
            ticker, str(row.get("date", "unknown")), stance, values, vol_range
        )

        pos = AgentPosition(
            agent_id="technical",
            stance=stance,
            reasoning=reasoning,
            volatility_range_pct=vol_range,
        )
        # Attach date for engine._get_as_of
        pos._as_of = str(row.get("date", ""))  # type: ignore[attr-defined]
        return pos

    async def respond(self, ticker: str, round1: dict) -> AgentPosition:
        """Round 2: review other agents' positions; update stance if warranted."""
        my_r1 = round1.get("technical")
        others = {k: v for k, v in round1.items() if k != "technical"}

        other_lines = "\n".join(
            f"- {k.capitalize()} agent ({v.stance}): {'; '.join(v.reasoning[:2])}"
            for k, v in others.items()
        )

        prompt = f"""\
You are the Technical Analysis agent. Your Round 1 stance was: {my_r1.stance if my_r1 else "neutral"}.
Your Round 1 reasoning: {'; '.join(my_r1.reasoning[:3]) if my_r1 else "N/A"}

Other agents' Round 1 positions:
{other_lines}

Review these positions. Maintain your stance if your technical evidence supports it.
Only shift if a SPECIFIC counter-argument from another agent is compelling — and
state exactly why you are shifting. Produce 3-5 bullet points (each starting with
"- ") for your updated reasoning. Do not capitulate without a concrete reason.

Respond in English with your final stance on the first line as exactly one word:
bull, bear, or neutral. Then list your updated reasoning bullets.
"""
        response = await self._llm.chat([
            {"role": "system", "content": "You are a strict technical analyst. Be concise and evidence-based."},
            {"role": "user", "content": prompt},
        ])

        stance, reasoning = _parse_stance_and_bullets(response, my_r1)
        return AgentPosition(
            agent_id="technical",
            stance=stance,
            reasoning=reasoning,
            volatility_range_pct=my_r1.volatility_range_pct if my_r1 else None,
        )

    async def _generate_reasoning(
        self,
        ticker: str,
        date: str,
        stance: Stance,
        values: dict,
        vol_range: float | None,
    ) -> list[str]:
        indicator_lines = "\n".join(f"  {k}: {v}" for k, v in values.items())
        vol_str = f"{vol_range:.2f}" if vol_range is not None else "N/A"
        prompt = _REASONING_PROMPT.format(
            ticker=ticker,
            date=date,
            stance=stance,
            indicator_lines=indicator_lines,
            vol_range=vol_str,
        )
        try:
            response = await self._llm.chat([
                {"role": "system", "content": "You are a concise technical analysis assistant."},
                {"role": "user", "content": prompt},
            ])
            bullets = _extract_bullets(response)
            if bullets:
                return bullets[:5]
        except Exception as exc:
            logger.warning("TechnicalAgent LLM call failed: %s", exc)
        return _FALLBACK_REASONING


_BULLET = re.compile(r"^[-*•]\s+(.*)$")  # marker + whitespace: "-2.5%" is not a bullet
# A line that STARTS with the stance word, tolerating markdown, a "Stance:" label
# (even "Stance (Round 2):"), "bullish"/"bearish", and a trailing annotation after a
# separator ("Bear — shifting because ...", "bear (shifted from bull)"). A sentence
# such as "Bear market weighs on ..." is not a stance line.
_STANCE_LINE = re.compile(
    r"^[\W_]*(?:(?:my|final|updated)\s+)*(?:stance(?:\s*\([^)]*\))?[\W_]*)?"
    r"(bull|bear|neutral)(?:ish)?(?![A-Za-z])(?=[\W_]*$|\s*[—–:(,;.\-])",
    re.IGNORECASE,
)
_STANCE_SCAN_LINES = 3  # the stance may follow a short preamble or heading


def _extract_bullets(text: str) -> list[str]:
    """Bullet lines with ONE leading marker removed (never `lstrip`, which would
    eat the minus of a bullet that starts with a negative number)."""
    matches = (_BULLET.match(raw.strip()) for raw in text.splitlines())
    return [m.group(1).strip() for m in matches if m and re.search(r"\w", m.group(1))]


def _parse_stance_and_bullets(response: str, fallback: AgentPosition | None) -> tuple[Stance, list[str]]:
    """Parse LLM response: a stance line near the top, then bullet lines.

    An unrecognised stance keeps the agent's Round 1 stance (`fallback`), or
    neutral when there is none, and is logged: a formatting slip must not
    silently flip a stance toward OBSERVE. A blank response raises, so the
    caller's own error handling runs instead of a silent "success".
    """
    lines = [l.strip() for l in response.strip().splitlines() if l.strip()]
    if not lines:
        raise ValueError("empty LLM response")

    stance: Stance = fallback.stance if fallback else "neutral"
    found = False
    for index, line in enumerate(lines[:_STANCE_SCAN_LINES]):
        if _BULLET.match(line):
            break  # past the header: "- Bear case: ..." is reasoning, not the stance
        match = _STANCE_LINE.match(line)
        if match:
            stance, found = match.group(1).lower(), True  # type: ignore[assignment]
            lines = lines[index + 1:]
            break
    if not found:
        logger.warning("Unrecognised stance line, keeping %s: %.80r", stance, lines[0])

    bullets = _extract_bullets("\n".join(lines))
    if not bullets:
        bullets = [l for l in lines[:5] if l]
    if not bullets and fallback:
        bullets = fallback.reasoning
    return stance, bullets or ["No updated reasoning provided."]
