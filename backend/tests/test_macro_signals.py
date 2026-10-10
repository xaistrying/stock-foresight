"""Tests for the Macro agent's market-data fetches (VN-Index, USD/VND) and its values list.

The agent makes no language-model call: its reasoning is the four signal lines
(`retire-debate-round-two-and-model-prose`).

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
    # No sector index exists, so this signal is the ticker's own return against the
    # index. Calling it "sector" would read as "SAB's sector is outperforming".
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: _dated([100.0 + i for i in range(n)]))
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: _dated([100.0 + 3 * i for i in range(n)]))
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: 0.0)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: None)

    position = await macro_mod.MacroAgent().run("SAB")

    relative = position.reasoning[1]
    assert relative.startswith("Relative performance: ") and "relative to VN-Index" in relative
    assert "sector" not in " ".join(position.reasoning).lower()


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

    position = await agent.run("SAB")  # must not raise or end the process

    assert position.degraded_reason == "no_input"


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


async def _macro_bullets(monkeypatch, flow, *, in_session=False, usdvnd=None):
    """Run the agent with only the foreign-flow and USD/VND signals; return (position, its bullets as text)."""
    monkeypatch.setattr(macro_mod, "_foreign_flow_is_settling", lambda now=None: in_session)
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: None)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([], dtype="float64"))
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: usdvnd)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: flow)
    position = await macro_mod.MacroAgent().run("SAB")
    return position, "\n".join(position.reasoning)


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
    position, text = await _macro_bullets(monkeypatch, (net, gross))

    assert position.stance == stance
    # Described as what it is: market-wide, latest session.
    assert "Market foreign flow (latest session): " in text
    assert f"{net / 1e9:+.0f}B VND" in text


@pytest.mark.asyncio
async def test_unavailable_foreign_flow_casts_no_vote(monkeypatch):
    position, text = await _macro_bullets(monkeypatch, None, usdvnd=0.0)  # one other signal keeps it live

    assert position.stance == "neutral"
    assert "Market foreign flow (latest session): unavailable" in position.reasoning


@pytest.mark.asyncio
async def test_a_closed_session_foreign_flow_shows_its_scale_and_is_marked_final(monkeypatch):
    position, _ = await _macro_bullets(monkeypatch, (-90.6e9, 637.6e9))

    assert position.reasoning[-1] == (
        "Market foreign flow (latest session): -91B VND net foreign out of 638B gross turnover "
        "(latest session, final)"
    )


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

    started = time.monotonic()
    position = await agent.run("SAB")

    assert time.monotonic() - started < 0.8  # not the 1 s the fetch takes
    assert "VN-Index trend: unavailable" in position.reasoning


@pytest.mark.asyncio
async def test_foreign_flow_during_the_session_is_shown_but_casts_no_vote(monkeypatch):
    # -15% of foreign turnover would vote bearish, but mid-session the figure keeps
    # moving: the same debate re-run an hour later flipped a verdict (-9.2% at
    # 14:35, -18.4% at 15:48, -24.5% at the close). Partial data is context, not a vote.
    position, text = await _macro_bullets(monkeypatch, (-90e9, 600e9), in_session=True, usdvnd=0.0)

    assert position.stance == "neutral"  # the only vote is a flat USD/VND
    flow = position.reasoning[-1]
    assert "-90B VND net foreign out of 600B gross turnover" in flow
    assert "session in progress" in flow and "not counted in the stance vote" in flow
    assert not any(word in flow.lower() for word in ("bullish", "bearish"))  # a size and a label, no direction


@pytest.mark.asyncio
async def test_the_same_flow_votes_once_the_session_has_closed(monkeypatch):
    position, _ = await _macro_bullets(monkeypatch, (-90e9, 600e9), in_session=False)

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

    await macro_mod.MacroAgent().run("SAB")

    assert order == ["clock", "fetch"]


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


async def _signal2(monkeypatch, vnindex, ticker):
    """Run the agent with USD/VND at -1% (one bullish vote) and return (position, its bullets as text)."""
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: vnindex)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: ticker)
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: -1.0)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: None)
    position = await macro_mod.MacroAgent().run("SAB")
    return position, "\n".join(position.reasoning)


@pytest.mark.asyncio
async def test_relative_return_uses_the_tickers_two_dates_not_the_indexs_last_20_positions(monkeypatch):
    # The stored ticker ends 2026-10-02; the live index runs 3 sessions further.
    ticker = _dated([100.0 + i for i in range(22)], end="2026-10-02")
    index = _dated([1000.0 + j ** 2 for j in range(25)], end="2026-10-07")
    d_first, d_last = ticker.index[-20], ticker.index[-1]

    _, text = await _signal2(monkeypatch, index, ticker)

    # by date: ticker +18.63%, index 2 -> 21: +43.53%  => -24.90%
    # by position (the old bug): index 5 -> 24: +53.76% => -35.13%
    assert "-24.90% relative to VN-Index" in text
    assert "-35.13" not in text
    assert f"{d_first}..{d_last}" in text  # the signal text names both dates


@pytest.mark.asyncio
async def test_an_index_that_misses_an_endpoint_casts_no_vote_and_says_so(monkeypatch):
    ticker = _dated([100.0 + i for i in range(22)], end="2026-10-02")
    index = _dated([1000.0 + j for j in range(10)], end="2026-10-02")  # starts after d_first
    d_first, d_last = ticker.index[-20], ticker.index[-1]
    note = f"ticker window {d_first}..{d_last} not covered by the VN-Index data"

    position, text = await _signal2(monkeypatch, index, ticker)

    assert position.reasoning[1] == f"Relative performance: unavailable ({note})"
    assert position.stance == "bull" and position.degraded_reason is None  # only USD/VND voted


@pytest.mark.asyncio
async def test_a_missing_endpoint_is_stated_once(monkeypatch):
    """The values list already carries the note, so nothing appends it a second time."""
    ticker = _dated([100.0 + i for i in range(22)], end="2026-10-02")
    index = _dated([1000.0 + j for j in range(10)], end="2026-10-02")

    position, _ = await _signal2(monkeypatch, index, ticker)

    assert sum("not covered by the VN-Index data" in bullet for bullet in position.reasoning) == 1
    assert len(position.reasoning) == 4


# ---------------------------------------------------------------------------
# No counted signal: degraded, not neutral
# ---------------------------------------------------------------------------

async def _run_with(monkeypatch, *, vnindex=None, usdvnd=None, flow=None, settling=False):
    monkeypatch.setattr(macro_mod, "_foreign_flow_is_settling", lambda now=None: settling)
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: vnindex)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([], dtype="float64"))
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: usdvnd)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: flow)
    return await macro_mod.MacroAgent().run("SAB")


@pytest.mark.asyncio
async def test_every_fetch_failing_degrades_macro_with_no_input(monkeypatch):
    position = await _run_with(monkeypatch)

    assert position.degraded_reason == "no_input"
    assert "no macro signal was available" in position.reasoning[0].lower()


@pytest.mark.asyncio
async def test_a_provisional_foreign_flow_alone_counts_for_nothing(monkeypatch):
    position = await _run_with(monkeypatch, flow=(-90e9, 600e9), settling=True)

    assert position.degraded_reason == "no_input"


@pytest.mark.asyncio
async def test_one_counted_signal_keeps_macro_live(monkeypatch):
    position = await _run_with(monkeypatch, usdvnd=-1.0)

    assert (position.stance, position.degraded_reason) == ("bull", None)
    assert len(position.reasoning) == 4


# ---------------------------------------------------------------------------
# Reasoning is the four signal lines (Rule 5: computed values, not model text)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_every_signal_has_a_line_in_the_specs_order(monkeypatch):
    monkeypatch.setattr(macro_mod, "_foreign_flow_is_settling", lambda now=None: False)
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: _dated([100.0 + i for i in range(n)]))
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: _dated([100.0 + 3 * i for i in range(n)]))
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: -0.31)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: (-90.6e9, 637.6e9))

    position = await macro_mod.MacroAgent().run("SAB")

    labels = [bullet.split(":")[0] for bullet in position.reasoning]
    assert labels == [
        "VN-Index trend", "Relative performance", "USD/VND", "Market foreign flow (latest session)",
    ]
    assert position.reasoning[0] == "VN-Index trend: up (+)"
    assert position.reasoning[2] == "USD/VND: -0.31%"
    # The engine applies the recommendation-wording check to every position: computed lines pass untouched.
    from app.services.debate.prompt_safety import withhold_advice

    assert [withhold_advice(bullet, "macro") for bullet in position.reasoning] == position.reasoning


@pytest.mark.asyncio
async def test_an_unavailable_signal_still_has_its_line(monkeypatch):
    position = await _run_with(monkeypatch, usdvnd=0.0)

    assert position.reasoning[0] == "VN-Index trend: unavailable"
    assert position.reasoning[1] == "Relative performance: unavailable"
    assert position.reasoning[3] == "Market foreign flow (latest session): unavailable"


@pytest.mark.asyncio
async def test_no_model_is_needed(monkeypatch):
    """Scenario "No model is needed": every language-model call would raise, and the agent is live."""
    from app.services.debate.llm_client import LLMClient

    async def llm_down(self, messages):
        raise AssertionError("the Macro agent called a language model")

    monkeypatch.setattr(LLMClient, "chat", llm_down)
    agent = macro_mod.MacroAgent()

    position = await _run_with(monkeypatch, usdvnd=-1.0)

    assert not hasattr(agent, "_llm") and not hasattr(agent, "respond")
    assert position.degraded_reason is None and len(position.reasoning) == 4


def test_the_dead_sector_placeholder_is_gone():
    assert not hasattr(macro_mod, "_get_sector_closes")

