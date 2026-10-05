"""Macro Agent — quantitative macro signals for the debate engine.

All data via vnstock API or the existing OHLCV table. No scraping.
LLM is used only to translate computed numeric signals into readable bullets.

Signals:
1. VN-Index 20-session price trend (slope direction)
2. Ticker's own 20-session return relative to VN-Index (no sector index is
   available, so this is not a sector comparison)
3. USD/VND 5-session change
4. Market-wide foreign net buy/sell value, latest session (summed over 30 large caps)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from datetime import date, timedelta

from app.vnstock_guard import install as _install_vnstock_guard

_install_vnstock_guard()  # must precede any vnstock import (docs/KNOWN_ISSUES.md)

import numpy as np
import pandas as pd
from vnstock.api.trading import Trading  # noqa: E402
from vnstock.ui import Market  # noqa: E402

from app.db.connection import get_connection
from app.services.bulk_ingestion import _is_rate_limit_exit  # one definition of vnai's exit
from app.services.debate.engine import AgentPosition, Stance
from app.services.debate.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _load_ohlcv_closes(ticker: str, n: int) -> pd.Series:
    """Load last n closes for a ticker, ascending date."""
    conn = get_connection()
    try:
        # The outer ORDER BY must name `date`: `ORDER BY rowid` on the subquery
        # followed its DESC scan, returning newest-first and silently flipping
        # the sign of every return computed from `iloc[-1] / iloc[-20]`.
        rows = conn.execute(
            """
            SELECT close FROM (
                SELECT date, close FROM ohlcv WHERE ticker = ?
                ORDER BY date DESC LIMIT ?
            ) ORDER BY date ASC
            """,
            (ticker, n),
        ).fetchall()
    finally:
        conn.close()
    return pd.Series([r[0] for r in rows], dtype="float64")


def _slope_sign(series: pd.Series) -> int:
    """+1 if trending up, -1 if trending down, 0 if flat."""
    if len(series) < 2:
        return 0
    x = np.arange(len(series))
    slope = np.polyfit(x, series.values, 1)[0]
    if slope > series.mean() * 0.0005:
        return 1
    if slope < -series.mean() * 0.0005:
        return -1
    return 0


# Calendar days to request for a handful of sessions: weekends and holidays mean
# 22 sessions span ~35 calendar days; this leaves headroom.
MARKET_LOOKBACK_DAYS = 90


def _market_closes(handle) -> pd.Series | None:
    """Daily closes from a vnstock 4.x Market handle (index / forex), or None."""
    end = date.today()
    df = handle.ohlcv(
        start=(end - timedelta(days=MARKET_LOOKBACK_DAYS)).isoformat(), end=end.isoformat()
    )
    if df is None or df.empty or "close" not in df.columns:
        return None
    return df["close"].astype("float64").reset_index(drop=True)


# vnstock retries with long timeouts, so a hung source could hold a debate for
# minutes; each fetch gets a deadline and degrades to "unavailable". (The worker
# thread is abandoned, not killed, and finishes on its own.)
MARKET_FETCH_TIMEOUT_SECONDS = 20


async def _bounded(fetch, *args):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fetch, *args), timeout=MARKET_FETCH_TIMEOUT_SECONDS
        )
    except TimeoutError:
        logger.warning("%s timed out after %ss", fetch.__name__, MARKET_FETCH_TIMEOUT_SECONDS)
        return None


_WARNED_ONCE: set[str] = set()


def _log_failure(what: str, detail: str, once: bool) -> None:
    # `once`: warn the first time per process, then debug. A fetch that is down for
    # good would otherwise add a warning to every debate; fully silent is what hid
    # the broken VN-Index/USD-VND fetches for weeks.
    if once and what in _WARNED_ONCE:
        logger.debug("%s %s", what, detail)
        return
    _WARNED_ONCE.add(what)
    logger.warning("%s %s", what, detail)


@contextmanager
def _soft_fail(what: str, *, once: bool = False):
    """Let a market-data fetch fail soft: log it and fall through to `return None`.

    Also swallows vnai's rate-limit `sys.exit()`. That is a SystemExit, which
    `except Exception` misses; raised in a worker thread it reaches the event
    loop through `asyncio.to_thread` and ends the server (bulk_ingestion handles
    the same exit for loads). Any other SystemExit is a real exit request.
    """
    try:
        yield
    except Exception as exc:
        _log_failure(what, f"fetch failed: {exc}", once)
    except SystemExit as exit_request:
        if not _is_rate_limit_exit(exit_request):
            raise
        _log_failure(what, f"fetch hit vnai's rate limit: {exit_request.code}", once)


def _get_vnindex_closes(n: int) -> pd.Series | None:
    """Get VN-Index closes from OHLCV; fetch from vnstock API if absent."""
    with _soft_fail("VN-Index"):
        closes = _load_ohlcv_closes("VNINDEX", n)
        if len(closes) >= n:
            return closes

        # Fallback: vnstock 4.x Market API. (The old Vnstock().stock(...) API this
        # used raised RetryError for an index, hidden by a debug-level log.)
        closes = _market_closes(Market().index("VNINDEX"))
        return closes.tail(n) if closes is not None else None
    return None


def _get_sector_closes(ticker: str, n: int) -> pd.Series | None:
    """Get closes for the ticker's ICB sector index if available."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT icb_code2 FROM ticker_universe WHERE symbol = ?", (ticker,)
        ).fetchone()
        if not row or not row[0]:
            return None
        # Proxy: use the ticker's own OHLCV (we don't have sector index in DB)
        # A proper implementation would load a basket of sector peers.
        return None
    finally:
        conn.close()


# Large caps whose summed foreign trading stands in for market-wide foreign flow.
# vnstock's free providers implement no foreign-trade history for the index or any
# ticker (foreign_trade raises NotImplementedError; the index quote's foreign fields
# are zeros), but VCI's price board returns each stock's foreign buy/sell *value* for
# the latest session. The VN30 membership as of writing; a sample, so refresh it
# when the index is reviewed.
FOREIGN_FLOW_SAMPLE = (
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
)
# Net flow counts as inflow/outflow only beyond this share of the sample's gross
# foreign turnover; below it the flow is "negligible" (neutral). Provisional, like
# Rule 3's 0.5: set from judgement, not backtested.
FOREIGN_FLOW_RATIO_THRESHOLD = 0.10


def _board_column(board: pd.DataFrame, name: str) -> pd.Series | None:
    """A price-board column by leaf name (VCI's columns are ('match', name))."""
    for column in board.columns:
        leaf = column[-1] if isinstance(column, tuple) else column
        if str(leaf).endswith(name):  # ('match', name) or a flattened 'match_<name>'
            return pd.to_numeric(board[column], errors="coerce").fillna(0.0)
    return None


def _get_market_foreign_flow() -> tuple[float, float] | None:
    """(net, gross) foreign trading value in VND over FOREIGN_FLOW_SAMPLE for the
    latest session — partial if the market is open. None if unavailable.
    Includes negotiated (put-through) deals, as the exchange's own figures do, so
    one block trade can move it.

    Latest session only: the free API returns no history. A rolling 5-10 session
    figure would need daily snapshots stored; until then the press-reported weekly
    figure reaches the debate through the News agent (news_feeds.FOREIGN_SLOTS).
    """
    with _soft_fail("Market foreign flow", once=True):
        board = Trading(source="vci").price_board(symbols_list=list(FOREIGN_FLOW_SAMPLE))
        buy = _board_column(board, "foreign_buy_value")
        sell = _board_column(board, "foreign_sell_value")
        if buy is None or sell is None:
            # Raised, not returned: a renamed column would otherwise leave the
            # signal "unavailable" forever without a trace in the log.
            raise KeyError(f"foreign value columns missing from price board: {list(board.columns)[:6]}")
        gross = float(buy.sum() + sell.sum())
        if gross == 0:  # pre-open or a holiday: no information, not a flat reading
            return None
        return float(buy.sum() - sell.sum()), gross
    return None


def _get_usd_vnd_change(n: int) -> float | None:
    """Get the USD/VND % change over the last n sessions (vnstock 4.x forex API)."""
    with _soft_fail("USD/VND"):
        closes = _market_closes(Market().forex("USDVND"))
        if closes is not None:
            closes = closes.tail(n + 1)
            if len(closes) >= 2:
                return float((closes.iloc[-1] / closes.iloc[0] - 1) * 100)
    return None


_REASONING_PROMPT = """\
You are a macro analysis assistant for Vietnamese stocks. Given these computed
macro signals, produce 3-4 plain-language bullet points (each starting with "- ")
explaining the macro environment. Translate the numbers into readable insights.
Do NOT add any macro context beyond the provided values.

Ticker: {ticker}
Overall macro stance: {stance}

Computed signals:
- VN-Index 20-session trend: {vnindex_trend}
- {ticker}'s own 20-session return relative to VN-Index: {sector_vs_market}
- USD/VND 5-session change: {usdvnd_change}
- Market-wide foreign net flow, latest session ({sample} large caps): {foreign_flow}
"""


class MacroAgent:
    def __init__(self) -> None:
        self._llm = LLMClient()

    async def run(self, ticker: str) -> AgentPosition:
        """Round 1: compute four macro signals, derive stance, generate reasoning."""
        signals: dict = {}
        votes: list[int] = []  # +1 bull, -1 bear, 0 neutral

        # The market-data fetches are blocking network calls: off the event loop
        # (they froze the whole server for seconds per debate), and in parallel.
        vnindex, usdvnd, flow = await asyncio.gather(
            _bounded(_get_vnindex_closes, 22),
            _bounded(_get_usd_vnd_change, 5),
            _bounded(_get_market_foreign_flow),
        )

        # Signal 1: VN-Index trend
        if vnindex is not None and len(vnindex) >= 20:
            slope = _slope_sign(vnindex.tail(20))
            signals["vnindex_trend"] = {1: "up (+)", -1: "down (-)", 0: "flat"}[slope]
            votes.append(slope)
        else:
            signals["vnindex_trend"] = "unavailable"

        # Signal 2: Sector relative (placeholder — using ticker own return vs VNINDEX)
        ticker_closes = _load_ohlcv_closes(ticker, 22)
        if len(ticker_closes) >= 20 and vnindex is not None and len(vnindex) >= 20:
            ticker_ret = float(ticker_closes.iloc[-1] / ticker_closes.iloc[-20] - 1) * 100
            vnindex_ret = float(vnindex.iloc[-1] / vnindex.iloc[-20] - 1) * 100
            rel = ticker_ret - vnindex_ret
            signals["sector_vs_market"] = f"{rel:+.2f}% relative to VN-Index"
            votes.append(1 if rel > 1 else (-1 if rel < -1 else 0))
        else:
            signals["sector_vs_market"] = "unavailable"

        # Signal 3: USD/VND change
        if usdvnd is not None:
            signals["usdvnd_change"] = f"{usdvnd:+.2f}%"
            # Stronger USD = weaker VND = mildly bearish for stocks
            votes.append(-1 if usdvnd > 0.5 else (1 if usdvnd < -0.5 else 0))
        else:
            signals["usdvnd_change"] = "unavailable"

        # Signal 4: market-wide foreign flow (latest session)
        if flow is not None:
            net, gross = flow
            share = net / gross if gross else 0.0
            signals["foreign_flow"] = (
                f"{net / 1e9:+.0f}B VND net foreign out of {gross / 1e9:.0f}B gross turnover "
                "(partial if the market is open)"
            )
            threshold = FOREIGN_FLOW_RATIO_THRESHOLD
            votes.append(1 if share > threshold else (-1 if share < -threshold else 0))
        else:
            signals["foreign_flow"] = "unavailable"

        # Majority vote
        if votes:
            total = sum(votes)
            stance: Stance = "bull" if total > 0 else ("bear" if total < 0 else "neutral")
        else:
            stance = "neutral"

        reasoning = await self._generate_reasoning(ticker, stance, signals)
        return AgentPosition(agent_id="macro", stance=stance, reasoning=reasoning)

    async def respond(self, ticker: str, round1: dict) -> AgentPosition:
        """Round 2: review other positions and maintain/update macro stance."""
        my_r1 = round1.get("macro")
        others = {k: v for k, v in round1.items() if k != "macro"}
        other_lines = "\n".join(
            f"- {k.capitalize()} agent ({v.stance}): {'; '.join(v.reasoning[:2])}"
            for k, v in others.items()
        )
        prompt = f"""\
You are the Macro agent. Your Round 1 stance was: {my_r1.stance if my_r1 else "neutral"}.
Your Round 1 reasoning: {'; '.join(my_r1.reasoning[:3]) if my_r1 else "N/A"}

Other agents' positions:
{other_lines}

Maintain your stance unless a specific counter-argument from the other agents
is compelling. Respond: first line = bull/bear/neutral, then 3-4 bullet points.
"""
        response = await self._llm.chat([
            {"role": "system", "content": "You are a disciplined macro analyst."},
            {"role": "user", "content": prompt},
        ])
        from app.services.debate.technical import _parse_stance_and_bullets
        stance, reasoning = _parse_stance_and_bullets(response, my_r1)
        return AgentPosition(agent_id="macro", stance=stance, reasoning=reasoning)

    async def _generate_reasoning(
        self, ticker: str, stance: Stance, signals: dict
    ) -> list[str]:
        prompt = _REASONING_PROMPT.format(
            ticker=ticker,
            stance=stance,
            vnindex_trend=signals.get("vnindex_trend", "unavailable"),
            sector_vs_market=signals.get("sector_vs_market", "unavailable"),
            usdvnd_change=signals.get("usdvnd_change", "unavailable"),
            foreign_flow=signals.get("foreign_flow", "unavailable"),
            sample=len(FOREIGN_FLOW_SAMPLE),
        )
        try:
            response = await self._llm.chat([
                {"role": "system", "content": "You are a concise macro analysis assistant."},
                {"role": "user", "content": prompt},
            ])
            bullets = [
                line.strip().lstrip("- ").strip()
                for line in response.splitlines()
                if line.strip().startswith("-")
            ]
            if bullets:
                return bullets[:4]
        except Exception as exc:
            logger.warning("MacroAgent LLM call failed: %s", exc)
        return [
            f"VN-Index trend: {signals.get('vnindex_trend', 'unavailable')}",
            f"Relative performance: {signals.get('sector_vs_market', 'unavailable')}",
            f"USD/VND: {signals.get('usdvnd_change', 'unavailable')}",
            f"Market foreign flow (latest session): {signals.get('foreign_flow', 'unavailable')}",
        ]
