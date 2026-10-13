"""What the COMPANY block needs for one ticker, gathered once (`add-announcement-tags-and-insider-sizing`).

`gather_company_facts` reads the announcements through the adapter, finds the previous brief's last-bar date in the
issued log, and, only when a listed trade states a quantity and sizing is on, resolves the share count: a fresh cached
value, else one vendor call through the injected function (never imported here), else the stale cached value with its
date. A value reaches the cache only after the fetch function has cross-checked it. The sections and the trigger
counters then work from these facts alone and do no I/O.

The fetch function raises on failure; an exception carrying `disagree = True` means the vendor's two counts differ.
Any `SystemExit` it raises is a failure like any other; `KeyboardInterrupt` is not caught.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Protocol

from app.services.brief import announcement_keywords as kw
from app.services.brief.announcements import Tag, build_listing
from app.services.brief.feed_source import AnnouncementRead, read_announcements
from app.services.brief.insider import parse_trade
from app.services.brief.issued_log import LogRead
from app.services.brief.share_cache import ShareCache, ShareCount, is_fresh
from app.services.brief.sizing import MODE_DISAGREE, MODE_OFF, MODE_OK, MODE_UNAVAILABLE, SizingInput
from app.services.brief.timing import ict_now

if TYPE_CHECKING:
    from app.services.brief.facts import MarketFacts

logger = logging.getLogger(__name__)
MODE_NOT_NEEDED = "not_needed"  # no listed trade states a quantity: the vendor is not asked


class Reading(Protocol):
    count: int
    year_report: int
    quarter: int


ShareCountFn = Callable[[str], Reading]


@dataclass(frozen=True)
class CompanyFacts:
    read: AnnouncementRead
    run_date: date  # the Vietnam date of the run
    previous_last_bar: date | None  # the previous issued brief's last bar for this ticker; None for a first brief
    sizing: SizingInput
    enabled_classes: frozenset[str] = field(default_factory=lambda: kw.ENABLED_KEYWORD_CLASSES)

    @property
    def checked(self) -> bool:
        """At least one kind of announcement has been fetched successfully."""
        return "fetched" in (self.read.news.status, self.read.events.status)

    @property
    def events_checked(self) -> bool:
        """The events kind was fetched successfully: the registered trades and share issues come from it."""
        return self.read.events.status == "fetched"


def stop_after_failure(fetch_fn: ShareCountFn) -> ShareCountFn:
    """`fetch_fn` for one run: after its first failure it is not called again and every later ticker reads as "could not be
    read", as the price refresh does after a rate limit. A disagreement between the vendor's two counts is a fact about one
    ticker, not a failure of the vendor, and does not close the gate."""
    state = {"failed": False}

    def guarded(ticker: str) -> Reading:
        if state["failed"]:
            raise ShareCountStopped()
        try:
            return fetch_fn(ticker)
        except (Exception, SystemExit) as error:
            state["failed"] = state["failed"] or not getattr(error, "disagree", False)
            raise

    return guarded


class ShareCountStopped(Exception):
    """An earlier share-count call of this run failed, so this one was not made."""


def previous_last_bar(log: LogRead, ticker: str, last_bar: str) -> date | None:
    """The latest bar a brief was issued for, strictly before this one (a same-bar re-run reads what an earlier week said).
    An entry whose date is not a real date is skipped."""
    days = []
    for entry in log.for_ticker(ticker):
        if entry.as_of is not None and entry.as_of < last_bar:
            try:
                days.append(date.fromisoformat(entry.as_of))
            except ValueError:
                continue
    return max(days, default=None)


def gather_company_facts(
    ticker: str,
    facts: MarketFacts,
    log: LogRead,
    now: datetime,
    *,
    sizing: bool = True,
    cache: ShareCache | None = None,
    fetch_fn: ShareCountFn | None = None,
    read_fn: Callable[[str], AnnouncementRead] = read_announcements,
) -> CompanyFacts:
    """The facts for one ticker with a last bar; never raises except for a non-limiter `SystemExit` from `fetch_fn`."""
    last_bar = date.fromisoformat(facts.last_bar)
    read = read_fn(ticker)
    previous = previous_last_bar(log, ticker, facts.last_bar)
    base = CompanyFacts(read, ict_now(now).date(), previous, SizingInput(MODE_UNAVAILABLE))
    if not sizing:
        return _with(base, SizingInput(MODE_OFF))
    if not _a_listed_trade_states_a_quantity(read, ticker, last_bar, previous, base.enabled_classes):
        return _with(base, SizingInput(MODE_NOT_NEEDED))
    return _with(base, _resolve_count(ticker, now, cache, fetch_fn))


def _with(base: CompanyFacts, sizing: SizingInput) -> CompanyFacts:
    return CompanyFacts(base.read, base.run_date, base.previous_last_bar, sizing, base.enabled_classes)


def _a_listed_trade_states_a_quantity(
    read: AnnouncementRead, ticker: str, last_bar: date, previous: date | None, enabled: frozenset[str],
) -> bool:
    """True when either copy would list a trade with a stated quantity: the full copy lists since the previous brief, the
    redacted copy lists the fixed 14 days. The vendor is asked for both, so the redacted size line never depends on the log."""
    for since in {previous, None}:
        listing = build_listing(read.items, ticker, last_bar, since, enabled)
        if any(
            listed.classified.tag is Tag.TRADE and parse_trade(listed.classified.item, ticker, last_bar).quantity is not None
            for listed in listing.needs_look
        ):
            return True
    return False


def _resolve_count(ticker: str, now: datetime, cache: ShareCache | None, fetch_fn: ShareCountFn | None) -> SizingInput:
    cached = cache.get(ticker) if cache is not None else None
    if cached is not None and is_fresh(cached, now):
        return SizingInput(MODE_OK, cached)
    usable_stale = cached if cached is not None and cached.fetched_at <= now else None  # never one stamped in the future
    if cached is not None and usable_stale is None and cache is not None:
        cache.note(f"the cached share count for {ticker} is stamped in the future and was not used")
    if fetch_fn is None:
        return SizingInput(MODE_OK, usable_stale) if usable_stale is not None else SizingInput(MODE_UNAVAILABLE)
    try:
        reading = fetch_fn(ticker)
    except (Exception, SystemExit) as error:  # noqa: BLE001 - whatever the vendor did, the line falls back; KeyboardInterrupt still interrupts
        logger.warning("the share count for %s could not be fetched (%s)", ticker, type(error).__name__)
        if getattr(error, "disagree", False):
            return SizingInput(MODE_DISAGREE)  # the two vendor counts differ: no count at all, not even an older cached one
        if usable_stale is not None:
            return SizingInput(MODE_OK, usable_stale)  # the stale value, shown with its own fetch date
        return SizingInput(MODE_UNAVAILABLE)
    entry = ShareCount(reading.count, reading.year_report, reading.quarter, now.astimezone(timezone.utc))
    if cache is not None:
        cache.put(ticker, entry)  # only a cross-checked value ever gets here
    return SizingInput(MODE_OK, entry)
