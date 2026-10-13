"""The adapter's announcements (`add-announcement-tags-and-insider-sizing`, task 1.3): a separate type with the stored
title, per-kind source health, no source name, link or author, and the same store-only imports as the events reader."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone

from app.services.brief import feed_source
from app.services.brief.feed_source import Announcement, IssueClass, read_announcements, read_events
from app.services.company_feed import fetch

from .brief_announcement_rows import event_row, insider_row, news_item, press_item, store_rows, store_status
from .brief_event_rows import BONUS, iss_row
from .company_feed_helpers import news_row
from .test_brief_support import brief_isolation  # noqa: F401


def test_the_item_cap_equals_the_fetch_modules_vendor_cap():
    assert feed_source.FEED_ITEM_CAP == fetch.VENDOR_ITEM_CAP == 50


def test_event_rows_become_announcements_with_title_dates_and_action():
    store_rows("AAA", "events", [insider_row("AAA", 1, qty="30,000", published="2026-10-08", start="2026-10-12", end="2026-11-10")])

    read = read_announcements("AAA")

    (item,) = read.items
    assert item.kind == "events" and item.event_code == "DDIND" and item.action_type_en == "Sell"
    assert item.published_at == date(2026, 10, 8) and item.start_date == date(2026, 10, 12) and item.end_date == date(2026, 11, 10)
    assert "30,000" in item.title and item.title.endswith(" AAA")
    assert item.first_seen == date(2026, 10, 10) and item.from_first_fetch is True
    assert read.events.status == "fetched" and read.news.status == "never_fetched"


def test_news_rows_carry_the_title_and_no_source_name_link_or_author():
    row = news_item("AAA", "synthetic notice") | {"news_source": "Example Wire", "news_source_link": "https://example.invalid/x", "news_author": "A. Writer"}
    store_rows("AAA", "news", [row])

    (item,) = read_announcements("AAA").items

    assert item.kind == "news" and item.title == "AAA: synthetic notice" and item.event_code is None
    blob = repr(dataclasses.asdict(item))
    assert "Example Wire" not in blob and "example.invalid" not in blob and "Writer" not in blob
    assert {f.name for f in dataclasses.fields(Announcement)}.isdisjoint({"news_source", "source", "link", "author", "news_author"})


def test_an_issue_row_carries_the_issue_class_and_ratio():
    store_rows("AAA", "events", [iss_row("AAA", BONUS, 1, published="2026-10-01", ex="2026-10-20", ratio=0.1)])

    (item,) = read_announcements("AAA").items

    assert item.issue_class is IssueClass.BONUS and item.exercise_ratio == 0.1 and item.exright_date == date(2026, 10, 20)


def test_the_event_title_is_not_added_to_the_title_free_event_type():
    store_rows("AAA", "events", [insider_row("AAA", 1)])

    (event,) = read_events("AAA").events

    assert "title" not in {f.name for f in dataclasses.fields(event)}


def test_an_undated_or_untitled_row_is_counted_and_dropped():
    store_rows("AAA", "news", [news_row(news_id=1, news_title="AAA: dated", public_date="2026-10-08T09:00:00"), news_row(news_id=2, news_title="AAA: bad date", public_date="not a date")])

    read = read_announcements("AAA")

    assert [i.title for i in read.items] == ["AAA: dated"] and read.unreadable == 1


def test_health_is_per_kind_and_never_fetched_is_not_none_found():
    store_rows("AAA", "news", [press_item("a press headline")])

    read = read_announcements("AAA")

    assert read.news.status == "fetched" and read.news.items_returned == 1 and read.news.newest_published == date(2026, 10, 8)
    assert read.events.status == "never_fetched" and read.events.items_returned is None


def test_a_failed_latest_attempt_keeps_the_last_success_and_names_the_error_class():
    store_rows("AAA", "events", [insider_row("AAA", 1)], fetched_at=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc))
    store_status("AAA", "events", "rate_limited", fetched_at=datetime(2026, 10, 9, 9, 0, tzinfo=timezone.utc), error=RuntimeError("x"))

    health = read_announcements("AAA").events

    assert health.status == "fetched" and health.latest_attempt_failed and health.error_class == "RuntimeError"
    assert health.last_success_at == datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    assert health.items_returned is None  # the stored count belongs to the failed attempt


def test_only_failed_attempts_read_as_never_succeeded():
    store_status("AAA", "news", "error", error=ValueError("x"))

    assert read_announcements("AAA").news.status == "never_succeeded"


def test_a_missing_log_reads_as_never_fetched_for_both_kinds():
    read = read_announcements("ZZZ")

    assert read.items == () and read.news.status == read.events.status == "never_fetched"


def test_a_read_that_raises_reads_as_unreadable_and_never_raises(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("locked")

    monkeypatch.setattr(feed_source.store, "latest_items", boom)
    store_rows("AAA", "events", [insider_row("AAA", 1)])
    store_rows("AAA", "news", [press_item("a press headline")])

    read = read_announcements("AAA")

    assert read.items == () and read.news.status == read.events.status == "unreadable"


def test_the_first_fetch_flag_and_first_seen_date_follow_the_log():
    store_rows("AAA", "events", [insider_row("AAA", 1)], fetched_at=datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc))
    store_rows("AAA", "events", [insider_row("AAA", 1), insider_row("AAA", 2, published="2026-10-05")], fetched_at=datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc))

    items = {i.published_at: i for i in read_announcements("AAA").items}

    assert items[date(2026, 10, 8)].from_first_fetch is True and items[date(2026, 10, 8)].first_seen == date(2026, 9, 1)
    assert items[date(2026, 10, 5)].from_first_fetch is False and items[date(2026, 10, 5)].first_seen == date(2026, 10, 6)


def test_other_codes_keep_their_code_and_dates():
    store_rows("AAA", "events", [event_row("AAA", "AGME", "synthetic meeting", record_date="2026-10-14", issue_date="2026-10-16")])

    (item,) = read_announcements("AAA").items

    assert item.event_code == "AGME" and item.record_date == date(2026, 10, 14) and item.issue_date == date(2026, 10, 16)


def test_an_error_class_that_is_not_a_class_name_is_never_printed_from_the_log(monkeypatch):
    store_rows("AAA", "news", [press_item("a press headline")], fetched_at=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc))
    store_status("AAA", "news", "error", fetched_at=datetime(2026, 10, 9, 9, 0, tzinfo=timezone.utc), error=RuntimeError("x"))
    real = feed_source.store.last_fetch

    def tampered(ticker, kind, source=None):
        found = real(ticker, kind, source)
        return found and dataclasses.replace(found, latest=dataclasses.replace(found.latest, error_class="bad\nclass <b>"))

    monkeypatch.setattr(feed_source.store, "last_fetch", tampered)

    assert read_announcements("AAA").news.error_class == "error"


def test_first_seen_is_the_vietnam_date_like_the_bar_dates():
    store_rows("AAA", "events", [insider_row("AAA", 1)], fetched_at=datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc))  # 03:00 on the 6th in Vietnam

    (item,) = read_announcements("AAA").items

    assert item.first_seen == date(2026, 10, 6)
