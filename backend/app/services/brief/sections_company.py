"""The COMPANY block of one ticker and its re-read trigger counts (`add-announcement-tags-and-insider-sizing`).

Pure functions of `MarketFacts` (which carries the announcement facts) to tuples of lines. Nothing in the block derives
from the investor's holdings, so a redacted copy keeps it; what the issued-brief log decides (which brief came before,
and so "since the last brief" and "first brief") is left out of the redacted copy: it lists the 14 days before the last
bar and says nothing about earlier briefs. The redacted copy goes to a language model, so it also shows no third-party
title and no counterparty name (a stored title can carry instructions in plain English); the full copy shows both,
sanitised and quoted. Dates, tags, window states, quantities, sizes and the read-the-notice fallback stay. Facts without announcement facts (`company is None`) get no block, which is
how every earlier test and golden file stays valid.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from app.services.brief import company_lines as cl
from app.services.brief import dividend_lines as dl
from app.services.brief import wording_company as wc
from app.services.brief.announcements import Listing, Tag, build_listing, classify
from app.services.brief.company_facts import CompanyFacts
from app.services.brief.facts import MarketFacts
from app.services.brief.insider import parse_trade
from app.services.brief.wording import TriggerCount

Lines = tuple[str, ...]


def company_listing(facts: MarketFacts, *, redact: bool = False) -> Listing | None:
    """The listing for one ticker, or None when the announcements were not read (or there is no last bar)."""
    if facts.company is None or facts.last_bar is None:
        return None
    company = facts.company
    previous = None if redact else company.previous_last_bar
    return build_listing(company.read.items, facts.ticker, date.fromisoformat(facts.last_bar), previous, company.enabled_classes)


def company_lines(facts: MarketFacts, *, redact: bool) -> Lines:
    """The COMPANY block: heading, source health, the three parts, in that order."""
    listing = company_listing(facts, redact=redact)
    if listing is None:
        return ()
    company, last_bar = facts.company, date.fromisoformat(facts.last_bar)
    events = facts.feed.events if facts.feed is not None else ()
    history = tuple(
        parse_trade(item, facts.ticker, last_bar) for item in company.read.items
        if classify(item, facts.ticker, company.enabled_classes).tag is Tag.TRADE
    )
    ctx = cl.ItemContext(facts.ticker, last_bar, company, tuple(events), history, redact=redact)
    empty = _empty_text(company)
    lines = [wc.COMPANY_HEADING_REDACTED if redact else wc.COMPANY_HEADING, *cl.health_lines(company.read, facts.ticker, last_bar)]
    needs_tail = [wc.NEEDS_MORE.format(count=listing.needs_more, shown=len(listing.needs_shown))] if listing.needs_more else []
    lines += _part(_needs_heading(listing, redact), [cl.item_lines(l, ctx) for l in listing.needs_shown], empty, tail=needs_tail)
    information = [cl.item_lines(l, ctx) for l in listing.information_shown]
    tail: list[str] = []
    if listing.information_more:
        tail.append(wc.INFORMATION_MORE.format(count=listing.information_more, shown=len(listing.information_shown)))
    if company.read.events.status == "fetched":
        tail += cl.small_issue_line(listing.small_issues)
    lines += _part(wc.INFORMATION, information, empty, tail=tail)
    lines += _scheduled(facts, last_bar)
    return tuple(lines)


def _needs_heading(listing: Listing, redact: bool) -> str:
    if redact:
        return wc.NEEDS_FIXED
    return wc.NEEDS_FIRST if listing.lookback else wc.NEEDS_SINCE


def _empty_text(company: CompanyFacts) -> str:
    """"not checked" when nothing was fetched; "none found" after a successful fetch, naming a kind that was not fetched."""
    if not company.checked:
        return wc.PART_NOT_CHECKED
    missing = cl.unchecked_kinds(company.read)
    return wc.PART_PARTIAL.format(unchecked=" and ".join(missing)) if missing else wc.PART_NONE


def _part(heading: str, items: list[Lines], empty: str, *, tail: Sequence[str] = ()) -> list[str]:
    if not items and not tail:
        return [f"{heading} {empty}"]
    lines = [heading]
    for item in items:
        lines += item
    return lines + list(tail)


def _scheduled(facts: MarketFacts, last_bar: date) -> Lines:
    """The brief's one Scheduled line: dated dividends and count-changing issues from the dividend logic, plus meetings."""
    feed = facts.feed
    if feed is None or feed.status != "fetched":
        return (wc.SCHEDULED_NOT_CHECKED,)
    return dl.scheduled_lines(feed, last_bar, cl.meeting_items(facts.company.read.items, last_bar))


# --- the re-read triggers (counts only; appended to the base line by `compose`) -----------------------------------
def _read_facts(all_facts: tuple[MarketFacts, ...]) -> tuple[MarketFacts, ...]:
    return tuple(f for f in all_facts if f.company is not None and f.last_bar is not None)


def _count_new(all_facts: tuple[MarketFacts, ...], tag: Tag) -> int:
    """Items under "Needs a look" that are new since the last brief; listed-again windows, small issues and additional
    listings never reach this list or are not new."""
    return sum(
        listed.is_new and listed.classified.tag is tag
        for facts in _read_facts(all_facts) for listed in company_listing(facts).needs_look
    )


def trades_trigger_count(all_facts: tuple[MarketFacts, ...]) -> TriggerCount | None:
    if not _read_facts(all_facts):
        return None
    return TriggerCount(wc.TRIGGER_TRADES_LABEL, _count_new(all_facts, Tag.TRADE))


def issues_trigger_count(all_facts: tuple[MarketFacts, ...]) -> TriggerCount | None:
    if not _read_facts(all_facts):
        return None
    return TriggerCount(wc.TRIGGER_ISSUES_LABEL, _count_new(all_facts, Tag.CAPITAL))


def unchecked_trigger_count(all_facts: tuple[MarketFacts, ...]) -> TriggerCount | None:
    """Holdings whose announcements were not checked; omitted at 0 so the line carries no clutter. The registered trades and
    share issues come from the events kind, so a holding whose events were never fetched counts, and so does a holding with no
    announcement facts (no stored price to date them against) while another holding was read."""
    if not _read_facts(all_facts):
        return None
    unchecked = sum(f.company is None or not f.company.events_checked or f.last_bar is None for f in all_facts)
    return TriggerCount(wc.TRIGGER_UNCHECKED_LABEL, unchecked) if unchecked else None
