"""Tests for the Macro agent's market-data fetches (VN-Index, USD/VND).

The agent used vnstock's removed `Vnstock().stock/fx(...)` API, so every fetch
failed silently (logged at debug) and every debate said "unavailable". These
tests use a fake of the 4.x `Market` API, so nothing touches the network.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta

import pandas as pd
import pytest

from app.services.debate import macro as macro_mod


def _sessions(end, count):
    """`count` weekday date strings ending on `end` (inclusive), oldest first."""
    days, day = [], date.fromisoformat(end)
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    return days[::-1]


def _dated(values, end="2026-10-02"):
    """A close series indexed by date, like `_load_ohlcv_closes` / `_market_closes` return."""
    return pd.Series(values, index=_sessions(end, len(values)), dtype="float64")


def _fake_market(closes, *, error=None, calls=None):
    """A stand-in for vnstock.ui.Market: .index(sym) / .forex(sym) -> .ohlcv()."""

    class _Handle:
        def __init__(self, kind, symbol):
            self.kind, self.symbol = kind, symbol

        def ohlcv(self, start=None, end=None, **kwargs):
            if error:
                raise error
            if calls is not None:
                calls.append((self.kind, self.symbol, start, end))
            times = pd.to_datetime(_sessions(date.today().isoformat(), len(closes)))
            return pd.DataFrame({"time": times, "close": closes})

    class _FakeMarket:
        def index(self, symbol=None, **kwargs):
            return _Handle("index", symbol)

        def forex(self, symbol=None, **kwargs):
            return _Handle("forex", symbol)

    return _FakeMarket


@pytest.fixture
def no_stored_vnindex(monkeypatch):
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([], dtype="float64"))


# ---------------------------------------------------------------------------
# VN-Index
# ---------------------------------------------------------------------------

def test_vnindex_closes_come_from_the_market_api_with_a_window_wide_enough(monkeypatch, no_stored_vnindex):
    calls = []
    monkeypatch.setattr(macro_mod, "Market", _fake_market([float(i) for i in range(1, 61)], calls=calls))

    closes = macro_mod._get_vnindex_closes(22)

    assert list(closes) == [float(i) for i in range(39, 61)]  # the last 22
    kind, symbol, start, end = calls[0]
    assert (kind, symbol) == ("index", "VNINDEX")
    # 22 sessions need well over 22 calendar days (weekends, holidays).
    assert (date.fromisoformat(end) - date.fromisoformat(start)).days >= 40


def test_stored_vnindex_history_is_preferred_and_the_api_is_not_called(monkeypatch):
    calls = []
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([1.0] * n))
    monkeypatch.setattr(macro_mod, "Market", _fake_market([9.0] * 60, calls=calls))

    assert len(macro_mod._get_vnindex_closes(22)) == 22
    assert calls == []


def test_a_vnindex_fetch_failure_returns_none_and_is_logged_visibly(monkeypatch, no_stored_vnindex, caplog):
    monkeypatch.setattr(macro_mod, "Market", _fake_market([], error=RuntimeError("upstream exploded")))

    with caplog.at_level(logging.WARNING):
        assert macro_mod._get_vnindex_closes(22) is None

    # At WARNING, not debug: the failure was invisible for weeks.
    assert "upstream exploded" in caplog.text


# ---------------------------------------------------------------------------
# USD/VND
# ---------------------------------------------------------------------------

def test_usd_vnd_change_is_the_percentage_move_over_the_last_five_sessions(monkeypatch):
    calls = []
    closes = [25000.0, 25050.0, 25100.0, 25150.0, 25200.0, 25250.0, 25300.0]
    monkeypatch.setattr(macro_mod, "Market", _fake_market(closes, calls=calls))

    change = macro_mod._get_usd_vnd_change(5)

    assert change == pytest.approx((25300.0 / 25050.0 - 1) * 100)  # 6 closes = 5 moves
    assert calls[0][:2] == ("forex", "USDVND")


def test_a_usd_vnd_fetch_failure_returns_none_and_is_logged_visibly(monkeypatch, caplog):
    monkeypatch.setattr(macro_mod, "Market", _fake_market([], error=RuntimeError("fx feed down")))

    with caplog.at_level(logging.WARNING):
        assert macro_mod._get_usd_vnd_change(5) is None

    assert "fx feed down" in caplog.text


# ---------------------------------------------------------------------------
# The agent must not stall the event loop on those network calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_macro_agent_keeps_the_event_loop_responsive_during_market_data_fetches(monkeypatch):
    # These fetches are blocking network calls. Run on the loop thread they froze
    # the whole server for seconds per debate — long enough that a CLI waiting on
    # its stdin gave up (see llm_client.py).
    def slow_vnindex(n):
        time.sleep(0.3)
        return None

    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", slow_vnindex)
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: None)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: None)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([], dtype="float64"))

    agent = macro_mod.MacroAgent()

    async def llm_stub(messages):
        return "- stub"

    monkeypatch.setattr(agent._llm, "chat", llm_stub)

    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    beat = asyncio.create_task(heartbeat())
    await agent.run("SAB")
    beat.cancel()

    assert ticks >= 10  # ~30 expected over 0.3 s; ~0 when the loop is blocked


@pytest.mark.asyncio
async def test_relative_performance_is_described_as_the_tickers_own_return_not_a_sector(monkeypatch):
    # No sector index exists (_get_sector_closes is a placeholder), so this signal
    # is the ticker's own return against the index. Labelling it "sector" made the
    # LLM report "SAB's sector is outperforming".
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: _dated([100.0 + i for i in range(n)]))
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: _dated([100.0 + 3 * i for i in range(n)]))
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: 0.0)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: None)
    agent = macro_mod.MacroAgent()
    seen = []

    async def llm_stub(messages):
        seen.append(messages[-1]["content"])
        return "- stub"

    monkeypatch.setattr(agent._llm, "chat", llm_stub)

    await agent.run("SAB")

    assert "sector" not in seen[0].lower()
    assert "SAB's own 20-session return relative to VN-Index" in seen[0]


# ---------------------------------------------------------------------------
# Review fixes: real-SQLite ordering, and vnai's rate-limit sys.exit
# ---------------------------------------------------------------------------

@pytest.fixture
def ohlcv_db(tmp_path, monkeypatch):
    """A real SQLite file (every earlier test patched _load_ohlcv_closes away,
    which is how a newest-first result went unnoticed)."""
    import sqlite3

    path = tmp_path / "app.db"
    setup = sqlite3.connect(path)
    setup.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, close REAL)")
    # Inserted oldest-first; close == day number, so ascending order is checkable.
    setup.executemany(
        "INSERT INTO ohlcv VALUES (?, ?, ?)",
        [("SAB", f"2026-09-{d:02d}", float(d)) for d in range(1, 31)]
        + [("OTHER", f"2026-09-{d:02d}", 999.0) for d in range(1, 31)],
    )
    setup.commit()
    setup.close()
    monkeypatch.setattr(macro_mod, "get_connection", lambda: sqlite3.connect(path))


def test_ticker_closes_come_back_oldest_first_so_iloc_minus_one_is_the_latest(ohlcv_db):
    closes = macro_mod._load_ohlcv_closes("SAB", 22)

    assert list(closes) == [float(d) for d in range(9, 31)]  # the last 22 days, ascending
    assert closes.iloc[-1] == 30.0  # the latest session, not the oldest of the window


_RATE_LIMIT_EXIT = "Rate limit exceeded. 20 requests per minute. Process terminated."


@pytest.mark.parametrize("fetch", [lambda: macro_mod._get_vnindex_closes(22), lambda: macro_mod._get_usd_vnd_change(5)])
def test_vnais_rate_limit_exit_is_swallowed_by_the_market_fetchers(monkeypatch, no_stored_vnindex, caplog, fetch):
    # vnai's limiter calls sys.exit() (a SystemExit, which `except Exception`
    # misses); out of a worker thread it reaches the event loop and, under
    # uvicorn, ends the server. bulk_ingestion already handles it for loads.
    monkeypatch.setattr(macro_mod, "Market", _fake_market([], error=SystemExit(_RATE_LIMIT_EXIT)))

    with caplog.at_level(logging.WARNING):
        assert fetch() is None

    assert "rate limit" in caplog.text.lower()


def test_a_genuine_exit_request_is_still_honoured(monkeypatch, no_stored_vnindex):
    monkeypatch.setattr(macro_mod, "Market", _fake_market([], error=SystemExit("shutting down")))

    with pytest.raises(SystemExit):
        macro_mod._get_usd_vnd_change(5)


def test_a_database_error_reading_stored_vnindex_degrades_to_none(monkeypatch, caplog):
    def locked(ticker, n):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", locked)

    with caplog.at_level(logging.WARNING):
        assert macro_mod._get_vnindex_closes(22) is None

    assert "database is locked" in caplog.text


@pytest.mark.asyncio
async def test_macro_agent_survives_a_rate_limit_exit_with_every_signal_unavailable(monkeypatch, no_stored_vnindex):
    monkeypatch.setattr(macro_mod, "Market", _fake_market([], error=SystemExit(_RATE_LIMIT_EXIT)))
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: None)
    agent = macro_mod.MacroAgent()
    seen = []

    async def llm_stub(messages):
        seen.append(messages[-1]["content"])
        return "- stub"

    monkeypatch.setattr(agent._llm, "chat", llm_stub)

    position = await agent.run("SAB")  # must not raise or end the process

    assert position.degraded_reason == "no_input"
    assert seen == []  # nothing to explain, so no LLM call


# ---------------------------------------------------------------------------
# Market-wide foreign flow (replaces the per-ticker call that never worked)
# ---------------------------------------------------------------------------

def _fake_trading(frame=None, *, error=None, calls=None):
    """A stand-in for vnstock.api.trading.Trading with a VCI-shaped price board."""

    class _FakeTrading:
        def __init__(self, source="kbs", symbol=None, **kwargs):
            self.source = source

        def price_board(self, symbols_list=None, **kwargs):
            if error:
                raise error
            if calls is not None:
                calls.append((self.source, list(symbols_list)))
            return frame

    return _FakeTrading


def _board(buy_values, sell_values):
    columns = pd.MultiIndex.from_tuples(
        [("match", "foreign_buy_value"), ("match", "foreign_sell_value")]
    )
    return pd.DataFrame(list(zip(buy_values, sell_values)), columns=columns)


def test_market_foreign_flow_sums_net_and_gross_value_across_the_sample(monkeypatch):
    calls = []
    board = _board([100e9, 200e9, None], [60e9, 340e9, None])  # a symbol with no trades is NaN
    monkeypatch.setattr(macro_mod, "Trading", _fake_trading(board, calls=calls))

    net, gross = macro_mod._get_market_foreign_flow()

    assert net == pytest.approx((100e9 + 200e9) - (60e9 + 340e9))  # -100e9
    assert gross == pytest.approx(100e9 + 200e9 + 60e9 + 340e9)
    assert calls[0][0] == "vci"  # the source that has foreign *values* (kbs has volumes only)
    assert calls[0][1] == list(macro_mod.FOREIGN_FLOW_SAMPLE)


def test_a_board_without_foreign_value_columns_gives_none_and_says_so(monkeypatch, caplog):
    # A vnstock upgrade that renames the columns would otherwise leave the signal
    # "unavailable" forever with nothing in the log.
    monkeypatch.setattr(macro_mod, "_WARNED_ONCE", set())
    monkeypatch.setattr(macro_mod, "Trading", _fake_trading(pd.DataFrame({"symbol": ["ACB"]})))

    with caplog.at_level(logging.WARNING):
        assert macro_mod._get_market_foreign_flow() is None

    assert "foreign" in caplog.text.lower() and "column" in caplog.text.lower()


def test_flattened_column_names_are_understood_too(monkeypatch):
    # vnstock can return flattened names ("match_foreign_buy_value").
    frame = pd.DataFrame({"match_foreign_buy_value": [30e9], "match_foreign_sell_value": [10e9]})
    monkeypatch.setattr(macro_mod, "Trading", _fake_trading(frame))

    assert macro_mod._get_market_foreign_flow() == (20e9, 40e9)


def test_a_board_with_no_foreign_turnover_is_unavailable_not_a_zero_reading(monkeypatch):
    # Pre-open or a holiday: nothing has traded. "+0B net foreign" would read as a
    # measured, flat flow rather than no information.
    monkeypatch.setattr(macro_mod, "Trading", _fake_trading(_board([0, 0], [0, 0])))

    assert macro_mod._get_market_foreign_flow() is None


def test_foreign_flow_failures_warn_once_per_process_then_stay_quiet(monkeypatch, caplog):
    monkeypatch.setattr(macro_mod, "_WARNED_ONCE", set())
    monkeypatch.setattr(macro_mod, "Trading", _fake_trading(error=RuntimeError("board down")))

    with caplog.at_level(logging.DEBUG):
        assert macro_mod._get_market_foreign_flow() is None
        assert macro_mod._get_market_foreign_flow() is None
        assert macro_mod._get_market_foreign_flow() is None

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "board down" in warnings[0].getMessage()


def test_foreign_flow_swallows_vnais_rate_limit_exit(monkeypatch):
    monkeypatch.setattr(macro_mod, "_WARNED_ONCE", set())
    monkeypatch.setattr(macro_mod, "Trading", _fake_trading(error=SystemExit(_RATE_LIMIT_EXIT)))

    assert macro_mod._get_market_foreign_flow() is None


async def _macro_prompt(monkeypatch, flow, *, in_session=False, usdvnd=None):
    monkeypatch.setattr(macro_mod, "_foreign_flow_is_settling", lambda now=None: in_session)
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: None)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([], dtype="float64"))
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: usdvnd)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: flow)
    agent = macro_mod.MacroAgent()
    seen = []

    async def llm_stub(messages):
        seen.append(messages[-1]["content"])
        return "- stub"

    monkeypatch.setattr(agent._llm, "chat", llm_stub)
    position = await agent.run("SAB")
    return position, seen[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "net, gross, stance",
    [
        (-95.4e9, 601.3e9, "bear"),  # net outflow, -15.9% of foreign turnover
        (80e9, 400e9, "bull"),  # net inflow, +20%
        (5e9, 400e9, "neutral"),  # +1.25%: negligible
    ],
)
async def test_market_foreign_flow_votes_by_its_share_of_foreign_turnover(monkeypatch, net, gross, stance):
    position, prompt = await _macro_prompt(monkeypatch, (net, gross))

    assert position.stance == stance
    # Described as what it is: market-wide, latest session, a sample of large caps.
    assert "Market-wide foreign net flow" in prompt
    assert "latest session" in prompt and "large caps" in prompt
    assert f"{net / 1e9:+.0f}B VND" in prompt


@pytest.mark.asyncio
async def test_unavailable_foreign_flow_casts_no_vote(monkeypatch):
    position, prompt = await _macro_prompt(monkeypatch, None, usdvnd=0.0)  # one other signal keeps it live

    assert position.stance == "neutral"
    assert "Market-wide foreign net flow, latest session (30 large caps): unavailable" in prompt


@pytest.mark.asyncio
async def test_a_closed_session_foreign_flow_shows_its_scale_and_is_marked_final(monkeypatch):
    _, prompt = await _macro_prompt(monkeypatch, (-90.6e9, 637.6e9))

    assert "-91B VND net foreign out of 638B gross turnover (latest session, final)" in prompt


@pytest.mark.asyncio
async def test_a_market_data_source_that_hangs_cannot_stall_the_agent(monkeypatch):
    # vnstock retries with long timeouts; a hung source could hold the whole debate
    # for minutes. Each fetch gets a deadline and degrades to "unavailable".
    monkeypatch.setattr(macro_mod, "MARKET_FETCH_TIMEOUT_SECONDS", 0.1)

    def hangs(n):
        time.sleep(1.0)

    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", hangs)
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: 0.0)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: None)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([], dtype="float64"))
    agent = macro_mod.MacroAgent()
    seen = []

    async def llm_stub(messages):
        seen.append(messages[-1]["content"])
        return "- stub"

    monkeypatch.setattr(agent._llm, "chat", llm_stub)

    started = time.monotonic()
    await agent.run("SAB")

    assert time.monotonic() - started < 0.8  # not the 1 s the fetch takes
    assert "VN-Index 20-session trend: unavailable" in seen[0]


@pytest.mark.asyncio
async def test_foreign_flow_during_the_session_is_shown_but_casts_no_vote(monkeypatch):
    # -15% of foreign turnover would vote bearish, but mid-session the figure keeps
    # moving: the same debate re-run an hour later flipped a verdict (-9.2% at
    # 14:35, -18.4% at 15:48, -24.5% at the close). Partial data is context, not a vote.
    position, prompt = await _macro_prompt(monkeypatch, (-90e9, 600e9), in_session=True, usdvnd=0.0)

    assert position.stance == "neutral"  # the only vote is a flat USD/VND
    assert "-90B VND net foreign out of 600B gross turnover" in prompt
    assert "session in progress" in prompt and "not counted in the stance vote" in prompt


@pytest.mark.asyncio
async def test_the_same_flow_votes_once_the_session_has_closed(monkeypatch):
    position, _ = await _macro_prompt(monkeypatch, (-90e9, 600e9), in_session=False)

    assert position.stance == "bear"


@pytest.mark.parametrize(
    "when, expected",
    [
        ("2026-10-05T09:00:00+07:00", True),   # Monday, opening
        ("2026-10-05T14:59:00+07:00", True),   # Monday, last minute of the session
        ("2026-10-05T15:00:00+07:00", True),   # closed, but the board is still settling
        ("2026-10-05T15:14:00+07:00", True),
        ("2026-10-05T15:15:00+07:00", False),  # settled: stable at 15:12-15:20 when measured
        ("2026-10-05T08:59:00+07:00", False),  # before the open: the board holds the last final session
        ("2026-10-05T03:00:00+00:00", True),   # 10:00 in Vietnam, given in UTC
        ("2026-10-03T11:00:00+07:00", False),  # Saturday
        ("2026-10-04T11:00:00+07:00", False),  # Sunday
    ],
)
def test_foreign_flow_is_settling_follows_weekday_trading_hours_in_vietnam_time(when, expected):
    from datetime import datetime

    assert macro_mod._foreign_flow_is_settling(datetime.fromisoformat(when)) is expected


def test_a_naive_datetime_is_rejected_rather_than_read_in_the_servers_own_timezone():
    from datetime import datetime

    with pytest.raises(ValueError, match="timezone-aware"):
        macro_mod._foreign_flow_is_settling(datetime(2026, 10, 5, 10, 0))


@pytest.mark.asyncio
async def test_the_clock_is_read_before_the_fetch_not_after(monkeypatch):
    # A fetch can take up to 20 s: a board read at 14:59:50 must not be labelled
    # settled because the clock was checked at 15:15:05 afterwards.
    order = []
    monkeypatch.setattr(macro_mod, "_foreign_flow_is_settling", lambda now=None: order.append("clock") or True)

    def fetch():
        order.append("fetch")
        return (-90e9, 600e9)

    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", fetch)
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: None)
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: None)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([], dtype="float64"))
    agent = macro_mod.MacroAgent()

    async def llm_stub(messages):
        return "- stub"

    monkeypatch.setattr(agent._llm, "chat", llm_stub)

    await agent.run("SAB")

    assert order == ["clock", "fetch"]


def test_the_reasoning_prompt_forbids_inferring_a_direction_from_a_provisional_signal():
    # The withheld vote only binds the stance; the LLM's bullets feed Round 2 and
    # the verdict, so it must not lean on a signal marked "not counted" either.
    assert "not counted in the stance vote" in macro_mod._REASONING_PROMPT
    assert "do not infer a direction" in macro_mod._REASONING_PROMPT.lower()


@pytest.mark.asyncio
async def test_the_round_two_prompt_says_provisional_data_must_not_move_the_stance(monkeypatch):
    from app.services.debate.engine import AgentPosition

    agent = macro_mod.MacroAgent()
    seen = []

    async def llm_stub(messages):
        seen.append(messages[-1]["content"])
        return "neutral\n- stub"

    monkeypatch.setattr(agent._llm, "chat", llm_stub)
    round1 = {a: AgentPosition(a, "neutral", ["x"]) for a in ("technical", "news", "macro")}

    await agent.respond("SAB", round1)

    assert "provisional" in seen[0].lower() and "not" in seen[0].lower()


# ---------------------------------------------------------------------------
# Signal 2 compares the same two dates; the index frame keeps its dates
# ---------------------------------------------------------------------------

def test_market_closes_keep_their_dates_and_one_row_per_date():
    # The live VN-Index frame repeats the latest session (same close, two rows).
    frame = pd.DataFrame({
        "time": pd.to_datetime(["2026-10-05 07:00", "2026-10-06 07:00", "2026-10-06 07:00"]),
        "close": [1753.2, 1759.0, 1759.08],
    })

    class _Handle:
        def ohlcv(self, **kwargs):
            return frame

    closes = macro_mod._market_closes(_Handle())

    assert list(closes.index) == ["2026-10-05", "2026-10-06"]
    assert closes["2026-10-06"] == 1759.08  # the later row wins


def test_a_frame_without_a_time_column_is_reported_not_guessed(monkeypatch, no_stored_vnindex, caplog):
    class _Handle:
        def ohlcv(self, **kwargs):
            return pd.DataFrame({"close": [1.0, 2.0]})

    class _Market:
        def index(self, symbol=None, **kwargs):
            return _Handle()

    monkeypatch.setattr(macro_mod, "Market", _Market)

    with caplog.at_level(logging.WARNING):
        assert macro_mod._get_vnindex_closes(22) is None

    assert "time" in caplog.text


async def _signal2(monkeypatch, vnindex, ticker, *, llm_reply="- stub"):
    """Run the agent with USD/VND at -1% (one bullish vote) and return (position, prompt)."""
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: vnindex)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: ticker)
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: -1.0)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: None)
    agent = macro_mod.MacroAgent()
    seen = []

    async def llm_stub(messages):
        seen.append(messages[-1]["content"])
        return llm_reply

    monkeypatch.setattr(agent._llm, "chat", llm_stub)
    return await agent.run("SAB"), seen[0]


@pytest.mark.asyncio
async def test_relative_return_uses_the_tickers_two_dates_not_the_indexs_last_20_positions(monkeypatch):
    # The stored ticker ends 2026-10-02; the live index runs 3 sessions further.
    ticker = _dated([100.0 + i for i in range(22)], end="2026-10-02")
    index = _dated([1000.0 + j ** 2 for j in range(25)], end="2026-10-07")
    d_first, d_last = ticker.index[-20], ticker.index[-1]

    _, prompt = await _signal2(monkeypatch, index, ticker)

    # by date: ticker +18.63%, index 2 -> 21: +43.53%  => -24.90%
    # by position (the old bug): index 5 -> 24: +53.76% => -35.13%
    assert "-24.90% relative to VN-Index" in prompt
    assert "-35.13" not in prompt
    assert f"{d_first}..{d_last}" in prompt  # the signal text names both dates


@pytest.mark.asyncio
async def test_an_index_that_misses_an_endpoint_casts_no_vote_and_says_so(monkeypatch):
    ticker = _dated([100.0 + i for i in range(22)], end="2026-10-02")
    index = _dated([1000.0 + j for j in range(10)], end="2026-10-02")  # starts after d_first
    d_first, d_last = ticker.index[-20], ticker.index[-1]
    note = f"ticker window {d_first}..{d_last} not covered by the VN-Index data"

    position, prompt = await _signal2(monkeypatch, index, ticker)

    assert note in prompt
    assert any(note in bullet for bullet in position.reasoning)  # not left to the LLM's wording
    assert position.stance == "bull" and position.degraded_reason is None  # only USD/VND voted


@pytest.mark.asyncio
async def test_a_missing_endpoint_is_stated_once_even_when_the_llm_is_down(monkeypatch):
    ticker = _dated([100.0 + i for i in range(22)], end="2026-10-02")
    index = _dated([1000.0 + j for j in range(10)], end="2026-10-02")
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: index)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: ticker)
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: -1.0)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: None)
    agent = macro_mod.MacroAgent()

    async def llm_down(messages):
        raise RuntimeError("llm down")

    monkeypatch.setattr(agent._llm, "chat", llm_down)

    position = await agent.run("SAB")

    assert sum("not covered by the VN-Index data" in bullet for bullet in position.reasoning) == 1


# ---------------------------------------------------------------------------
# No counted signal: degraded, not neutral
# ---------------------------------------------------------------------------

async def _run_with(monkeypatch, *, vnindex=None, usdvnd=None, flow=None, settling=False):
    monkeypatch.setattr(macro_mod, "_foreign_flow_is_settling", lambda now=None: settling)
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: vnindex)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([], dtype="float64"))
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: usdvnd)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: flow)
    agent = macro_mod.MacroAgent()
    calls = []

    async def llm_stub(messages):
        calls.append(messages)
        return "- stub"

    monkeypatch.setattr(agent._llm, "chat", llm_stub)
    return await agent.run("SAB"), calls


@pytest.mark.asyncio
async def test_every_fetch_failing_degrades_macro_with_no_input(monkeypatch):
    position, calls = await _run_with(monkeypatch)

    assert position.degraded_reason == "no_input"
    assert "no macro signal was available" in position.reasoning[0].lower()
    assert calls == []


@pytest.mark.asyncio
async def test_a_provisional_foreign_flow_alone_counts_for_nothing(monkeypatch):
    position, _ = await _run_with(monkeypatch, flow=(-90e9, 600e9), settling=True)

    assert position.degraded_reason == "no_input"


@pytest.mark.asyncio
async def test_one_counted_signal_keeps_macro_live(monkeypatch):
    position, calls = await _run_with(monkeypatch, usdvnd=-1.0)

    assert (position.stance, position.degraded_reason) == ("bull", None)
    assert len(calls) == 1
