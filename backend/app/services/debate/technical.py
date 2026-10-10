"""Technical Agent for the debate engine.

Reads the ticker's latest feature row, computes a stance from RSI/MACD/Ichimoku
(Rule 5: technical proxy, labeled "Technical Signal" in the UI) and carries the
typical 5-session move (calibrated HAR-RV band, from the range service) on the position.
Its reasoning is the list of computed indicator values; the agent calls no language
model (`retire-debate-round-two-and-model-prose`).

Rule 5: stance is derived from RSI, MACD histogram, Ichimoku Tenkan/Kijun —
never from real news or NLP sentiment. Labeled "Technical Signal" in the UI.
Rule 1: the typical move is for the next 5 trading sessions.
Rule 2: range_5s_pct is a percentage, never a raw log return. The bullets do not state it:
the range block and the export Summary do.
"""

from __future__ import annotations

import asyncio
import logging
import re

from app.db.connection import get_connection
from app.services.debate.engine import AgentPosition, Stance
from app.services.feature_rows import get_latest_features_row
from app.services.range import RangeResult, compute_range

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


async def _fetch_range(ticker: str) -> RangeResult | None:
    """The range service answers or the band fields stay null; it never stops the agent."""
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


def _values_list(values: dict) -> list[str]:
    """One bullet per available indicator, in the order of `_compute_stance_from_indicators`."""
    return [f"{_VALUE_LABELS[name]}: {value}" for name, value in values.items()]


class TechnicalAgent:
    async def run(self, ticker: str, as_of: str | None = None) -> AgentPosition:
        """Compute the stance and the typical 5-session move; reasoning is the values list.

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

        served = _served_band(band)
        return AgentPosition(
            agent_id="technical",
            stance=stance,
            reasoning=_values_list(values),
            **_band_fields(band),
            evidence={**values, "near_gap": row.get("near_gap"), "range_k": served.range_k if served else None},
        )


_BULLET = re.compile(r"^[-*•]\s+(.*)$")  # marker + whitespace: "-2.5%" is not a bullet
# A line that STARTS with the stance word, tolerating markdown, a "Stance:" label
# (even "Stance (final):"), "bullish"/"bearish", and a trailing annotation after a
# separator ("Bear — weak headlines", "bear (mostly market news)"). A sentence
# such as "Bear market weighs on ..." is not a stance line. The News agent's reply is the
# only text parsed here.
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
    (News: `llm_failed`) instead of a formatting slip silently confirming or flipping
    a stance. `fallback` only supplies bullets when the reply has none.
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
