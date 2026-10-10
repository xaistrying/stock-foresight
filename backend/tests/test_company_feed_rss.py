"""Snapshotting RSS items into the company feed log (`company-feed`: "RSS items are snapshotted
into the same log").

The feeds are served by httpx.MockTransport, so nothing touches the network.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx

from app.db import company_feed_log
from app.services.company_feed import rss, store
from app.services.debate import news_feeds
from app.services.debate.news_feeds import FEEDS

from .company_feed_helpers import FEED_A, FEED_B, FEED_C, feed_client, rss_body, rss_items

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def _run(feeds, *, when=NOW) -> list[store.StoredFetch]:
    """Fetch the feeds through an injected client and store every planned fetch."""
    async def go():
        async with feed_client(feeds) as client:
            return await rss.fetch_feeds(client=client)

    results = asyncio.run(go())
    return [store.record_fetch(plan.row, plan.records, fetched_at=when) for plan in rss.plan_fetches(results)]


def _query(sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(company_feed_log.COMPANY_FEED_LOG_DB_PATH)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _three_feeds(snippet_suffix: str = "") -> dict:
    return {
        FEED_A: rss_body(*[(t, p, d + snippet_suffix) for t, p, d in rss_items(60, prefix="A", start=NOW)]),
        FEED_B: rss_body(*rss_items(50, prefix="B", start=NOW)),
        FEED_C: rss_body(*rss_items(20, prefix="C", start=NOW)),
    }


def test_the_feeds_are_the_news_agents_feeds_and_the_fetch_is_its_bounded_fetch():
    assert (FEED_A, FEED_B, FEED_C) == FEEDS
    assert rss.fetch_feed is news_feeds._fetch_feed
    assert rss.FEEDS is news_feeds.FEEDS


def test_all_three_feeds_are_stored_as_rss_items_without_a_ticker_in_utc():
    """Scenario: All three feeds are stored."""
    stored = _run(_three_feeds())

    assert [s.items_new for s in stored] == [60, 50, 20]
    assert _query("SELECT COUNT(*) FROM company_feed_item WHERE kind = 'rss' AND ticker = ''") == [(130,)]
    assert _query("SELECT source, ticker, kind, status, items_returned, items_new FROM company_feed_fetch ORDER BY id") == [
        (FEED_A, "", "rss", "ok", 60, 60), (FEED_B, "", "rss", "ok", 50, 50), (FEED_C, "", "rss", "ok", 20, 20),
    ]
    published, fields = _query("SELECT published_at, fields FROM company_feed_item WHERE title = 'C 0'")[0]
    assert published == "2026-10-08T12:00:00+00:00"
    assert json.loads(fields) == {"snippet": "Mô tả C 0"}
    assert _query("SELECT COUNT(*) FROM company_feed_fetch WHERE vnstock_version IS NOT NULL") == [(0,)]


def test_a_second_run_stores_only_the_genuinely_new_items():
    _run(_three_feeds())
    feeds = _three_feeds()
    feeds[FEED_C] = rss_body(*rss_items(2, prefix="Mới", start=NOW + timedelta(hours=1)), *rss_items(20, prefix="C", start=NOW))

    stored = _run(feeds, when=NOW + timedelta(days=1))

    assert [s.items_new for s in stored] == [0, 0, 2]
    assert _query("SELECT COUNT(*) FROM company_feed_item") == [(132,)]


def test_one_feed_timing_out_is_an_error_row_and_the_others_are_stored():
    """Scenario: One feed is down."""
    feeds = _three_feeds()
    feeds[FEED_B] = httpx.ReadTimeout("timed out")

    stored = _run(feeds)

    assert [s.items_new for s in stored] == [60, 0, 20]
    assert _query("SELECT source, status, items_returned, items_new, error_class FROM company_feed_fetch ORDER BY id") == [
        (FEED_A, "ok", 60, 60, None), (FEED_B, "error", None, 0, "ReadTimeout"), (FEED_C, "ok", 20, 20, None),
    ]
    assert _query("SELECT COUNT(*) FROM company_feed_item WHERE source = ?", (FEED_B,)) == [(0,)]


def test_all_three_feeds_down_give_three_error_rows():
    stored = _run({FEED_A: 500, FEED_B: httpx.ConnectError("refused"), FEED_C: 404})

    assert [s.items_new for s in stored] == [0, 0, 0]
    assert _query("SELECT status, error_class FROM company_feed_fetch ORDER BY id") == [
        ("error", "HTTPStatusError"), ("error", "ConnectError"), ("error", "HTTPStatusError"),
    ]
    assert _query("SELECT COUNT(*) FROM company_feed_item") == [(0,)]


def test_a_feed_with_no_items_is_empty_not_an_error():
    _run({FEED_A: rss_body(), FEED_B: rss_body(*rss_items(1, prefix="B", start=NOW)), FEED_C: rss_body()})

    assert _query("SELECT status, items_returned FROM company_feed_fetch ORDER BY id") == [("empty", 0), ("ok", 1), ("empty", 0)]


def test_an_oversized_feed_is_an_error_row_because_the_existing_bound_applies():
    feeds = _three_feeds()
    feeds[FEED_A] = "<rss>" + "x" * (news_feeds.MAX_FEED_BYTES + 10) + "</rss>"

    _run(feeds)

    assert _query("SELECT status, error_class FROM company_feed_fetch ORDER BY id LIMIT 1") == [("error", "ValueError")]


def test_an_edited_snippet_is_a_new_version_with_the_same_item_id():
    """Scenario: The snippet is kept, the identity ignores it."""
    _run(_three_feeds())

    stored = _run(_three_feeds(snippet_suffix=" (đã sửa)"), when=NOW + timedelta(days=1))

    assert [s.items_new for s in stored] == [60, 0, 0]
    versions = _query("SELECT item_id, content_hash FROM company_feed_item WHERE title = 'A 3' ORDER BY id")
    assert len(versions) == 2 and versions[0][0] == versions[1][0] and versions[0][1] != versions[1][1]
    assert store.latest_items("", "rss", since="2026-10-08")[0].fields["snippet"] is not None


def test_items_are_not_filtered_by_ticker_sector_or_age():
    old = NOW - timedelta(days=400)
    feeds = {
        FEED_A: rss_body(("Giá dầu thế giới giảm", NOW, "Không liên quan"), ("SAB công bố cổ tức", old, "Cũ")),
        FEED_B: rss_body(), FEED_C: rss_body(),
    }

    _run(feeds)

    assert sorted(r[0] for r in _query("SELECT title FROM company_feed_item")) == ["Giá dầu thế giới giảm", "SAB công bố cổ tức"]


def test_fetch_headlines_returns_the_same_lines_after_snapshotting():
    """Scenario: News agent unchanged."""
    bodies = {
        FEED_A: rss_body(("SAB: kết quả quý 3 vượt kế hoạch", NOW - timedelta(hours=3), "SAB lãi lớn")),
        FEED_B: rss_body(("VN-Index giảm 20 điểm phiên sáng", NOW - timedelta(hours=1), "")),
        FEED_C: rss_body(),
    }

    async def headlines():
        async with feed_client(bodies) as client:
            return await news_feeds.fetch_headlines("SAB", "food and beverage", client=client, now=NOW)

    before = asyncio.run(headlines())
    _run(bodies)
    after = asyncio.run(headlines())

    assert before == after and len(before) == 2
    assert _query("SELECT COUNT(*) FROM company_feed_item") == [(2,)]


def test_the_default_client_is_built_like_fetch_headlines_does(monkeypatch):
    built = {}

    class Recorder(httpx.AsyncClient):
        def __init__(self, **kwargs):
            built.update(kwargs)
            super().__init__(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=rss_body().encode())))

    monkeypatch.setattr(rss.httpx, "AsyncClient", Recorder)

    results = asyncio.run(rss.fetch_feeds())

    assert built == {
        "headers": news_feeds.HEADERS, "timeout": news_feeds.TIMEOUT, "follow_redirects": True,
        "max_redirects": news_feeds.MAX_REDIRECTS,
    }
    assert [r.url for r in results] == list(FEEDS) and all(r.error is None for r in results)
