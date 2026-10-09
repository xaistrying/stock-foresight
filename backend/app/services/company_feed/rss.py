"""Snapshot the RSS items of the News agent's feeds, which hold about four days and cannot be backfilled.

A second reader of the same feeds, through the existing bounded fetch of `news_feeds.py`
(bounded time, bounded size, `defusedxml`, a redirect limit): no new HTTP code, no ticker, sector
or age filter, and `news_feeds.py` is not edited. `fetch_headlines` and the News agent are
untouched and do not read the log. No vnstock import.

RSS fetches are plain HTTP to news sites: vnai does not count them against its rate limit, so the
snapshot runs them first.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from app.services.company_feed.normalise import KIND_RSS, rss_items_to_records
from app.services.company_feed.store import STATUS_EMPTY, STATUS_ERROR, STATUS_OK, FetchRow, PlannedFetch
from app.services.debate.news_feeds import (
    FEEDS,
    HEADERS,
    MAX_REDIRECTS,
    TIMEOUT,
    _fetch_feed as fetch_feed,
)


@dataclass(frozen=True)
class FeedResult:
    """What one feed gave: its items (`(published, title, snippet)` tuples), or the exception it raised."""

    url: str
    items: tuple | None = None
    error: Exception | None = None


async def fetch_feeds(*, client: httpx.AsyncClient | None = None) -> list[FeedResult]:
    """Fetch every feed in `FEEDS`; one feed failing does not stop the others. `client` is injectable
    for tests and otherwise built the way `fetch_headlines` builds its own."""
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            headers=HEADERS, timeout=TIMEOUT, follow_redirects=True, max_redirects=MAX_REDIRECTS
        )
    try:
        outcomes = await asyncio.gather(*(fetch_feed(client, url) for url in FEEDS), return_exceptions=True)
    finally:
        if owns_client:
            await client.aclose()

    results: list[FeedResult] = []
    for url, outcome in zip(FEEDS, outcomes):
        if isinstance(outcome, BaseException) and not isinstance(outcome, Exception):
            raise outcome  # a cancellation or an exit request is not a feed failure
        if isinstance(outcome, Exception):
            results.append(FeedResult(url=url, error=outcome))
        else:
            results.append(FeedResult(url=url, items=tuple(outcome)))
    return results


def plan_fetches(results: list[FeedResult]) -> list[PlannedFetch]:
    """One planned fetch per feed: `ok`, `empty` (a feed with no items is a normal answer) or `error`."""
    plans: list[PlannedFetch] = []
    for result in results:
        if result.error is not None:
            plans.append(PlannedFetch(FetchRow(ticker="", source=result.url, kind=KIND_RSS, status=STATUS_ERROR, error=result.error)))
            continue
        records = rss_items_to_records(result.items, source=result.url).records
        status = STATUS_OK if result.items else STATUS_EMPTY
        plans.append(PlannedFetch(
            FetchRow(ticker="", source=result.url, kind=KIND_RSS, status=status, items_returned=len(result.items)), records,
        ))
    return plans
