"""Technical Agent for the debate engine.

Reads the ticker's latest feature row, computes a stance from RSI/MACD/Ichimoku
(Rule 5: technical proxy, labeled "Technical Signal" in the UI), adds a
typical 5-session move (calibrated HAR-RV band, from the range service), then
uses the LLM to produce readable bullet reasoning.

Rule 5: stance is derived from RSI, MACD histogram, Ichimoku Tenkan/Kijun —
never from real news or NLP sentiment. Labeled "Technical Signal" in the UI.
Rule 1: the typical move is for the next 5 trading sessions.
Rule 2: range_5s_pct is a percentage, never a raw log return.
"""

from __future__ import annotations

import asyncio
import logging
import re

from app.db.connection import get_connection
from app.services.debate.engine import AgentPosition, Stance
from app.services.debate.llm_client import LLMClient
from app.services.debate.prompt_safety import DESCRIBE_ONLY, fence
from app.services.feature_rows import get_latest_features_row
from app.services.range import RangeResult, compute_range, coverage_phrase

logger = logging.getLogger(__name__)

# Indicator thresholds for the stance vote
RSI_BULL_THRESHOLD = 55
RSI_BEAR_THRESHOLD = 45


def _compute_stance_from_indicators(row: dict) -> tuple[Stance, list[str], dict]:
    """Majority vote from RSI, MACD histogram, Ichimoku Tenkan/Kijun.

    Returns (stance, available_indicators, indicator_values).
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
information beyond what is given. {describe_only}

Ticker: {ticker}
Date: {date}
Stance: {stance}

Indicator values:
{indicator_lines}
{range_line}
The typical 5-session move is a size, not a direction, not a ceiling and not a prediction.
If it is unavailable, do not estimate one.
"""

_FALLBACK_REASONING = ["Indicator data unavailable for this session."]
_VALUE_LABELS = {
    "rsi": "RSI",
    "macd_histogram": "MACD histogram",
    "tenkan_sen": "Ichimoku Tenkan-sen",
    "kijun_sen": "Ichimoku Kijun-sen",
}
_FEATURES_BY_DATE = (
    "SELECT date, rsi, macd_histogram, tenkan_sen, kijun_sen, near_gap "
    "FROM features WHERE ticker = ? AND date = ?"
)


_SERVED_STATUSES = ("ok", "uncalibrated")


def _served_band(band: RangeResult | None) -> RangeResult | None:
    return band if band is not None and band.status in _SERVED_STATUSES else None


def _range_line(band: RangeResult | None) -> str:
    """The prompt line for the typical 5-session move (design.md Decision 14)."""
    band = _served_band(band)
    if band is None:
        return "Typical 5-session move: unavailable"
    coverage = (
        f"{coverage_phrase(band.range_coverage)} of past 5-session moves stayed within this band"
        if band.range_coverage is not None
        else "coverage not established for this stock"
    )
    return (
        f"Typical 5-session move: ±{band.range_5s_pct:.1f}% ({coverage}; "
        f"daily volatility forecast {band.sigma_daily_pct:.2f}%)"
    )


async def _fetch_range(ticker: str) -> RangeResult | None:
    """The range service answers or the line reads "unavailable"; it never stops the agent."""
    try:
        return await asyncio.to_thread(compute_range, ticker)  # blocking sqlite
    except Exception as exc:
        logger.warning("Range service failed for %s: %s", ticker, exc, exc_info=True)
        return None


def _band_fields(band: RangeResult | None) -> dict:
    band = _served_band(band)
    return {
        "range_5s_pct": band.range_5s_pct if band else None,
        "sigma_daily_pct": band.sigma_daily_pct if band else None,
        "range_coverage": band.range_coverage if band else None,
    }


def _get_features_row(ticker: str, as_of: str) -> dict | None:
    """The features row of one date (`feature_rows` only reads the latest)."""
    conn = get_connection()
    try:
        cursor = conn.execute(_FEATURES_BY_DATE, (ticker, as_of))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip([column[0] for column in cursor.description], row))
    finally:
        conn.close()


class TechnicalAgent:
    def __init__(self) -> None:
        self._llm = LLMClient()

    async def run(self, ticker: str, as_of: str | None = None) -> AgentPosition:
        """Round 1: compute stance + typical 5-session move, generate LLM reasoning.

        Reads the features row dated `as_of` (the engine passes the eligibility
        date, so a refresh during the debate cannot change the data under the
        label); the latest row when `as_of` is not given.
        """
        # Blocking SQLite: off the event loop.
        if as_of:
            row = await asyncio.to_thread(_get_features_row, ticker, as_of)
        else:
            row = await asyncio.to_thread(get_latest_features_row, ticker)
        if row is None:
            return AgentPosition(
                agent_id="technical",
                stance="neutral",
                reasoning=["No feature data available for this ticker."],
                degraded_reason="no_input",
            )

        stance, available, values = _compute_stance_from_indicators(row)
        band = await _fetch_range(ticker)

        if not available:
            return AgentPosition(
                agent_id="technical",
                stance="neutral",
                reasoning=_FALLBACK_REASONING,
                **_band_fields(band),
                degraded_reason="no_input",
            )

        reasoning = await self._generate_reasoning(
            ticker, str(row.get("date", "unknown")), stance, values, band
        )
        served = _served_band(band)
        return AgentPosition(
            agent_id="technical",
            stance=stance,
            reasoning=reasoning,
            **_band_fields(band),
            evidence={**values, "near_gap": row.get("near_gap"), "range_k": served.range_k if served else None},
        )

    async def respond(self, ticker: str, round1: dict) -> AgentPosition:
        """Round 2: review other agents' positions; update stance if warranted."""
        my_r1 = round1.get("technical")
        others = {k: v for k, v in round1.items() if k != "technical"}

        other_lines = "\n".join(
            f"- {k.capitalize()} agent ({v.stance}): {'; '.join(v.reasoning[:2])}"
            for k, v in others.items()
        )
        peers = fence("PEERS", other_lines)  # the peers' bullets can quote scraped headlines

        prompt = f"""\
You are the Technical Analysis agent. Your Round 1 stance was: {my_r1.stance if my_r1 else "neutral"}.
Your Round 1 reasoning: {'; '.join(my_r1.reasoning[:3]) if my_r1 else "N/A"}

Other agents' Round 1 positions:
{peers}

Review these positions. Maintain your stance if your technical evidence supports it.
Only shift if a SPECIFIC counter-argument from another agent is compelling — and
state exactly why you are shifting. Produce 3-5 bullet points (each starting with
"- ") for your updated reasoning. Do not capitulate without a concrete reason.
{DESCRIBE_ONLY}

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
            range_5s_pct=my_r1.range_5s_pct if my_r1 else None,
            sigma_daily_pct=my_r1.sigma_daily_pct if my_r1 else None,
            range_coverage=my_r1.range_coverage if my_r1 else None,
        )

    async def _generate_reasoning(
        self,
        ticker: str,
        date: str,
        stance: Stance,
        values: dict,
        band: RangeResult | None,
    ) -> list[str]:
        indicator_lines = "\n".join(f"  {k}: {v}" for k, v in values.items())
        prompt = _REASONING_PROMPT.format(
            ticker=ticker,
            date=date,
            stance=stance,
            indicator_lines=indicator_lines,
            range_line=_range_line(band),
            describe_only=DESCRIBE_ONLY,
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
        # The stance is computed, so a failed LLM only costs the prose: state the
        # values rather than claim the data is unavailable.
        return [f"{_VALUE_LABELS[name]}: {value}" for name, value in values.items()]


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


class StanceNotRecognised(ValueError):
    """The reply has no stance line: a failed call, never a guessed or kept stance."""


def _parse_stance_and_bullets(response: str, fallback: AgentPosition | None) -> tuple[Stance, list[str]]:
    """Parse LLM response: a stance line near the top, then bullet lines.

    A blank response raises `ValueError` and a reply with no recognisable stance
    line raises `StanceNotRecognised`, so the caller's own error handling runs
    (Round 2: the agent is excluded from the vote; News Round 1: `llm_failed`)
    instead of a formatting slip silently confirming or flipping a stance.
    `fallback` only supplies bullets when the reply has none.
    """
    lines = [l.strip() for l in response.strip().splitlines() if l.strip()]
    if not lines:
        raise ValueError("empty LLM response")

    stance: Stance | None = None
    for index, line in enumerate(lines[:_STANCE_SCAN_LINES]):
        if _BULLET.match(line):
            break  # past the header: "- Bear case: ..." is reasoning, not the stance
        match = _STANCE_LINE.match(line)
        if match:
            stance = match.group(1).lower()  # type: ignore[assignment]
            lines = lines[index + 1:]
            break
    if stance is None:
        raise StanceNotRecognised(f"no stance line in reply: {lines[0][:80]!r}")

    bullets = _extract_bullets("\n".join(lines))
    if not bullets:
        bullets = [l for l in lines[:5] if l]
    if not bullets and fallback:
        bullets = fallback.reasoning
    return stance, bullets or ["No updated reasoning provided."]
