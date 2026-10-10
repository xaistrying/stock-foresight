"""Macro Agent — quantitative macro signals for the debate engine.

All data via vnstock API or the existing OHLCV table. No scraping.
No language model: the reasoning is the four computed signal lines (Rule 5), not model
text (`retire-debate-round-two-and-model-prose`).

Signals:
1. VN-Index 20-session price trend (slope direction)
2. Ticker's own 20-session return relative to VN-Index over the same two dates
   (no sector index is available, so this is not a sector comparison)
3. USD/VND 5-session change
4. Market-wide foreign net buy/sell value, latest session (summed over 30 large caps);
   counted in the stance vote only once the board has settled after the close
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

from app.vnstock_guard import install as _install_vnstock_guard

_install_vnstock_guard()  # must precede any vnstock import (docs/KNOWN_ISSUES.md)

import numpy as np
import pandas as pd
from vnstock.api.trading import Trading  # noqa: E402
from vnstock.ui import Market  # noqa: E402

from app.db.connection import get_connection
from app.services.bulk_ingestion import _is_rate_limit_exit  # one definition of vnai's exit
from app.services.debate.engine import AgentPosition, Stance
from app.services.debate.news_feeds import ICT

logger = logging.getLogger(__name__)


def _load_ohlcv_closes(ticker: str, n: int) -> pd.Series:
    """Load last n closes for a ticker, ascending date, indexed by 'YYYY-MM-DD'."""
    conn = get_connection()
    try:
        # The outer ORDER BY must name `date`: `ORDER BY rowid` on the subquery
        # followed its DESC scan, returning newest-first and silently flipping
        # the sign of every return computed from `iloc[-1] / iloc[-20]`.
        rows = conn.execute(
            """
            SELECT date, close FROM (
                SELECT date, close FROM ohlcv WHERE ticker = ?
                ORDER BY date DESC LIMIT ?
            ) ORDER BY date ASC
            """,
            (ticker, n),
        ).fetchall()
    finally:
        conn.close()
    return pd.Series([r[1] for r in rows], index=[r[0] for r in rows], dtype="float64")


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
    """Daily closes from a vnstock 4.x Market handle (index / forex), or None,
    indexed by 'YYYY-MM-DD' with one row per date.

    Dates are kept so signal 2 can compare like with like. The live frame can
    repeat the latest session (same close, two rows, measured on VNINDEX), so the
    later row of a date wins: `series[date]` must be a scalar.
    """
    end = date.today()
    df = handle.ohlcv(
        start=(end - timedelta(days=MARKET_LOOKBACK_DAYS)).isoformat(), end=end.isoformat()
    )
    if df is None or df.empty or "close" not in df.columns:
        return None
    if "time" not in df.columns:
        # Raised, not guessed: a renamed column must show up in the log.
        raise KeyError(f"time column missing from market frame: {list(df.columns)[:6]}")
    closes = pd.Series(
        df["close"].astype("float64").to_numpy(),
        index=pd.to_datetime(df["time"]).dt.strftime("%Y-%m-%d"),
    )
    return closes[~closes.index.duplicated(keep="last")]


# Closes of the index fetched for signal 1 (last 20) and signal 2. The ticker's
# window ends d_last up to MAX_AGE_SESSIONS (3) sessions before yesterday, and the
# live frame may already hold today's bar: d_last is up to 5 closes from the end.
# Its 20 closes span 19 intervals plus up to MAX_MISSING_SESSIONS (2) sessions the
# ticker lacks, so d_first is up to 26 from the end. +1 slack.
VNINDEX_CLOSES = 27

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
# foreign turnover; below it the flow is "negligible" (neutral). Provisional: set
# from judgement, not backtested, and not covered by Rules 1-6.
FOREIGN_FLOW_RATIO_THRESHOLD = 0.10

# HOSE trades Mon-Fri 09:00-14:45 Vietnam time (matching, then ATC), with
# put-through until 15:00. Until the board settles its foreign values are
# cumulative-so-far and still moving: the same market read -9.2% of foreign
# turnover at 13:35, -18.4% at 14:48 and -24.5% from 15:12 on (identical at 15:12,
# 15:16, 15:17, 15:19 and 15:20, all Vietnam time) — enough to flip a verdict across
# the 10% threshold. So until then the figure informs the reasoning but does not
# vote. Where it settles inside 15:00-15:12 was not measured, so the margin runs to
# 15:15. Exchange holidays are not known here: on a weekday holiday this treats
# 09:00-15:15 as settling, which only withholds the vote from a final figure — the
# safe direction.
FOREIGN_FLOW_OPEN = time(9, 0)
FOREIGN_FLOW_SETTLED = time(15, 15)


def _foreign_flow_is_settling(now: datetime | None = None) -> bool:
    """True from the open until the board has settled after the close (see above).
    `now` must be timezone-aware: a naive value would be read in the server's own
    zone, which is not Vietnam's."""
    if now is not None and now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = (now or datetime.now(ICT)).astimezone(ICT)
    return now.weekday() < 5 and FOREIGN_FLOW_OPEN <= now.time() < FOREIGN_FLOW_SETTLED


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


def _signal_lines(signals: dict) -> list[str]:
    """The four signals as the agent's reasoning, one bullet each, in a fixed order."""
    return [
        f"VN-Index trend: {signals.get('vnindex_trend', 'unavailable')}",
        f"Relative performance: {signals.get('sector_vs_market', 'unavailable')}",
        f"USD/VND: {signals.get('usdvnd_change', 'unavailable')}",
        f"Market foreign flow (latest session): {signals.get('foreign_flow', 'unavailable')}",
    ]


class MacroAgent:
    async def run(self, ticker: str) -> AgentPosition:
        """Compute four macro signals, derive the stance; reasoning is the four signal lines."""
        signals: dict = {}
        votes: list[int] = []  # +1 bull, -1 bear, 0 neutral
        # Raw numbers for the outcome log, beside the prompt strings in `signals`.
        evidence: dict = {
            "vnindex_slope": None, "rel_vs_vnindex_pct": None, "usdvnd_change_pct": None,
            "foreign_net_vnd": None, "foreign_gross_vnd": None, "foreign_vote_counted": False,
        }

        # The market-data fetches are blocking network calls: off the event loop
        # (they froze the whole server for seconds per debate), and in parallel.
        # Read the clock BEFORE the fetches: each can take up to 20 s, and a board
        # read just before the settle time must not be labelled settled.
        settling = _foreign_flow_is_settling()
        vnindex, usdvnd, flow = await asyncio.gather(
            _bounded(_get_vnindex_closes, VNINDEX_CLOSES),
            _bounded(_get_usd_vnd_change, 5),
            _bounded(_get_market_foreign_flow),
        )

        # Signal 1: VN-Index trend
        if vnindex is not None and len(vnindex) >= 20:
            slope = _slope_sign(vnindex.tail(20))
            signals["vnindex_trend"] = {1: "up (+)", -1: "down (-)", 0: "flat"}[slope]
            evidence["vnindex_slope"] = slope
            votes.append(slope)
        else:
            signals["vnindex_trend"] = "unavailable"

        # Signal 2: the ticker's own return vs VN-Index (no sector index exists), over
        # the SAME two dates: the ticker's 20th-latest and latest stored closes. A
        # stale ticker is compared with the index on its own dates, never the index's
        # latest 20 positions; if the index lacks either date there is no vote.
        ticker_closes = await asyncio.to_thread(_load_ohlcv_closes, ticker, 22)  # blocking SQLite
        if len(ticker_closes) >= 20 and vnindex is not None:
            window = ticker_closes.iloc[-20:]
            d_first, d_last = window.index[0], window.index[-1]
            if d_first in vnindex.index and d_last in vnindex.index:
                ticker_ret = float(window.iloc[-1] / window.iloc[0] - 1) * 100
                vnindex_ret = float(vnindex[d_last] / vnindex[d_first] - 1) * 100
                rel = ticker_ret - vnindex_ret
                evidence["rel_vs_vnindex_pct"] = rel
                signals["sector_vs_market"] = f"{rel:+.2f}% relative to VN-Index ({d_first}..{d_last})"
                votes.append(1 if rel > 1 else (-1 if rel < -1 else 0))
            else:
                signals["sector_vs_market"] = (
                    f"unavailable (ticker window {d_first}..{d_last} not covered by the VN-Index data)"
                )
        else:
            signals["sector_vs_market"] = "unavailable"

        # Signal 3: USD/VND change
        if usdvnd is not None:
            signals["usdvnd_change"] = f"{usdvnd:+.2f}%"
            evidence["usdvnd_change_pct"] = usdvnd
            # Stronger USD = weaker VND = mildly bearish for stocks
            votes.append(-1 if usdvnd > 0.5 else (1 if usdvnd < -0.5 else 0))
        else:
            signals["usdvnd_change"] = "unavailable"

        # Signal 4: market-wide foreign flow (latest session). Mid-session it is a
        # partial, moving figure: shown for context, but only a final one votes.
        if flow is not None:
            net, gross = flow
            share = net / gross if gross else 0.0
            evidence.update(foreign_net_vnd=net, foreign_gross_vnd=gross, foreign_vote_counted=not settling)
            note = (
                "provisional: session in progress or just closed, not counted in the stance vote"
                if settling
                else "latest session, final"
            )
            signals["foreign_flow"] = (
                f"{net / 1e9:+.0f}B VND net foreign out of {gross / 1e9:.0f}B gross turnover ({note})"
            )
            if not settling:
                threshold = FOREIGN_FLOW_RATIO_THRESHOLD
                votes.append(1 if share > threshold else (-1 if share < -threshold else 0))
        else:
            signals["foreign_flow"] = "unavailable"

        # No counted signal is no stance at all, not a neutral one (design Decision 4).
        if not votes:
            return AgentPosition(
                agent_id="macro",
                stance="neutral",
                reasoning=["No macro signal was available — none of the four signals could be counted."],
                degraded_reason="no_input",
            )

        total = sum(votes)
        stance: Stance = "bull" if total > 0 else ("bear" if total < 0 else "neutral")

        return AgentPosition(agent_id="macro", stance=stance, reasoning=_signal_lines(signals), evidence=evidence)
