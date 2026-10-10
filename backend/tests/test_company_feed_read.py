"""Reading stored items back with their provenance (`company-feed`: "Stored items can be read back").

The helpers read `mode=ro`; there is no route and no UI for them.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.db import company_feed_log
from app.services.company_feed import store
from app.services.company_feed.normalise import frame_to_records, rss_items_to_records
from app.services.company_feed.store import FetchRow

from .company_feed_helpers import events_frame, events_row, many_news, news_frame, news_row

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def _day(n: int) -> datetime:
    return T0 + timedelta(days=n)


def _put(frame, *, kind="news", ticker="SAB", when=0, status="ok"):
    records = frame_to_records(frame, kind=kind, ticker=ticker, source="vci").records
    return store.record_fetch(
        FetchRow(ticker=ticker, source="vci", kind=kind, status=status, items_returned=len(frame)),
        records, fetched_at=_day(when),
    )


def _mark(kind="news", ticker="SAB", status="empty", when=0, error=None):
    return store.record_fetch(
        FetchRow(ticker=ticker, source="vci", kind=kind, status=status, items_returned=0, error=error), (), fetched_at=_day(when)
    )


def test_latest_items_returns_the_later_version_once_with_the_earlier_first_seen_time():
    """Scenario: Latest version only."""
    _put(events_frame(events_row(payout_date=np.nan)), kind="events", when=0)
    _put(events_frame(events_row(payout_date="2026-08-28T00:00:00")), kind="events", when=3)

    items = store.latest_items("SAB", "events")

    assert len(items) == 1
    assert items[0].fields["payout_date"] == "2026-08-28T00:00:00"
    assert items[0].first_seen_at == _day(0).isoformat()
    assert items[0].fetched_at == _day(3).isoformat()


def test_items_come_newest_published_first_one_row_per_item():
    _put(news_frame(
        news_row(news_title="Cũ", public_date="2026-01-05T09:00:00"),
        news_row(news_title="Mới", public_date="2026-09-05T09:00:00"),
        news_row(news_title="Giữa", public_date="2026-05-05T09:00:00"),
    ))
    _put(news_frame(news_row(news_title="Mới", public_date="2026-09-05T09:00:00", news_source="CafeF")), when=1)

    items = store.latest_items("SAB", "news")

    assert [i.title for i in items] == ["Mới", "Giữa", "Cũ"]
    assert items[0].fields["news_source"] == "CafeF"


def test_backfill_is_marked_history_and_later_items_are_not():
    """Scenario: Backfill is marked."""
    _put(many_news(50), when=0)
    _put(news_frame(news_row(news_title="Mới 1", public_date="2026-09-30T09:00:00"),
                    news_row(news_title="Mới 2", public_date="2026-09-30T10:00:00")), when=1)

    by_title = {i.title: i for i in store.latest_items("SAB", "news")}

    assert sum(i.from_first_fetch for i in by_title.values()) == 50
    assert not by_title["Mới 1"].from_first_fetch and not by_title["Mới 2"].from_first_fetch
    assert by_title["Mới 1"].first_seen_at == _day(1).isoformat()


def test_a_failed_first_attempt_is_not_the_first_successful_fetch():
    _mark(status="error", when=0, error=ValueError("down"))
    _put(many_news(3), when=1)

    assert all(i.from_first_fetch for i in store.latest_items("SAB", "news"))


def test_items_that_first_appear_after_an_empty_first_fetch_are_not_history():
    _mark(status="empty", when=0)
    _put(many_news(2), when=5)

    assert not any(i.from_first_fetch for i in store.latest_items("SAB", "news"))


def test_each_ticker_and_kind_has_its_own_first_fetch():
    _put(many_news(2), ticker="SAB", when=0)
    _put(many_news(2, prefix="VPB"), ticker="VPB", when=4)
    _put(many_news(1, prefix="Thêm"), ticker="SAB", when=5)

    sab, vpb = store.latest_items("SAB", "news"), store.latest_items("VPB", "news")

    assert {i.title for i in sab} == {"Tin số 0", "Tin số 1", "Thêm số 0"}
    assert all(i.title.startswith("VPB") for i in vpb) and all(i.from_first_fetch for i in vpb)
    assert store.latest_items("SAB", "events") == []


def test_since_keeps_items_published_on_or_after_it():
    _put(news_frame(
        news_row(news_title="Cũ", public_date="2026-01-05T09:00:00"),
        news_row(news_title="Mới", public_date="2026-09-05T09:00:00"),
    ))

    assert [i.title for i in store.latest_items("SAB", "news", since="2026-06-01")] == ["Mới"]
    assert [i.title for i in store.latest_items("SAB", "news", since=datetime(2026, 1, 5, 9, 0).date())] == ["Mới", "Cũ"]


def test_rss_first_fetch_is_per_feed():
    feeds = ("https://a.example.invalid/rss", "https://b.example.invalid/rss")
    published = datetime(2026, 9, 30, 3, 0, tzinfo=timezone.utc)
    for day, feed, title in ((0, feeds[0], "A1"), (2, feeds[1], "B1"), (3, feeds[0], "A2")):
        records = rss_items_to_records([(published, title, "")], source=feed).records
        store.record_fetch(FetchRow(ticker="", source=feed, kind="rss", status="ok", items_returned=1), records, fetched_at=_day(day))

    flags = {i.title: i.from_first_fetch for i in store.latest_items("", "rss")}

    assert flags == {"A1": True, "B1": True, "A2": False}


def test_last_fetch_returns_the_latest_attempt_and_the_latest_success_time():
    _put(many_news(1), when=0)
    _mark(status="error", when=2, error=RuntimeError("x"))

    last = store.last_fetch("SAB", "news")

    assert last.latest.status == "error" and last.latest.error_class == "RuntimeError"
    assert last.last_success_at == _day(0).isoformat()


def test_none_found_is_not_never_fetched_and_not_a_failed_fetch():
    """Scenario: None found is not never fetched."""
    _mark(kind="events", status="empty", when=1)
    _mark(kind="news", status="error", when=1, error=ValueError("x"))

    empty = store.last_fetch("SAB", "events")
    failed = store.last_fetch("SAB", "news")

    assert empty.latest.status == "empty" and empty.last_success_at == _day(1).isoformat()
    assert failed.latest.status == "error" and failed.last_success_at is None
    assert store.last_fetch("VPB", "events") is None


def test_last_fetch_can_be_narrowed_to_one_feed():
    for day, feed in ((0, "https://a.example.invalid/rss"), (1, "https://b.example.invalid/rss")):
        store.record_fetch(FetchRow(ticker="", source=feed, kind="rss", status="ok", items_returned=0), (), fetched_at=_day(day))

    assert store.last_fetch("", "rss").latest.source == "https://b.example.invalid/rss"
    assert store.last_fetch("", "rss", source="https://a.example.invalid/rss").latest.fetched_at == _day(0).isoformat()


def test_a_missing_log_reads_as_never_fetched_and_is_not_created_by_reading():
    """Scenario: Never fetched."""
    path = company_feed_log.COMPANY_FEED_LOG_DB_PATH
    assert not path.exists()

    assert store.latest_items("SAB", "news") == []
    assert store.last_fetch("SAB", "news") is None
    assert not path.exists()


def test_a_file_without_tables_reads_as_never_fetched():
    sqlite3.connect(company_feed_log.COMPANY_FEED_LOG_DB_PATH).close()

    assert store.latest_items("SAB", "news") == []
    assert store.last_fetch("SAB", "news") is None


def test_the_read_connection_cannot_write():
    _put(many_news(1))
    conn = store.open_log_readonly()
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM company_feed_item")
    finally:
        conn.close()


def test_reading_leaves_the_file_byte_identical():
    _put(many_news(3))
    before = company_feed_log.COMPANY_FEED_LOG_DB_PATH.read_bytes()

    store.latest_items("SAB", "news")
    store.last_fetch("SAB", "news")

    assert company_feed_log.COMPANY_FEED_LOG_DB_PATH.read_bytes() == before
