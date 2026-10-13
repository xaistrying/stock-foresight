"""Rules over feed events: dividends, share issues, what is pending or scheduled, and what is in the window.

Pure functions over `Event` values, no I/O. `Event` is imported for type checking only, so this module
does not pull the feed package into the import closure; the issue class is compared by its name.
Prices in the brief are thousand VND and `value_per_share` is VND, so a shift of a range divides by 1000.

The three day counts are date windows that decide which feed events are printed. None of them is a
threshold on the size of a price move (Rule 3), and none feeds a number: the range, its horizon and the
week just ended stay on 5 sessions (Rule 1).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.brief.feed_source import Event

# Observed announcement-to-ex-date lags: 44 cash dividends in 9 tickers, maximum 85 days (SAB, the next is
# SAB at 81); every other ticker 21 days or fewer. 120 is about 40% over the largest observed lag. It is a
# margin over an observed maximum, not a proven bound.
MAX_LAG_DAYS = 120
# No trading calendar exists, so "the next 5 sessions" selects feed dates by calendar days. A display
# filter only: the range itself stays the model's 5-session band (Rule 1).
WINDOW_CALENDAR_DAYS = 7
# A bonus or stock-dividend announcement with no ex-date is shown while it is this recent; a guess.
PENDING_ANNOUNCEMENT_DAYS = 365

COUNT_CHANGING_CLASSES = frozenset({"BONUS", "STOCK_DIVIDEND"})  # the one definition; others import it
PRICE_UNIT = 1000  # VND per displayed unit (prices are thousand VND)


@dataclass(frozen=True)
class Completeness:
    complete: bool
    oldest: date | None  # the oldest stored event date over every code
    horizon: date | None  # oldest + MAX_LAG_DAYS


@dataclass(frozen=True)
class ShareIssues:
    issues: tuple[Event, ...]
    factor: float  # product of (1 + ratio); calculated


def _is_positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def _class_name(event: Event) -> str | None:
    return event.issue_class.name if event.issue_class is not None else None


def _unique(events: Iterable[Event], key) -> tuple[Event, ...]:
    seen, kept = set(), []
    for event in events:
        if (k := key(event)) not in seen:
            seen.add(k)
            kept.append(event)
    return tuple(kept)


def _by_ex_date(events: Iterable[Event]) -> tuple[Event, ...]:
    return tuple(sorted(events, key=lambda e: (e.exright_date, e.event_code, e.value_per_share or 0.0, e.exercise_ratio or 0.0)))


def cash_dividends(events: Iterable[Event]) -> tuple[Event, ...]:
    """Event code DIV with an ex-date and a positive finite per-share amount, once per (ex-date, amount), ascending."""
    found = (e for e in events if e.event_code == "DIV" and e.exright_date is not None and _is_positive(e.value_per_share))
    return _unique(_by_ex_date(found), lambda e: (e.exright_date, e.value_per_share))


def dividends_since(events: Iterable[Event], after: date, upto: date) -> tuple[Event, ...]:
    """Cash dividends with `after < ex-date <= upto`: a buyer on the ex-date does not receive that dividend."""
    return tuple(e for e in cash_dividends(events) if after < e.exright_date <= upto)


def completeness(oldest_event_date: date | None, purchase_date: date) -> Completeness:
    """Complete iff the purchase is on or after the oldest stored event date plus `MAX_LAG_DAYS`.

    A dividend missing from the store was announced before the oldest stored event, so its ex-date is at
    most `MAX_LAG_DAYS` later. With nothing stored the list is never complete.
    """
    if oldest_event_date is None:
        return Completeness(False, None, None)
    horizon = oldest_event_date + timedelta(days=MAX_LAG_DAYS)
    return Completeness(purchase_date >= horizon, oldest_event_date, horizon)


def count_changing_issues(events: Iterable[Event]) -> tuple[Event, ...]:
    """The issues that change an investor's share count by themselves: class BONUS or STOCK_DIVIDEND, an
    ex-date and a positive ratio, once per (ex-date, ratio), ascending. A rights offer, a private placement,
    an employee issue and an undated announcement are not returned. N3 and N2b use this and do not restate it."""
    found = (
        e for e in events
        if _class_name(e) in COUNT_CHANGING_CLASSES and e.exright_date is not None and _is_positive(e.exercise_ratio)
    )
    return _unique(_by_ex_date(found), lambda e: (e.exright_date, e.exercise_ratio))


def share_issues_between(events: Iterable[Event], after: date, upto: date) -> ShareIssues:
    """Count-changing issues with `after < ex-date <= upto` and their cumulative factor.

    The factor is calculated from the source's ratios and is not checked against a broker: any display of it
    SHALL carry "calculated, check with your broker".
    """
    issues = tuple(e for e in count_changing_issues(events) if after < e.exright_date <= upto)
    factor = 1.0
    for issue in issues:
        factor *= 1 + issue.exercise_ratio
    return ShareIssues(issues, factor)


def pending_issues(events: Iterable[Event], last_bar: date) -> tuple[Event, ...]:
    """BONUS or STOCK_DIVIDEND announcements with no ex-date yet, announced within `PENDING_ANNOUNCEMENT_DAYS`."""
    return tuple(sorted(
        (e for e in _undated(events) if e.published_at is not None and (last_bar - e.published_at).days <= PENDING_ANNOUNCEMENT_DAYS),
        key=lambda e: (e.published_at, e.exercise_ratio or 0.0),
    ))


def older_undated_count(events: Iterable[Event], last_bar: date) -> int:
    """How many such announcements are older than `PENDING_ANNOUNCEMENT_DAYS`: counted, never shown."""
    return sum(e.published_at is None or (last_bar - e.published_at).days > PENDING_ANNOUNCEMENT_DAYS for e in _undated(events))


def _undated(events: Iterable[Event]) -> list[Event]:
    """BONUS or STOCK_DIVIDEND rows with no ex-date; one with no announcement date is counted as older, never dropped."""
    return [e for e in events if _class_name(e) in COUNT_CHANGING_CLASSES and e.exright_date is None]


def rights_offers_between(events: Iterable[Event], after: date, upto: date) -> tuple[Event, ...]:
    """Rights offers to shareholders with `after < ex-date <= upto`; never applied, never in a factor."""
    found = (e for e in events if _class_name(e) == "RIGHTS_OFFER" and e.exright_date is not None and after < e.exright_date <= upto)
    return _unique(_by_ex_date(found), lambda e: (e.exright_date, e.exercise_ratio))


def _dated_actions(events: Iterable[Event], after: date, upto: date) -> tuple[Event, ...]:
    events = tuple(events)
    return _by_ex_date((
        *dividends_since(events, after, upto), *share_issues_between(events, after, upto).issues,
        *rights_offers_between(events, after, upto),
    ))


def events_between(events: Iterable[Event], after: date, upto: date) -> tuple[Event, ...]:
    """Cash dividends and count-changing issues with `after < ex-date <= upto` (level notes, the week, the
    re-adjusted-close explanation). Rights offers are left out: no price effect is calculated for them."""
    events = tuple(events)
    return _by_ex_date((*dividends_since(events, after, upto), *share_issues_between(events, after, upto).issues))


def events_in_window(events: Iterable[Event], last_bar: date) -> tuple[Event, ...]:
    """Dividends, count-changing issues and rights offers within `WINDOW_CALENDAR_DAYS` calendar days after the last bar."""
    return _dated_actions(events, last_bar, last_bar + timedelta(days=WINDOW_CALENDAR_DAYS))


def scheduled_events(events: Iterable[Event], last_bar: date) -> tuple[Event, ...]:
    """Dividends, count-changing issues and rights offers dated after the last bar (the window's too)."""
    return _dated_actions(events, last_bar, date.max)


def shifted_range(low: float, high: float, dividend_vnd: float) -> tuple[float, float] | None:
    """The range moved down by the dividend (VND to thousand VND), rounded to two decimals; None if the low end is not positive."""
    shift = dividend_vnd / PRICE_UNIT
    new_low, new_high = round(low - shift, 2), round(high - shift, 2)
    return (new_low, new_high) if new_low > 0 else None


def window_range(low: float, high: float, in_window: tuple[Event, ...]) -> tuple[float, float] | None:
    """The shifted range, only when exactly one ex-date is in the window and it is a cash dividend."""
    if len(in_window) != 1 or in_window[0].event_code != "DIV":
        return None
    return shifted_range(low, high, in_window[0].value_per_share)
