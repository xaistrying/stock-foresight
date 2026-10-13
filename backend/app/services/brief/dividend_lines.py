"""Renderers for the market-derived dividend, ex-date and share-issue lines.

Pure functions from feed events, a week plan and a few numbers to tuples of lines; every sentence is a
template in `wording.py`. Nothing here receives the investor's data, so a redacted copy keeps these lines
(`dividend_lines_holding.py` holds the ones derived from the investor's purchase date and levels). The only
number computed from a share ratio is its "new shares per 100 held" text and the week's price-adjustment
percentage; no count, cost, total or amount on a share count is produced (that is a later change).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from app.services.brief import corporate_actions as ca
from app.services.brief import wording
from app.services.brief.adjustment_status import AdjustmentStatus
from app.services.brief.feed_source import Event, FeedSnapshot, snapshot_command
from app.services.brief.week_move import BoardMove, WeekOne, WeekPlan

Lines = tuple[str, ...]
MAX_SCHEDULED_ITEMS = 10


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")


def is_cash(event: Event) -> bool:
    return event.event_code == "DIV"


def _is_rights(event: Event) -> bool:
    return event.issue_class is not None and event.issue_class.name == "RIGHTS_OFFER"


def ratio_text(event: Event) -> str:
    return wording.fmt_new_shares(event.exercise_ratio)


def age_text(fetched: date, last_bar: date) -> str:
    """How far `fetched` is from the last bar, in calendar days, printed as is (no staleness threshold)."""
    days = (fetched - last_bar).days
    if days == 0:
        return "on the last bar's date"
    unit = f"{abs(days)} calendar day{'s' if abs(days) != 1 else ''}"
    return f"{unit} {'after' if days > 0 else 'before'} the last bar"


# --- the block header and the feed states ---------------------------------------------------------------
def header_lines(ticker: str, feed: FeedSnapshot, last_bar: date) -> Lines:
    """The DIVIDENDS header with when events were last fetched, or the never-fetched sentence and the command."""
    if feed.status != "fetched":
        template = {
            "never_fetched": wording.NOT_FETCHED, "never_succeeded": wording.NOT_FETCHED_OK,
        }.get(feed.status, wording.NOT_READABLE)
        return (
            wording.DIVIDENDS_HEADER_NO_FETCH, template.format(ticker=ticker, command=snapshot_command([ticker])),
        )
    failed = wording.ATTEMPT_FAILED.format(time=stamp(feed.latest_attempt_at)) if feed.latest_attempt_failed else ""
    header = wording.DIVIDENDS_HEADER.format(
        time=stamp(feed.last_success_at), age=age_text(feed.last_success_at.date(), last_bar), failed=failed,
    )
    unreadable = (wording.UNREADABLE_ROWS.format(count=feed.unreadable),) if feed.unreadable else ()
    return (header, *unreadable)


def _scheduled_item(event: Event) -> str:
    if is_cash(event):
        record = f", record {event.record_date.isoformat()}" if event.record_date else ""
        return wording.SCHEDULED_CASH.format(ex=event.exright_date.isoformat(), amount=wording.fmt_vnd(event.value_per_share), record=record)
    if _is_rights(event):
        return wording.SCHEDULED_RIGHTS.format(ex=event.exright_date.isoformat())
    return wording.SCHEDULED_ISSUE.format(ex=event.exright_date.isoformat(), ratio=ratio_text(event))


def _pending_item(event: Event) -> str:
    what = "bonus shares" if event.issue_class.name == "BONUS" else "stock dividend"
    ratio = f", {ratio_text(event)} new shares per 100 held" if event.exercise_ratio else ""
    return wording.SCHEDULED_PENDING.format(date=event.published_at.isoformat(), what=what, ratio=ratio)


def scheduled_lines(feed: FeedSnapshot, last_bar: date, extra_items: Sequence[str] = ()) -> Lines:
    """The brief's one Scheduled line (printed in the COMPANY block), and the older-announcements line when some
    undated announcement is past its window. `extra_items` are the meeting items the announcements change adds."""
    if feed.status != "fetched":
        return ()
    items = [_scheduled_item(e) for e in ca.scheduled_events(feed.events, last_bar)]
    items += [_pending_item(e) for e in ca.pending_issues(feed.events, last_bar)]
    items += list(extra_items)
    if len(items) > MAX_SCHEDULED_ITEMS:  # a long list is cut, never printed as one unbounded line
        items = [*items[:MAX_SCHEDULED_ITEMS], wording.SCHEDULED_MORE.format(count=len(items) - MAX_SCHEDULED_ITEMS)]
    line = wording.SCHEDULED.format(
        time=stamp(feed.last_success_at), last_bar=last_bar.isoformat(), items="; ".join(items) or wording.SCHEDULED_NONE,
    )
    older = ca.older_undated_count(feed.events, last_bar)
    return (line, wording.OLDER_UNDATED.format(count=older)) if older else (line,)


# --- the window under NEXT 5 TRADING DAYS -----------------------------------------------------------------
def window_lines(in_window: Sequence[Event], shown_range: tuple[float, float] | None) -> Lines:
    """One line per ex-date within the window; `shown_range` is the displayed range (low, high), None when there is none."""
    in_window = tuple(in_window)
    return tuple(_window_line(event, in_window, shown_range) for event in in_window)


def _window_line(event: Event, in_window: tuple[Event, ...], shown_range: tuple[float, float] | None) -> str:
    ex = event.exright_date.isoformat()
    if is_cash(event):
        return wording.WINDOW_CASH.format(
            ex=ex, amount=wording.fmt_vnd(event.value_per_share), shift=_shift_sentence(in_window, shown_range),
            record=wording.RECORD_DATE.format(date=event.record_date.isoformat()) if event.record_date else wording.RECORD_DATE_NONE,
            payout=event.payout_date.isoformat() if event.payout_date else wording.PAYOUT_NONE,
        )
    if _is_rights(event):
        tail = wording.WINDOW_RIGHTS_TAIL if shown_range else wording.WINDOW_TAIL_NO_RANGE
        return wording.WINDOW_RIGHTS.format(ex=ex, tail=tail)
    tail = wording.WINDOW_ISSUE_TAIL if shown_range else wording.WINDOW_TAIL_NO_RANGE
    return wording.WINDOW_ISSUE.format(ex=ex, ratio=ratio_text(event), tail=tail)


def _shift_sentence(in_window: tuple[Event, ...], shown_range: tuple[float, float] | None) -> str:
    if shown_range is None:
        return wording.WINDOW_NO_RANGE
    if len(in_window) > 1:
        return wording.WINDOW_SHIFT_SEVERAL
    shifted = ca.window_range(*shown_range, in_window)
    if shifted is None:
        return wording.WINDOW_SHIFT_NOT_SHOWN
    return wording.WINDOW_SHIFT.format(low=wording.fmt_price(shifted[0]), high=wording.fmt_price(shifted[1]))


# --- the week just ended -----------------------------------------------------------------------------------
def _what(event: Event) -> str:
    return "the dividend" if is_cash(event) else "the issue"


def board_move_lines(move: BoardMove, range_clause: str, feed: FeedSnapshot) -> Lines:
    """The combined line (board move first, the event named in the same sentence) and its footnote, which
    names the source and when its events were fetched."""
    event = move.event
    common = dict(
        board=wording.fmt_signed_pct(move.board_pct), raw=wording.fmt_price(move.raw_prior), last=wording.fmt_price(move.last_close),
        base=wording.fmt_price(move.base_close), excluding=wording.fmt_signed_pct(move.excluding_pct),
        ex=event.exright_date.isoformat(), range=range_clause,
    )
    time = stamp(feed.last_success_at)
    if is_cash(event):
        line = wording.BOARD_CASH.format(amount=wording.fmt_vnd(event.value_per_share), **common)
        return (line, wording.BOARD_FOOTNOTE.format(time=time))
    line = wording.BOARD_ISSUE.format(ratio=ratio_text(event), adjustment=f"{move.adjustment_pct:.1f}%", **common)
    return (line, wording.BOARD_FOOTNOTE_ISSUE.format(time=time))


def _verdict(inside: bool) -> str:
    return "inside" if inside else "outside"


def issued_range_clause(band_pct: float, inside: bool, event: Event, *, provisional: bool) -> str:
    """The range clause of the combined line from the issued band, percent only (unredacted copy only)."""
    clause = wording.BOARD_RANGE_ISSUED.format(band=wording.fmt_band(band_pct), what=_what(event), verdict=_verdict(inside))
    return f"{clause} {wording.PROVISIONAL_ISSUE_NOTE}" if provisional else clause


def recomputed_range_clause(week: WeekOne, event: Event) -> str:
    """The range clause when no range was issued: the recomputed, labelled one; empty if it cannot be made."""
    if week.band_pct is None or week.inside is None:
        return ""
    return wording.BOARD_RANGE_RECOMPUTED.format(
        date=week.base_date, band=wording.fmt_band(week.band_pct), what=_what(event), verdict=_verdict(week.inside),
    )


def week_note_lines(plan: WeekPlan | None, ticker: str, feed: FeedSnapshot | None = None) -> Lines:
    """The market-derived notes under the week: an ex-date not yet adjusted, unclear, several, or an unknown feed."""
    if plan is None or plan.state in ("none", "combined"):
        return ()
    if plan.state == "unknown":
        return (wording.WEEK_UNKNOWN.format(ticker=ticker),)
    time = stamp(feed.last_success_at)
    if plan.state == "several":
        return (_several_line(plan, time),)
    event = plan.events[0].event
    return (f"{_week_event_sentence(event, time)} {_status_sentence(event, plan.state)}",)


def _week_event_sentence(event: Event, time: str) -> str:
    ex = event.exright_date.isoformat()
    if is_cash(event):
        return wording.WEEK_EVENT_CASH.format(ex=ex, amount=wording.fmt_vnd(event.value_per_share), time=time)
    return wording.WEEK_EVENT_ISSUE.format(ex=ex, ratio=ratio_text(event), time=time)


def _status_sentence(event: Event, state: str) -> str:
    ex = event.exright_date.isoformat()
    if state == "not_adjusted":
        return (wording.WEEK_NOT_YET_CASH if is_cash(event) else wording.WEEK_NOT_YET_ISSUE).format(ex=ex)
    return (wording.WEEK_UNCLEAR_CASH if is_cash(event) else wording.WEEK_UNCLEAR_ISSUE).format(ex=ex)


def _several_line(plan: WeekPlan, time: str) -> str:
    dates = [w.event.exright_date.isoformat() for w in plan.events]
    listed = " and ".join([", ".join(dates[:-1]), dates[-1]]) if len(dates) > 2 else " and ".join(dates)
    statuses = ", ".join(f"{day} {wording.STATUS_WORDS[w.status.name]}" for day, w in zip(dates, plan.events))
    return wording.WEEK_SEVERAL.format(time=time, dates=listed, statuses=statuses)


def week_one_lines(week: WeekOne, feed: FeedSnapshot | None = None) -> Lines:
    """The week-1 recomputed line (unredacted copy only), with or without a comparison, or the failure sentence.
    When a fetched feed decides whether the week is compared, the line says which source and when it was fetched."""
    if week.band_pct is None:
        return (wording.WEEK_ONE_FAILED,)
    if week.suppressed is not None:
        verdict = wording.WEEK_ONE_SUPPRESSED.format(reason=wording.WEEK_ONE_REASONS[week.suppressed])
    else:
        verdict = wording.WEEK_ONE_INSIDE if week.inside else wording.WEEK_ONE_OUTSIDE
    line = wording.WEEK_ONE.format(
        date=week.base_date, band=wording.fmt_band(week.band_pct), move=wording.fmt_signed_pct(week.move_pct), verdict=verdict,
    )
    if feed is not None and feed.status == "fetched":
        line += wording.WEEK_ONE_SOURCE.format(time=stamp(feed.last_success_at))
    return (line,)


def readjusted_explanation_lines(events: Sequence[Event], as_of: date) -> Lines:
    """One line per cash dividend or count-changing issue that went ex after the logged date, as a likely explanation."""
    return tuple(_explanation(event, as_of) for event in events)


def _explanation(event: Event, as_of: date) -> str:
    ex, when = event.exright_date.isoformat(), as_of.isoformat()
    if is_cash(event):
        return wording.READJUSTED_EXPLAINS_CASH.format(amount=wording.fmt_vnd(event.value_per_share), ex=ex, as_of=when)
    return wording.READJUSTED_EXPLAINS_ISSUE.format(ratio=ratio_text(event), ex=ex, as_of=when)


def status_clause(status: AdjustmentStatus) -> str:
    """The clause a level note appends: nothing for ADJUSTED."""
    return {AdjustmentStatus.NOT_YET_ADJUSTED: wording.STATUS_NOT_YET, AdjustmentStatus.UNCLEAR: wording.STATUS_UNCLEAR}.get(status, "")
