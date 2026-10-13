"""Renderers for the dividend lines that depend on the investor's own entries: the lists since the purchase
date, the "update your entries" line and the notes under a level.

Pure functions; none runs in a redacted copy (which dividends are listed reveals the purchase date, and a
note reveals a level). No share count, cost, amount on a share count or total is computed or printed: the
lists are per share, and a share issue is shown by its ratio only. The investor's own text is never
touched or repeated here.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from app.services.brief import corporate_actions as ca
from app.services.brief import wording
from app.services.brief.adjustment_status import AdjustmentStatus, status_of
from app.services.brief.dividend_lines import is_cash, ratio_text, status_clause
from app.services.brief.feed_source import Event, FeedSnapshot

Lines = tuple[str, ...]


def since_purchase_lines(feed: FeedSnapshot | None, purchase_date: date | None, last_bar: date) -> Lines:
    """Cash dividends, share issues and rights offers with an ex-date after the purchase date, per share, not added up."""
    if feed is None or feed.status != "fetched":
        return ()
    if purchase_date is None:
        return (wording.NO_PURCHASE_DATE,)
    return (*_cash_lines(feed, purchase_date, last_bar), *_issue_lines(feed, purchase_date, last_bar))


def _cash_lines(feed: FeedSnapshot, purchase_date: date, last_bar: date) -> Lines:
    listed = ca.dividends_since(feed.events, purchase_date, last_bar)
    items = ", ".join(f"{wording.fmt_vnd(e.value_per_share)} (ex {e.exright_date.isoformat()})" for e in listed) or wording.SINCE_NONE
    if feed.oldest_event_date is None:
        return (wording.SINCE_NO_SOURCE_DATE.format(items=items), wording.INCOMPLETE_NOTHING)
    lines = (wording.SINCE_CASH.format(oldest=feed.oldest_event_date.isoformat(), items=items),)
    completeness = ca.completeness(feed.oldest_event_date, purchase_date)
    if completeness.complete:
        return lines
    incomplete = wording.INCOMPLETE.format(
        horizon=completeness.horizon.isoformat(), oldest=completeness.oldest.isoformat(), lag=ca.MAX_LAG_DAYS,
    )
    return (*lines, incomplete)


def _issue_lines(feed: FeedSnapshot, purchase_date: date, last_bar: date) -> Lines:
    issues = ca.share_issues_between(feed.events, purchase_date, last_bar).issues
    if issues:
        items = "; ".join(wording.SINCE_ISSUE_ITEM.format(ex=e.exright_date.isoformat(), ratio=ratio_text(e)) for e in issues)
        lines = (wording.SINCE_ISSUES.format(items=items),)
    else:
        lines = (wording.SINCE_ISSUES_NONE,)
    offers = ca.rights_offers_between(feed.events, purchase_date, last_bar)
    return (*lines, *(wording.SINCE_RIGHTS.format(ex=e.exright_date.isoformat()) for e in offers))


def update_entries_lines(in_window: Sequence[Event]) -> Lines:
    """For each count-changing issue within the window: the investor's share count and cost per share change."""
    return tuple(wording.UPDATE_ENTRIES.format(ex=e.exright_date.isoformat()) for e in ca.count_changing_issues(in_window))


def level_note_lines(
    feed: FeedSnapshot | None, ex_status: Sequence[tuple[Event, AdjustmentStatus]], entered: date, last_bar: date,
) -> Lines:
    """One note per cash dividend or count-changing issue that went ex after the level was entered; the level is never changed."""
    if feed is None or feed.status != "fetched":
        return ()
    return tuple(_level_note(e, status_of(e, ex_status), entered) for e in ca.events_between(feed.events, entered, last_bar))


def _level_note(event: Event, status: AdjustmentStatus, entered: date) -> str:
    common = dict(ex=event.exright_date.isoformat(), entered=entered.isoformat(), status=status_clause(status))
    if is_cash(event):
        return wording.LEVEL_NOTE_CASH.format(amount=wording.fmt_vnd(event.value_per_share), **common)
    return wording.LEVEL_NOTE_ISSUE.format(ratio=ratio_text(event), **common)
