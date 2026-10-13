"""Renderers for the COMPANY block (`add-announcement-tags-and-insider-sizing`): source health, one listed item, the
trade line with its size and benchmark, and the meeting items of the Scheduled line.

Pure functions from the typed announcements, the sizing result and a few dates to tuples of lines; every fixed
sentence is a constant in `wording_company.py`. Third-party text (a title, a counterparty name) is shown only through
`third_party_text.third_party()`, never inside one of the tool's own sentences, and each such span is labelled.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.services.brief import issue_size
from app.services.brief import wording_company as wc
from app.services.brief.announcements import Listed, Tag
from app.services.brief.company_facts import CompanyFacts
from app.services.brief.corporate_actions import WINDOW_CALENDAR_DAYS
from app.services.brief.dividend_lines import age_text, stamp
from app.services.brief.feed_source import FEED_ITEM_CAP, Announcement, AnnouncementRead, Event, SourceHealth, snapshot_command
from app.services.brief.insider import Trade, WindowStatus, parse_trade
from app.services.brief.sizing import (
    CHANGING, DISAGREE, IMPLAUSIBLE, NO_QUANTITY, OFF, SHOWN, UNAVAILABLE, UNREADABLE, Benchmark, Size, fmt_percent, size_for,
)
from app.services.brief.third_party_text import NAME_LIMIT, TITLE_LIMIT, third_party
from app.services.brief.wording import fmt_new_shares

Lines = tuple[str, ...]
INDENT = "  "
_BASIS_NAMES = {"event record": "BASIS_RECORD", "title keyword": "BASIS_KEYWORD"}
_MEETING_DATE_FIELDS = ("record_date", "exright_date", "issue_date")  # the source's own names; none is called the meeting date


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


# --- source health -------------------------------------------------------------------------------------------
def health_lines(read: AnnouncementRead, ticker: str, last_bar: date) -> Lines:
    """One line per kind (news, then corporate events), the unreadable-rows line, the after-last-fetch sentence when
    something was fetched, and the fetch command (never run) when a kind is missing, failed or unreadable."""
    lines = [
        _health_line(wc.LABEL_NEWS, wc.HEALTH_NEWS, read.news, ticker, last_bar),
        _health_line(wc.LABEL_EVENTS, wc.HEALTH_EVENTS, read.events, ticker, last_bar),
    ]
    if read.unreadable:
        lines.append(wc.HEALTH_UNREADABLE_ROWS.format(count=read.unreadable))
    if "fetched" in (read.news.status, read.events.status):
        lines.append(wc.HEALTH_AFTER_FETCH)
    needs_fetch = any(h.status != "fetched" or h.latest_attempt_failed for h in (read.news, read.events))
    if needs_fetch:
        lines.append(wc.HEALTH_COMMAND.format(command=snapshot_command([ticker])))
    return tuple(lines)


def _health_line(label: str, template: str, health: SourceHealth, ticker: str, last_bar: date) -> str:
    if health.status == "never_fetched":
        return wc.HEALTH_NEVER.format(label=label, ticker=ticker)
    if health.status == "never_succeeded":
        return wc.HEALTH_NEVER_SUCCEEDED.format(label=label, ticker=ticker)
    if health.status != "fetched":
        return wc.HEALTH_UNREADABLE.format(label=label)
    answered = health.last_success_at.date().isoformat()
    if health.latest_attempt_failed:
        return wc.HEALTH_FAILED.format(label=label, when=stamp(health.latest_attempt_at), error=health.error_class or "error", answered=answered)
    count = health.items_returned
    newest = health.newest_published
    return template.format(
        answered=answered, count=_plural(count, "item", "items") if count is not None else "an unknown number of items",
        newest=newest.isoformat() if newest else wc.HEALTH_NO_ITEM,
        limit=wc.HEALTH_LIMIT if count == FEED_ITEM_CAP else "",
        old=wc.HEALTH_OLD.format(days=_plural((last_bar - newest).days, "day", "days")) if newest is not None and newest < last_bar else "",
        age=wc.HEALTH_AGE.format(age=age_text(health.last_success_at.date(), last_bar)),
    )


def unchecked_kinds(read: AnnouncementRead) -> tuple[str, ...]:
    """The kinds with no successful fetch, named for the partial "none found" wording."""
    return tuple(
        name for name, health in ((wc.LABEL_NEWS, read.news), (wc.LABEL_EVENTS, read.events)) if health.status != "fetched"
    )


# --- one listed item ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ItemContext:
    ticker: str
    last_bar: date
    company: CompanyFacts
    events: tuple[Event, ...]  # the typed feed events, for the issue rules
    history: tuple[Trade, ...]  # every parsed trade of the ticker, for the benchmark
    redact: bool = False  # the redacted copy goes to a language model: no third-party title, no counterparty name


def item_lines(listed: Listed, ctx: ItemContext) -> Lines:
    classified, item = listed.classified, listed.classified.item
    marker = wc.MARK_RELISTED if listed.relisted else ""
    tag = getattr(wc, f"TAG_{classified.tag.name}")  # looked up when used, so a changed constant is the one printed
    basis = getattr(wc, _BASIS_NAMES[classified.basis]) if classified.basis else ""
    head = f"- {item.published_at.isoformat()}, {tag}{basis}{marker}"
    body = _body(listed, ctx)
    return (head, *(INDENT + line for line in body))


def _title_line(item: Announcement, ctx: ItemContext) -> str:
    if ctx.redact:
        return wc.TITLE_OMITTED
    return wc.TITLE_LABEL.format(title=third_party(item.title, TITLE_LIMIT))


def _body(listed: Listed, ctx: ItemContext) -> Lines:
    classified, item = listed.classified, listed.classified.item
    if classified.tag is Tag.TRADE:
        return _trade_body(item, ctx)
    lines: list[str] = []
    if item.event_code == "ISS":
        lines.append(_issue_facts(item))
    lines.append(_title_line(item, ctx))
    if classified.tag is Tag.UNCLASSIFIED:
        lines.append(wc.UNCLASSIFIED_NOTE)
    if classified.tag is Tag.CAPITAL and item.event_code != "AIS":
        lines.append(wc.RANGE_SENTENCE)
    return tuple(lines)


def _issue_facts(item: Announcement) -> str:
    kind = wc.ISSUE_KINDS[issue_size.class_name(item)]
    ratio = wc.ISSUE_RATIO.format(ratio=fmt_new_shares(item.exercise_ratio)) if issue_size.ratio_known(item) else wc.ISSUE_RATIO_NONE
    dates = (wc.ISSUE_DATES.format(ex=item.exright_date.isoformat()) if item.exright_date else "") + (
        wc.ISSUE_RECORD.format(record=item.record_date.isoformat()) if item.record_date else ""
    )
    return wc.ISSUE_FACTS.format(kind=kind, ratio=ratio, dates=dates)


# --- the trade line, its size and its benchmark ----------------------------------------------------------------
def _trade_body(item: Announcement, ctx: ItemContext) -> Lines:
    trade = parse_trade(item, ctx.ticker, ctx.last_bar)
    size = size_for(trade, ctx.company.sizing, ctx.events, ctx.company.run_date, ctx.history)
    return (_trade_sentence(trade, ctx), *size_lines(trade, size), _title_line(item, ctx), wc.RANGE_SENTENCE)


def _window_text(trade: Trade) -> str:
    if trade.status is WindowStatus.UNKNOWN or trade.start is None or trade.end is None:
        return wc.TRADE_WINDOW_MISSING
    return wc.TRADE_WINDOW.format(start=trade.start.isoformat(), end=trade.end.isoformat(), status=trade.status.value)


def _trade_sentence(trade: Trade, ctx: ItemContext) -> str:
    if trade.direction is None:
        return wc.TRADE_UNREADABLE
    inside = [wc.TRADE_NO_QUANTITY] if trade.quantity is None else []
    inside.append(_window_text(trade))
    quantity = f"{trade.quantity:,} " if trade.quantity is not None else ""
    if ctx.redact:
        sentence = wc.TRADE_NAMELESS.format(noun=trade.direction, quantity=quantity, ticker=ctx.ticker, inside="; ".join(inside))
    else:
        sentence = wc.TRADE.format(
            name=third_party(trade.name, NAME_LIMIT), noun=trade.direction, quantity=quantity, ticker=ctx.ticker,
            inside="; ".join(inside),
        )
    extra = {WindowStatus.UNDER_WAY: wc.TRADE_UNDER_WAY, WindowStatus.ENDED: wc.TRADE_ENDED}.get(trade.status)
    parts = [sentence, extra] if extra else [sentence]
    if trade.extends_past(ctx.last_bar) and trade.weeks is not None:
        parts.append(wc.TRADE_WEEKS.format(weeks=trade.weeks, unit="week" if trade.weeks == 1 else "weeks"))
    return " ".join(parts)


def size_lines(trade: Trade, size: Size) -> Lines:
    """The size line and, only when a size is shown, the benchmark line."""
    if size.state == SHOWN:
        shown = wc.SIZE_SHOWN.format(
            percent=fmt_percent(size.percent), count=f"{size.count.count:,}", year=size.count.year_report,
            quarter=size.count.quarter, fetched=size.count.fetched_at.date().isoformat(),
        )
        return (shown, benchmark_line(trade, size.benchmark))
    reasons = {
        NO_QUANTITY: wc.SIZE_NO_QUANTITY, OFF: wc.SIZE_OFF, UNAVAILABLE: wc.SIZE_UNAVAILABLE, DISAGREE: wc.SIZE_DISAGREE,
        CHANGING: wc.SIZE_CHANGING, UNREADABLE: wc.SIZE_UNREADABLE, IMPLAUSIBLE: wc.SIZE_IMPLAUSIBLE,
    }
    date_text = size.issue_on.isoformat() if size.issue_on else ""
    return (reasons[size.state].format(checklist=wc.CHECKLIST, date=date_text),)


def benchmark_line(trade: Trade, benchmark: Benchmark | None) -> str:
    if benchmark is None or not benchmark.shown:
        return wc.BENCHMARK_NONE.format(count=benchmark.compared if benchmark else 0)
    larger = wc.BENCHMARK_LARGER_NONE if benchmark.larger == 0 else wc.BENCHMARK_LARGER.format(
        count=benchmark.larger, verb="was" if benchmark.larger == 1 else "were",
    )
    others = (
        wc.BENCHMARK_OTHERS.format(percent=fmt_percent(benchmark.largest_other_pct))
        if benchmark.largest_other_pct is not None else wc.BENCHMARK_NO_OTHERS
    )
    return wc.BENCHMARK.format(
        count=benchmark.compared, nouns=wc.NOUN_PLURALS[trade.direction], year=benchmark.first_year, larger=larger, others=others,
    )


# --- small issues and meetings --------------------------------------------------------------------------------------
def small_issue_line(small: Sequence[Announcement]) -> Lines:
    """One quiet line with counts and class names only, no title and no date."""
    if not small:
        return ()
    names = []
    for item in small:
        name = wc.ISSUE_PLURALS[issue_size.class_name(item)]
        if name not in names:
            names.append(name)
    unstated = any(not issue_size.ratio_known(item) for item in small)
    template = wc.SMALL_ISSUES_UNSTATED if unstated else wc.SMALL_ISSUES
    return (template.format(count=len(small), classes=", ".join(names)),)


def meeting_items(items: Sequence[Announcement], last_bar: date) -> tuple[str, ...]:
    """Meeting events with a date after the last bar and within the calendar-day window, each date with the source's field name."""
    horizon = last_bar + timedelta(days=WINDOW_CALENDAR_DAYS)
    found: list[tuple[date, str]] = []
    for item in items:
        if item.event_code not in wc.MEETING_KINDS:
            continue
        dates = [(name, getattr(item, name)) for name in _MEETING_DATE_FIELDS if getattr(item, name) is not None]
        if not any(last_bar < day <= horizon for _, day in dates):
            continue
        text = wc.SCHEDULED_MEETING.format(
            kind=wc.MEETING_KINDS[item.event_code], dates=", ".join(f"{name} {day.isoformat()}" for name, day in dates),
        )
        found.append((min(day for _, day in dates), text))
    return tuple(text for _, text in sorted(set(found)))
