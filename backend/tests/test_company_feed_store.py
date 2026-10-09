"""Writing fetches and item versions to the company feed log (`company-feed`: items stored once per
version; every fetch recorded; a failed write is raised, not swallowed).

Every test runs against a temporary file (`conftest._temporary_company_feed_log`).
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.db import company_feed_log
from app.services.company_feed import store
from app.services.company_feed.normalise import frame_to_records
from app.services.company_feed.store import FetchRow

from .company_feed_helpers import events_frame, events_row, many_news, news_frame, news_row

T0 = datetime(2026, 10, 9, 9, 0, tzinfo=timezone.utc)


def _records(frame, kind="news", ticker="SAB"):
    return frame_to_records(frame, kind=kind, ticker=ticker, source="vci").records


def _fetch(kind="news", ticker="SAB", status="ok", returned=None, **kwargs) -> FetchRow:
    return FetchRow(ticker=ticker, source="vci", kind=kind, status=status, items_returned=returned, **kwargs)


def _query(sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(company_feed_log.COMPANY_FEED_LOG_DB_PATH)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_the_first_write_creates_the_file_with_both_tables_and_the_item():
    """Scenario: First write creates the file."""
    assert not company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists()

    stored = store.record_fetch(_fetch(returned=1), _records(news_frame()), fetched_at=T0)

    assert stored.items_new == 1
    assert _query("SELECT COUNT(*) FROM company_feed_item") == [(1,)]
    assert _query("SELECT COUNT(*) FROM company_feed_fetch") == [(1,)]


def test_a_repeated_fetch_inserts_nothing():
    """Scenario: A repeated item is not stored twice."""
    records = _records(many_news(50))

    first = store.record_fetch(_fetch(returned=50), records, fetched_at=T0)
    second = store.record_fetch(_fetch(returned=50), records, fetched_at=T0 + timedelta(days=1))

    assert (first.items_new, second.items_new) == (50, 0)
    assert _query("SELECT COUNT(*) FROM company_feed_item") == [(50,)]
    assert _query("SELECT items_returned, items_new FROM company_feed_fetch ORDER BY id") == [(50, 50), (50, 0)]


def test_a_revised_field_becomes_a_new_version_and_leaves_the_old_row_unchanged():
    """Scenario: A revised item becomes a new version."""
    store.record_fetch(_fetch("events", returned=1), _records(events_frame(events_row(payout_date=np.nan)), "events"), fetched_at=T0)
    before = _query("SELECT * FROM company_feed_item")
    revised = _records(events_frame(events_row(payout_date="2026-08-28T00:00:00")), "events")

    stored = store.record_fetch(_fetch("events", returned=1), revised, fetched_at=T0 + timedelta(days=2))

    rows = _query("SELECT id, item_id, content_hash FROM company_feed_item ORDER BY id")
    assert stored.items_new == 1 and len(rows) == 2
    assert rows[0][1] == rows[1][1] and rows[0][2] != rows[1][2]
    assert _query("SELECT * FROM company_feed_item ORDER BY id")[0] == before[0]


def test_fetched_at_stays_the_first_sighting():
    """Scenario: `fetched_at` is the first sighting."""
    records = _records(news_frame())
    for days in (0, 1, 2):
        store.record_fetch(_fetch(returned=1), records, fetched_at=T0 + timedelta(days=days))

    assert _query("SELECT fetched_at FROM company_feed_item") == [(T0.isoformat(),)]
    assert _query("SELECT fetched_at FROM company_feed_fetch ORDER BY id")[-1] == ((T0 + timedelta(days=2)).isoformat(),)


def test_item_rows_point_at_the_fetch_that_first_saw_them_and_times_are_utc_with_an_offset():
    records = _records(news_frame())
    first = store.record_fetch(_fetch(returned=1), records, fetched_at=T0)
    store.record_fetch(_fetch(returned=1), records, fetched_at=T0 + timedelta(days=1))

    assert _query("SELECT fetch_id FROM company_feed_item") == [(first.fetch_id,)]
    ict = timezone(timedelta(hours=7))
    stored = store.record_fetch(_fetch(returned=0, status="empty"), (), fetched_at=datetime(2026, 10, 10, 16, 0, tzinfo=ict))
    assert stored.fetched_at == "2026-10-10T09:00:00+00:00"


def test_a_naive_timestamp_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        store.record_fetch(_fetch(returned=0, status="empty"), (), fetched_at=datetime(2026, 10, 9, 9, 0))


def test_an_unknown_status_is_refused():
    with pytest.raises(ValueError, match="status"):
        store.record_fetch(_fetch(status="fine"), ())


def test_two_writers_storing_the_same_items_at_once_leave_no_duplicate_and_no_error():
    """Scenario: Overlapping runs are harmless."""
    records = _records(many_news(50))
    barrier = threading.Barrier(2)
    results: list[object] = []

    def run():
        barrier.wait()
        try:
            results.append(store.record_fetch(_fetch(returned=50), records, fetched_at=T0))
        except Exception as error:  # noqa: BLE001 — the test asserts there is none
            results.append(error)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert all(isinstance(r, store.StoredFetch) for r in results), results
    assert sorted(r.items_new for r in results) == [0, 50]
    assert _query("SELECT COUNT(*) FROM company_feed_item") == [(50,)]
    assert _query("SELECT COUNT(*) FROM company_feed_fetch") == [(2,)]


def test_fetch_rows_for_ok_empty_and_error_carry_their_columns():
    store.record_fetch(_fetch(returned=2, vnstock_version="4.0.5"), _records(many_news(2)), fetched_at=T0)
    store.record_fetch(_fetch("events", status="empty", returned=0, vnstock_version="4.0.5"), (), fetched_at=T0)
    store.record_fetch(
        _fetch("news", ticker="VPB", status="error", error=ValueError("boom"), vnstock_version="4.0.5"), (), fetched_at=T0
    )
    store.record_fetch(
        FetchRow(ticker="", source="https://example.invalid/feed.rss", kind="rss", status="ok", items_returned=1),
        (), fetched_at=T0,
    )

    rows = _query(
        "SELECT ticker, source, kind, status, items_returned, items_new, error_class, vnstock_version "
        "FROM company_feed_fetch ORDER BY id"
    )
    assert rows == [
        ("SAB", "vci", "news", "ok", 2, 2, None, "4.0.5"),
        ("SAB", "vci", "events", "empty", 0, 0, None, "4.0.5"),
        ("VPB", "vci", "news", "error", None, 0, "ValueError", "4.0.5"),
        ("", "https://example.invalid/feed.rss", "rss", "ok", 1, 0, None, None),
    ]


def test_an_exception_message_is_not_stored_only_its_class_name():
    """Scenario: An exception message is not stored."""
    promo = "Rate limit exceeded. Upgrade now at https://vnstocks.example.invalid/promo for unlimited access. " * 20

    store.record_fetch(_fetch(status="rate_limited", error=SystemExit(promo)), (), fetched_at=T0)

    assert _query("SELECT error_class FROM company_feed_fetch") == [("SystemExit",)]
    assert b"Upgrade now" not in company_feed_log.COMPANY_FEED_LOG_DB_PATH.read_bytes()


def test_a_failing_insert_rolls_the_fetch_back_and_raises():
    good = _records(news_frame())[0]
    bad = replace(good, item_id="x" * 16, content_hash="y" * 64, title=object())

    with pytest.raises(sqlite3.Error):
        store.record_fetch(_fetch(returned=2), (good, bad), fetched_at=T0)

    assert _query("SELECT COUNT(*) FROM company_feed_item") == [(0,)]
    assert _query("SELECT COUNT(*) FROM company_feed_fetch") == [(0,)]


def test_a_locked_log_raises_instead_of_failing_silently(monkeypatch):
    """Scenario: The insert fails (the file is locked), at the writer: it raises, the caller decides."""
    store.record_fetch(_fetch(returned=1), _records(news_frame()), fetched_at=T0)
    monkeypatch.setattr(company_feed_log, "BUSY_TIMEOUT_SECONDS", 0.05)
    holder = sqlite3.connect(company_feed_log.COMPANY_FEED_LOG_DB_PATH)
    holder.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            store.record_fetch(_fetch(returned=1), _records(news_frame(news_row(news_title="Khác"))), fetched_at=T0)
    finally:
        holder.rollback()
        holder.close()

    assert _query("SELECT COUNT(*) FROM company_feed_fetch") == [(1,)]


def test_values_are_bound_not_interpolated():
    nasty = "x'); DROP TABLE company_feed_item; --"

    store.record_fetch(_fetch(returned=1), _records(news_frame(news_row(news_title=nasty))), fetched_at=T0)
    store.record_fetch(_fetch(returned=1, ticker=nasty), (), fetched_at=T0)

    assert _query("SELECT title FROM company_feed_item") == [(nasty,)]
    assert _query("SELECT ticker FROM company_feed_fetch ORDER BY id")[-1] == (nasty,)


def test_the_stored_item_columns_hold_the_cleaned_title_the_date_and_the_fields():
    store.record_fetch(_fetch(returned=1), _records(news_frame(news_row(news_title="<i>SAB</i> công bố"))), fetched_at=T0)

    row = _query("SELECT ticker, source, kind, published_at, title, fields FROM company_feed_item")[0]
    assert row == ("SAB", "vci", "news", "2026-08-28T17:39:58", "SAB công bố",
                   '{"news_author":null,"news_source":null,"news_source_link":null}')


def test_no_environment_value_is_stored(monkeypatch):
    """Scenario: No credential in the log file."""
    monkeypatch.setenv("VNSTOCK_API_KEY", "vnstock-key-placeholder-not-real")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder-not-a-real-key")

    store.record_fetch(_fetch(returned=1, vnstock_version="4.0.5"), _records(news_frame()), fetched_at=T0)

    content = company_feed_log.COMPANY_FEED_LOG_DB_PATH.read_bytes()
    assert b"placeholder" not in content
