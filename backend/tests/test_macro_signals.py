"""Tests for the Macro agent's market-data fetches (VN-Index, USD/VND).

The agent used vnstock's removed `Vnstock().stock/fx(...)` API, so every fetch
failed silently (logged at debug) and every debate said "unavailable". These
tests use a fake of the 4.x `Market` API, so nothing touches the network.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date

import pandas as pd
import pytest

from app.services.debate import macro as macro_mod


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
            return pd.DataFrame({"time": range(len(closes)), "close": closes})

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
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: pd.Series([100.0 + i for i in range(n)]))
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([100.0 + 3 * i for i in range(n)]))
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

    position = await agent.run("SAB")

    assert position.stance == "neutral"
    assert "VN-Index 20-session trend: unavailable" in seen[0]
    assert "USD/VND 5-session change: unavailable" in seen[0]


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


async def _macro_prompt(monkeypatch, flow):
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: None)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([], dtype="float64"))
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: None)
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
    position, prompt = await _macro_prompt(monkeypatch, None)

    assert position.stance == "neutral"
    assert "Market-wide foreign net flow, latest session (30 large caps): unavailable" in prompt


@pytest.mark.asyncio
async def test_the_foreign_flow_signal_shows_its_scale_and_that_it_may_be_partial(monkeypatch):
    _, prompt = await _macro_prompt(monkeypatch, (-90.6e9, 637.6e9))

    assert "-91B VND net foreign out of 638B gross turnover" in prompt
    assert "partial if the market is open" in prompt


@pytest.mark.asyncio
async def test_a_market_data_source_that_hangs_cannot_stall_the_agent(monkeypatch):
    # vnstock retries with long timeouts; a hung source could hold the whole debate
    # for minutes. Each fetch gets a deadline and degrades to "unavailable".
    monkeypatch.setattr(macro_mod, "MARKET_FETCH_TIMEOUT_SECONDS", 0.1)

    def hangs(n):
        time.sleep(1.0)

    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", hangs)
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: None)
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
