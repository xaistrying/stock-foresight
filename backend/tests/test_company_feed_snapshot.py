"""One snapshot run (`company-feed`: pacing, rate limit, non-fatal failures, the run report).

Fetchers, clock and `sleep` are injected; the store is the real one on a temporary file
(`conftest._temporary_company_feed_log`). Nothing calls the vendor or waits for real.
"""

from __future__ import annotations

import inspect
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.db import company_feed_log
from app.services.company_feed import fetch, rss, snapshot, store
from app.services.company_feed.normalise import frame_to_records
from app.services.company_feed.snapshot import Options, Tools, run_snapshot
from app.services.company_feed.store import FetchRow
from app.services.company_feed.summary import format_summary

from .company_feed_helpers import (
    FEED_A, FEED_B, FEED_C, events_frame, events_row, many_news, news_frame, news_row,
)

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
FETCH_SECONDS = 1.0
RATE_LIMIT_MESSAGE = "Rate limit exceeded. Upgrade for more requests. Process terminated."
DEFAULT_FRAMES = {"news": news_frame, "events": events_frame}


class World:
    """A fake clock that sleeps by adding to it, and a record of what the run called, in order."""

    def __init__(self, outcomes: dict | None = None, feeds: list | None = None):
        self.t = 5000.0
        self.sleeps: list[float] = []
        self.calls: list[tuple] = []  # (clock time, "fetch" | "rss", ticker, kind)
        self._outcomes = {key: list(value) if isinstance(value, list) else [value] for key, value in (outcomes or {}).items()}
        self._feeds = feeds

    def clock(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds

    def fetch_frame(self, ticker: str, kind: str) -> pd.DataFrame:
        self.calls.append((self.t, "fetch", ticker, kind))
        self.t += FETCH_SECONDS
        queue = self._outcomes.get((ticker, kind))
        outcome = DEFAULT_FRAMES[kind]() if not queue else (queue.pop(0) if len(queue) > 1 else queue[0])
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def fetch_feeds(self) -> list[rss.FeedResult]:
        self.calls.append((self.t, "rss", "", "rss"))
        return self._feeds if self._feeds is not None else [rss.FeedResult(url=url, items=()) for url in (FEED_A, FEED_B, FEED_C)]

    def tools(self, **overrides) -> Tools:
        base = dict(
            fetch_frame=self.fetch_frame, fetch_feeds=self.fetch_feeds, vnstock_version=lambda: "4.0.5",
            now=lambda: NOW, clock=self.clock, sleep=self.sleep,
        )
        return Tools(**{**base, **overrides})

    def starts(self) -> list[float]:
        """When each ticker was first asked for (a rate-limit retry is the same ticker, not a new start)."""
        first: dict[str, float] = {}
        for t, what, ticker, kind in self.calls:
            if what == "fetch" and kind == "news":
                first.setdefault(ticker, t)
        return list(first.values())


def _run(world: World, tickers, **option_changes) -> snapshot.RunSummary:
    options = Options(include_rss=False, **option_changes)
    return run_snapshot(tuple(tickers), options, world.tools())


def _query(sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(company_feed_log.COMPANY_FEED_LOG_DB_PATH)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _statuses(summary) -> list[tuple[str, str, str]]:
    return [(r.ticker, r.kind, r.status) for r in summary.reports]


# --- 8.1: pacing -------------------------------------------------------------------------------


def _most_starts_in_any_minute(starts: list[float]) -> int:
    return max(sum(1 for t in starts if s <= t < s + 60.0) for s in starts)


def test_default_pacing_never_starts_more_than_eight_tickers_in_a_minute():
    """Scenario: Pacing."""
    world = World()
    tickers = [f"T{i:02d}" for i in range(24)]

    summary = _run(world, tickers)

    assert len(world.starts()) == 24 and summary.exit_code == 0
    assert _most_starts_in_any_minute(world.starts()) <= 8
    assert min(b - a for a, b in zip(world.starts(), world.starts()[1:])) >= 7.5 - 1e-9
    assert snapshot.Options().tickers_per_minute == 8


def test_tickers_per_minute_changes_the_pace():
    world = World()

    _run(world, [f"T{i:02d}" for i in range(12)], tickers_per_minute=4)

    assert _most_starts_in_any_minute(world.starts()) <= 4
    assert min(b - a for a, b in zip(world.starts(), world.starts()[1:])) >= 15.0 - 1e-9


def test_a_slow_ticker_is_not_followed_by_a_catch_up_burst():
    outcomes = {("T00", "news"): [fetch.RateLimited(), fetch.RateLimited(), news_frame()]}
    world = World(outcomes)

    _run(world, [f"T{i:02d}" for i in range(10)])

    assert _most_starts_in_any_minute(world.starts()) <= 8


def test_both_kinds_are_fetched_for_every_ticker():
    world = World()

    summary = _run(world, ["SAB", "VPB"])

    assert _statuses(summary) == [("SAB", "news", "ok"), ("SAB", "events", "ok"), ("VPB", "news", "ok"), ("VPB", "events", "ok")]
    assert _query("SELECT ticker, kind FROM company_feed_fetch ORDER BY id") == [
        ("SAB", "news"), ("SAB", "events"), ("VPB", "news"), ("VPB", "events"),
    ]


def test_the_vendor_cap_is_a_recorded_fact_not_a_claim_about_earlier_items():
    """Scenario: The vendor cap is a recorded fact."""
    world = World({("SAB", "news"): many_news(snapshot.fetch.VENDOR_ITEM_CAP)})

    summary = _run(world, ["SAB"])

    assert _query("SELECT items_returned, items_new FROM company_feed_fetch WHERE kind = 'news'") == [(50, 50)]
    assert fetch.VENDOR_ITEM_CAP == 50 and summary.exit_code == 0
    assert not any(r.possible_gap for r in summary.reports)


def test_a_non_positive_pace_is_refused():
    with pytest.raises(ValueError):
        Options(tickers_per_minute=0)


# --- 8.1: rate limit ---------------------------------------------------------------------------


def test_a_rate_limit_is_waited_out_and_the_call_retried():
    """Scenario: A rate-limit exit is waited out."""
    world = World({("SAB", "news"): [fetch.RateLimited("limit"), news_frame()]})

    summary = _run(world, ["SAB"])

    assert world.sleeps == [60.0]
    assert _statuses(summary) == [("SAB", "news", "ok"), ("SAB", "events", "ok")]
    assert summary.reports[0].rate_limit_waits == 1 and summary.exit_code == 0
    assert _query("SELECT COUNT(*) FROM company_feed_item WHERE kind = 'news'") == [(1,)]


def test_vnais_exit_raised_inside_the_wrapper_is_waited_out_end_to_end(monkeypatch):
    """The real `fetch_company_frame` turns vnai's `SystemExit` into a retry, the run goes on."""
    answers = [SystemExit(RATE_LIMIT_MESSAGE), news_frame()]

    def vendor(symbol, kind):
        outcome = answers.pop(0) if kind == "news" and answers else DEFAULT_FRAMES[kind]()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(fetch, "_call_vendor", vendor)
    world = World()

    summary = run_snapshot(("SAB",), Options(include_rss=False), world.tools(fetch_frame=fetch.fetch_company_frame))

    assert world.sleeps == [60.0] and summary.exit_code == 0
    assert _query("SELECT status, error_class FROM company_feed_fetch ORDER BY id") == [("ok", None), ("ok", None)]


def test_a_persistent_rate_limit_stops_the_run_and_lists_what_was_not_attempted():
    """Scenario: Persistent rate limit stops the run."""
    world = World({("VPB", "news"): fetch.RateLimited("limit")})

    summary = _run(world, ["SAB", "VPB", "HPG", "SSI"])

    assert [s for s in world.sleeps if s == 60.0] == [60.0] * 5  # the other sleep is the pacing gap
    assert _statuses(summary) == [("SAB", "news", "ok"), ("SAB", "events", "ok"), ("VPB", "news", "rate_limited")]
    assert summary.reports[2].rate_limit_waits == 5
    assert summary.not_attempted == ("VPB:events", "HPG", "SSI")
    assert summary.exit_code != 0
    assert _query("SELECT status, error_class FROM company_feed_fetch WHERE ticker = 'VPB'") == [("rate_limited", "RateLimited")]
    assert _query("SELECT COUNT(*) FROM company_feed_fetch WHERE ticker IN ('HPG', 'SSI')") == [(0,)]
    assert "Not attempted" in format_summary(summary, NOW) and "HPG" in format_summary(summary, NOW)


def test_the_wait_and_retry_counts_can_be_set():
    world = World({("SAB", "news"): fetch.RateLimited("limit")})

    summary = run_snapshot(("SAB",), Options(include_rss=False, rate_limit_wait=3.0, max_rate_limit_waits=2), world.tools())

    assert world.sleeps == [3.0, 3.0] and summary.reports[0].status == "rate_limited"


def test_wrapped_errors_are_recorded_with_the_underlying_class(monkeypatch):
    """Scenario: Wrapped errors are classified."""
    from concurrent.futures import Future

    from tenacity import RetryError

    future: Future = Future()
    future.set_exception(ValueError("underlying"))

    def vendor(symbol, kind):
        raise RetryError(future)

    monkeypatch.setattr(fetch, "_call_vendor", vendor)

    summary = run_snapshot(("SAB",), Options(include_rss=False), World().tools(fetch_frame=fetch.fetch_company_frame))

    assert _query("SELECT status, error_class FROM company_feed_fetch ORDER BY id") == [("error", "ValueError"), ("error", "ValueError")]
    assert summary.exit_code == 1


def test_a_genuine_exit_propagates():
    """Scenario: A genuine exit is honoured."""
    world = World({("VPB", "news"): SystemExit("shutting down")})

    with pytest.raises(SystemExit, match="shutting down"):
        _run(world, ["SAB", "VPB", "HPG"])

    assert [c[2] for c in world.calls if c[3] == "news"] == ["SAB", "VPB"]


# --- 8.1: failures are non-fatal and never silent ----------------------------------------------


def test_one_failing_ticker_does_not_stop_the_others_and_is_logged_with_its_traceback(caplog):
    """Scenario: One ticker fails."""
    world = World({("VPB", "news"): ValueError("bad frame"), ("VPB", "events"): ValueError("bad frame")})

    with caplog.at_level(logging.ERROR):
        summary = _run(world, ["SAB", "VPB", "HPG"])

    assert summary.exit_code == 1
    assert _query("SELECT ticker, kind, status, error_class FROM company_feed_fetch WHERE status = 'error' ORDER BY id") == [
        ("VPB", "news", "error", "ValueError"), ("VPB", "events", "error", "ValueError"),
    ]
    assert _query("SELECT COUNT(DISTINCT ticker) FROM company_feed_item") == [(2,)]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 2
    assert all(r.exc_info and r.exc_info[0] is ValueError for r in errors)
    assert "VPB news" in errors[0].getMessage() and "VPB events" in errors[1].getMessage()


def test_a_changed_frame_is_an_unexpected_frame_error_and_stores_no_item():
    """Scenario: A changed frame is an error."""
    world = World({("SAB", "news"): news_frame().drop(columns=["news_title"])})

    summary = _run(world, ["SAB"])

    assert _query("SELECT status, error_class FROM company_feed_fetch WHERE kind = 'news'") == [("error", "UnexpectedFrame")]
    assert _query("SELECT COUNT(*) FROM company_feed_item WHERE kind = 'news'") == [(0,)]
    assert summary.exit_code == 1


def test_a_quiet_ticker_is_empty_and_the_run_is_clean():
    """Scenario: A quiet ticker is empty, not an error."""
    world = World({("SAB", "events"): pd.DataFrame()})

    summary = _run(world, ["SAB"])

    assert _query("SELECT status, items_returned, error_class FROM company_feed_fetch WHERE kind = 'events'") == [("empty", 0, None)]
    assert summary.exit_code == 0


def test_a_failing_insert_is_logged_counted_and_does_not_stop_the_run(caplog):
    """Scenario: The insert fails."""
    attempts = []

    def flaky_record(row, records, *, fetched_at):
        attempts.append((row.ticker, row.kind))
        if len(attempts) == 1:
            raise sqlite3.OperationalError("database is locked")
        return store.record_fetch(row, records, fetched_at=fetched_at)

    world = World()
    with caplog.at_level(logging.ERROR):
        summary = run_snapshot(("SAB", "VPB"), Options(include_rss=False), world.tools(record=flaky_record))

    assert len(attempts) == 4 and summary.write_failures == 1 and summary.exit_code == 1
    assert [r.write_failed for r in summary.reports] == [True, False, False, False]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1 and errors[0].exc_info[0] is sqlite3.OperationalError
    assert _query("SELECT COUNT(*) FROM company_feed_fetch") == [(3,)]
    assert "Write failures: 1" in format_summary(summary, NOW)


def test_a_body_column_is_warned_about_once_per_run_and_never_stored(caplog):
    """Scenario: A body column is dropped."""
    body = "Nội dung đầy đủ rất dài của bản tin cần được giữ ngoài nhật ký"
    frame = news_frame(news_row(news_full_content=body))
    world = World({("SAB", "news"): frame, ("VPB", "news"): frame, ("HPG", "news"): frame})

    with caplog.at_level(logging.WARNING):
        summary = _run(world, ["SAB", "VPB", "HPG"])

    warnings = [r for r in caplog.records if "news_full_content" in r.getMessage()]
    assert len(warnings) == 1 and len(summary.warnings) == 1
    assert body.encode() not in company_feed_log.COMPANY_FEED_LOG_DB_PATH.read_bytes()


def test_non_scalar_cells_are_counted_in_the_report():
    frame = events_frame(events_row(category=["a", "b"]))
    world = World({("SAB", "events"): frame})

    summary = _run(world, ["SAB"])

    assert [r.skipped_cells for r in summary.reports] == [0, 1]


# --- 8.1: RSS ordering -------------------------------------------------------------------------


def test_rss_runs_before_the_tickers_and_no_rss_skips_it():
    with_rss, without_rss = World(), World()

    run_snapshot(("SAB",), Options(), with_rss.tools())
    run_snapshot(("SAB",), Options(include_rss=False), without_rss.tools())

    assert [c[1] for c in with_rss.calls] == ["rss", "fetch", "fetch"]
    assert [c[1] for c in without_rss.calls] == ["fetch", "fetch"]


def test_rss_runs_even_when_the_rate_limit_later_stops_the_tickers():
    items = ((NOW, "Tin", "mô tả"),)
    world = World({("SAB", "news"): fetch.RateLimited("limit")}, feeds=[rss.FeedResult(url=FEED_A, items=items)])

    summary = run_snapshot(("SAB", "VPB"), Options(), world.tools())

    assert _query("SELECT COUNT(*) FROM company_feed_item WHERE kind = 'rss'") == [(1,)]
    assert summary.not_attempted == ("SAB:events", "VPB")


def test_a_failing_feed_is_an_error_row_and_the_exit_code_is_one(caplog):
    """Scenario: One feed is down."""
    feeds = [
        rss.FeedResult(url=FEED_A, items=((NOW, "Tin A", ""),)),
        rss.FeedResult(url=FEED_B, error=TimeoutError("slow")),
        rss.FeedResult(url=FEED_C, items=((NOW, "Tin C", ""),)),
    ]
    world = World(feeds=feeds)

    with caplog.at_level(logging.ERROR):
        summary = run_snapshot((), Options(), world.tools())

    assert summary.exit_code == 1
    assert _query("SELECT source, status, error_class FROM company_feed_fetch ORDER BY id") == [
        (FEED_A, "ok", None), (FEED_B, "error", "TimeoutError"), (FEED_C, "ok", None),
    ]
    assert any(r.levelno == logging.ERROR and FEED_B in r.getMessage() and r.exc_info for r in caplog.records)


def test_a_feed_fetch_that_raises_as_a_whole_is_three_error_rows(caplog):
    async def broken():
        raise RuntimeError("client could not be built")

    with caplog.at_level(logging.ERROR):
        summary = run_snapshot((), Options(), World().tools(fetch_feeds=broken))

    assert summary.exit_code == 1
    assert _query("SELECT status, error_class FROM company_feed_fetch ORDER BY id") == [("error", "RuntimeError")] * 3


# --- 8.2: the run report -----------------------------------------------------------------------


def _earlier_fetch(kind: str, days_ago: float, items: int = 1, status: str = "ok", prefix: str = "Cũ"):
    frame = many_news(items, prefix=prefix) if kind == "news" else events_frame()
    records = frame_to_records(frame, kind=kind, ticker="SAB", source="vci").records
    store.record_fetch(
        FetchRow(ticker="SAB", source="vci", kind=kind, status=status, items_returned=items), records,
        fetched_at=NOW - timedelta(days=days_ago),
    )


def test_the_summary_states_the_age_of_the_previous_successful_fetch():
    """Scenario: A lapse is visible."""
    _earlier_fetch("news", days_ago=9)

    summary = _run(World(), ["SAB"])
    text = format_summary(summary, NOW)

    news_line = next(line for line in text.splitlines() if line.startswith("  SAB news"))
    events_line = next(line for line in text.splitlines() if line.startswith("  SAB events"))
    assert "previous successful fetch 9.0 days ago" in news_line
    assert "no previous successful fetch" in events_line


def test_hours_are_used_for_a_recent_previous_fetch():
    _earlier_fetch("news", days_ago=0.25)

    text = format_summary(_run(World(), ["SAB"]), NOW)

    assert "previous successful fetch 6.0 hours ago" in text


def test_a_failed_attempt_is_not_the_previous_successful_fetch():
    _earlier_fetch("news", days_ago=9)
    store.record_fetch(FetchRow(ticker="SAB", source="vci", kind="news", status="error", error=ValueError("x")), (), fetched_at=NOW - timedelta(days=1))

    text = format_summary(_run(World(), ["SAB"]), NOW)

    assert "previous successful fetch 9.0 days ago" in text


def test_fifty_items_all_new_after_an_earlier_successful_fetch_is_a_possible_gap(caplog):
    """Scenario: A possible gap is reported."""
    _earlier_fetch("news", days_ago=2, items=5)
    world = World({("SAB", "news"): many_news(50, prefix="Mới")})

    with caplog.at_level(logging.WARNING):
        summary = _run(world, ["SAB"])

    assert [r.possible_gap for r in summary.reports] == [True, False]
    gap_warnings = [r for r in caplog.records if "possible gap" in r.getMessage()]
    assert len(gap_warnings) == 1 and "SAB" in gap_warnings[0].getMessage() and "news" in gap_warnings[0].getMessage()
    assert "possible gap: SAB news" in format_summary(summary, NOW)


def test_a_repeated_row_in_a_fifty_row_frame_does_not_hide_a_possible_gap():
    """Scenario: A possible gap is reported (the vendor can repeat a row, so 50 returned is 49 distinct)."""
    _earlier_fetch("news", days_ago=2, items=5)
    fresh = many_news(49, prefix="Mới")
    world = World({("SAB", "news"): pd.concat([fresh, fresh.iloc[:1]], ignore_index=True)})

    summary = _run(world, ["SAB"])

    assert len(world._outcomes[("SAB", "news")][0]) == fetch.VENDOR_ITEM_CAP
    assert [r.possible_gap for r in summary.reports] == [True, False]


def test_a_first_fifty_item_fetch_is_not_a_gap(caplog):
    """Scenario: A first fetch is not a gap."""
    world = World({("SAB", "news"): many_news(50)})

    with caplog.at_level(logging.WARNING):
        summary = _run(world, ["SAB"])

    assert not any(r.possible_gap for r in summary.reports)
    assert not any("possible gap" in r.getMessage() for r in caplog.records)


def test_fifty_items_that_overlap_the_log_are_not_a_gap():
    _earlier_fetch("news", days_ago=1, items=50, prefix="Tin")
    world = World({("SAB", "news"): many_news(50)})

    summary = _run(world, ["SAB"])

    assert not any(r.possible_gap for r in summary.reports)


def test_fewer_than_fifty_new_items_after_an_earlier_fetch_is_not_a_gap():
    _earlier_fetch("news", days_ago=1, items=3)
    world = World({("SAB", "news"): many_news(49, prefix="Mới")})

    assert not any(r.possible_gap for r in _run(world, ["SAB"]).reports)


# --- 8.2: dry run ------------------------------------------------------------------------------


def test_a_dry_run_creates_no_file_and_lists_what_would_be_stored():
    """Scenario: Dry run writes nothing."""
    world = World({("SAB", "news"): news_frame(news_row(news_title="SAB công bố cổ tức"))})

    summary = run_snapshot(("SAB",), Options(include_rss=False, dry_run=True), world.tools())
    text = format_summary(summary, NOW)

    assert not company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists()
    assert summary.exit_code == 0 and summary.dry_run
    assert "dry run" in text and "would store" in text
    assert "2026-08-28T17:39:58  SAB công bố cổ tức" in text


def test_a_dry_run_leaves_an_existing_log_byte_identical_and_counts_only_new_items():
    _earlier_fetch("news", days_ago=1, items=2)
    before = company_feed_log.COMPANY_FEED_LOG_DB_PATH.read_bytes()
    world = World({("SAB", "news"): many_news(4, prefix="Cũ")})

    summary = run_snapshot(("SAB",), Options(include_rss=False, dry_run=True), world.tools())

    assert company_feed_log.COMPANY_FEED_LOG_DB_PATH.read_bytes() == before
    assert summary.reports[0].items_returned == 4 and summary.reports[0].items_new == 2


def test_a_dry_run_with_rss_writes_nothing_either():
    feeds = [rss.FeedResult(url=FEED_A, items=((NOW, "Tin A", ""),))]

    summary = run_snapshot((), Options(dry_run=True), World(feeds=feeds).tools())

    assert not company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists()
    assert [r.items_new for r in summary.reports] == [1]


# --- No model call -----------------------------------------------------------------------------


def test_no_model_client_is_constructed_by_a_run(monkeypatch):
    """Scenario: No model client is used."""
    from app.services.debate.llm_client import LLMClient

    def forbidden(*args, **kwargs):
        raise AssertionError("a model client was constructed")

    monkeypatch.setattr(LLMClient, "__init__", forbidden)

    summary = run_snapshot(("SAB",), Options(), World().tools())

    assert summary.exit_code == 0


def test_the_whole_run_is_sync_code_a_caller_without_a_loop_can_use():
    assert not inspect.iscoroutinefunction(run_snapshot)
