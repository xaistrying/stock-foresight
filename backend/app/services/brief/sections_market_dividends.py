"""Market-derived dividend, ex-date and week lines, from `MarketFacts` alone.

Everything here comes from the feed events, the stored bars, the adjustment statuses and the displayed
range, so a redacted copy keeps it. What depends on the investor's own entries is in the
investor-side sibling module, and what depends on the issued-brief log (the range clause of the combined
week line and the week-1 recompute) is only produced when `with_previous_range` is true, which the
redacted copy never asks for. Facts without a feed state (`feed is None`) get no line.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.services.brief import corporate_actions as ca
from app.services.brief import dividend_lines as dl
from app.services.brief.facts import MarketFacts
from app.services.brief.week_move import week_plan, week_without_issue

Lines = tuple[str, ...]


def _last_bar(facts: MarketFacts) -> date | None:
    return date.fromisoformat(facts.last_bar) if facts.last_bar else None


def dividends_lines(facts: MarketFacts) -> Lines:
    """The DIVIDENDS header with the feed state. The Scheduled line is printed once, in the COMPANY block."""
    last_bar = _last_bar(facts)
    if facts.feed is None or last_bar is None:
        return ()
    return dl.header_lines(facts.ticker, facts.feed, last_bar)


def window_events(facts: MarketFacts) -> tuple:
    """The events within the calendar-day window after the last bar; none unless the feed was fetched."""
    last_bar = _last_bar(facts)
    if facts.feed is None or facts.feed.status != "fetched" or last_bar is None:
        return ()
    return ca.events_in_window(facts.feed.events, last_bar)


def window_lines(facts: MarketFacts) -> Lines:
    """The ex-date, share-issue and rights-offer lines for NEXT 5 TRADING DAYS, with the range shifted by one dividend."""
    shown = (round(facts.band_lo, 2), round(facts.band_hi, 2)) if facts.band_pct is not None else None
    return dl.window_lines(window_events(facts), shown)


def readjusted_explanation(facts: MarketFacts) -> Lines:
    """After the re-adjusted-close note: the dividends or issues the feed lists after the date the earlier brief logged."""
    last_bar = _last_bar(facts)
    if facts.feed is None or facts.feed.status != "fetched" or facts.readjusted is None or last_bar is None:
        return ()
    as_of = date.fromisoformat(facts.readjusted.date)
    return dl.readjusted_explanation_lines(ca.events_between(facts.feed.events, as_of, last_bar), as_of)


@dataclass(frozen=True)
class WeekExtras:
    """What the dividend logic adds to or takes from N1's week block."""

    combined: Lines = ()  # replaces the move line (board move and footnote)
    replaces_previous_range: bool = False  # the issued range is inside the combined line
    notes: Lines = ()  # after the previous-range and limit sentences
    week_one: Lines = ()  # after the notes; only when the log has no range for the week


def week_extras(facts: MarketFacts, *, with_previous_range: bool) -> WeekExtras:
    week = facts.week
    plan = week_plan(facts.feed, facts.ex_status, facts.dates, facts.closes) if week is not None else None
    if plan is None:
        return WeekExtras()
    notes = dl.week_note_lines(plan, facts.ticker, facts.feed)
    recompute = with_previous_range and week.kind in ("first", "no_match") and facts.model is not None
    one = week_without_issue(plan, facts.dates, facts.closes, facts.model) if recompute else None
    if plan.state != "combined":
        return WeekExtras(notes=notes, week_one=dl.week_one_lines(one, facts.feed) if one else ())
    event = plan.board.event
    clause, replaces = "", False
    if with_previous_range and week.kind == "band":
        clause, replaces = dl.issued_range_clause(week.band_pct, week.inside, event, provisional=week.prior_provisional), True
    elif one is not None:
        clause = dl.recomputed_range_clause(one, event)
    return WeekExtras(
        combined=dl.board_move_lines(plan.board, clause, facts.feed), replaces_previous_range=replaces, notes=notes,
        week_one=dl.week_one_lines(one, facts.feed) if one is not None and not clause else (),
    )
