"""The week just ended around an ex-date: its events, the board move, and the week-1 recomputed range.

Pure functions over stored bars, feed events and their adjustment statuses. The week is the last five
stored sessions (`dates[-6]` the base, `dates[-1]` the end): exact, no calendar approximation. Prices are
thousand VND and `value_per_share` is VND. Every move is a simple percentage computed from two-decimal
prices (Rule 2); the inside/outside test is the model's, in log space, as the issued-range comparison does.

    raw prior close (the board price at the base bar):  cash  s * (eve + D) / eve      issue  s * (1 + r)
    board move       (c - raw prior) / raw prior        move excluding the event   (c - s) / s

`s` and `c` are the stored closes at the base and last bars, `eve` the stored close on the last session
before the ex-date. The board figures assume the vendor's conventions (cash (P - D) / P, stock 1 / (1 + r)),
confirmed on several tickers, and are only produced when the stored history is ADJUSTED for the event.
Nothing here reads or writes the issued-brief log.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import numpy as np

from app.ml.volatility import HORIZON_SESSIONS, HarModel, band_from_sigma, sigma_daily_pct_from_closes, sigma_out_of_bounds
from app.services.brief.adjustment_status import AdjustmentStatus, status_of
from app.services.brief.corporate_actions import COUNT_CHANGING_CLASSES, PRICE_UNIT, events_between

if TYPE_CHECKING:
    from app.services.brief.feed_source import Event, FeedSnapshot

_PRICE_DECIMALS = 2


@dataclass(frozen=True)
class WeekEvent:
    event: Event
    status: AdjustmentStatus


@dataclass(frozen=True)
class BoardMove:
    event: Event
    raw_prior: float  # the board price at the base bar, two decimals
    board_pct: float
    excluding_pct: float  # the stored (adjusted) move
    base_close: float  # s, two decimals
    last_close: float  # c, two decimals
    adjustment_pct: float | None  # for an issue: r / (1 + r), percent of the price


@dataclass(frozen=True)
class WeekPlan:
    state: str  # none | unknown | combined | not_adjusted | unclear | several
    events: tuple[WeekEvent, ...]
    board: BoardMove | None


@dataclass(frozen=True)
class WeekOne:
    """The week-1 recompute: `band_pct` is None when it cannot be made; `suppressed` says why no verdict is given."""

    base_date: str
    move_pct: float  # simple percent over the week, stored closes
    band_pct: float | None
    inside: bool | None
    suppressed: str | None  # unknown | several | not_adjusted


def week_events(events: Sequence[Event], dates: Sequence[str]) -> tuple[Event, ...]:
    """Cash dividends and count-changing issues with `dates[-6] < ex-date <= dates[-1]`; none with fewer than 6 bars."""
    if len(dates) < HORIZON_SESSIONS + 1:
        return ()
    return events_between(events, date.fromisoformat(dates[-HORIZON_SESSIONS - 1]), date.fromisoformat(dates[-1]))


def board_move(event: Event, dates: Sequence[str], closes: Sequence[float]) -> BoardMove | None:
    """The board move and the move excluding `event`, or None for an event with no calculable price effect."""
    if len(dates) < HORIZON_SESSIONS + 1 or event.exright_date is None:
        return None
    base, last = round(float(closes[-HORIZON_SESSIONS - 1]), _PRICE_DECIMALS), round(float(closes[-1]), _PRICE_DECIMALS)
    adjustment = None
    if event.event_code == "DIV" and event.value_per_share:
        eve = _eve_close(event.exright_date, dates, closes)
        if eve is None or eve <= 0:
            return None
        raw = base * (eve + event.value_per_share / PRICE_UNIT) / eve
    elif event.issue_class is not None and event.issue_class.name in COUNT_CHANGING_CLASSES and event.exercise_ratio:
        raw = base * (1 + event.exercise_ratio)
        adjustment = event.exercise_ratio / (1 + event.exercise_ratio) * 100
    else:
        return None
    raw = round(raw, _PRICE_DECIMALS)
    return BoardMove(event, raw, (last - raw) / raw * 100, (last - base) / base * 100, base, last, adjustment)


def _eve_close(ex_date: date, dates: Sequence[str], closes: Sequence[float]) -> float | None:
    earlier = [i for i, day in enumerate(dates) if day < ex_date.isoformat()]
    return float(closes[earlier[-1]]) if earlier else None


def week_plan(
    feed: FeedSnapshot | None, ex_status: Sequence[tuple[Event, AdjustmentStatus]], dates: Sequence[str], closes: Sequence[float],
) -> WeekPlan | None:
    """What the week block says about ex-dates; None when the feed was not read or there are fewer than 6 bars."""
    if feed is None or len(dates) < HORIZON_SESSIONS + 1:
        return None
    if feed.status != "fetched":
        return WeekPlan("unknown", (), None)
    found = tuple(WeekEvent(e, status_of(e, ex_status)) for e in week_events(feed.events, dates))
    if not found:
        return WeekPlan("none", (), None)
    if len(found) > 1:
        return WeekPlan("several", found, None)
    status = found[0].status
    if status is AdjustmentStatus.ADJUSTED:
        board = board_move(found[0].event, dates, closes)
        return WeekPlan("combined", found, board) if board else WeekPlan("unclear", found, None)
    return WeekPlan("not_adjusted" if status is AdjustmentStatus.NOT_YET_ADJUSTED else "unclear", found, None)


def recomputed_band(closes: Sequence[float], model: HarModel) -> float | None:
    """The half-width of the typical 5-session move from the closes up to the base bar, percent; None if not computable."""
    sigma = sigma_daily_pct_from_closes(np.asarray(closes[:-HORIZON_SESSIONS], dtype=float), model)
    if sigma is None or sigma_out_of_bounds(sigma):
        return None
    return band_from_sigma(sigma, model)


def week_without_issue(plan: WeekPlan | None, dates: Sequence[str], closes: Sequence[float], model: HarModel) -> WeekOne:
    """The week-1 fallback: a range recomputed today from the prices up to the base bar, compared in log space.

    The comparison is made on stored closes (the move excluding any event) when no event fell in the week or
    exactly one did and its history is adjusted; otherwise it is suppressed and the reason is given.
    """
    base, last = float(closes[-HORIZON_SESSIONS - 1]), float(closes[-1])
    band = recomputed_band(closes, model)
    reason = _suppression(plan)
    inside = None if band is None or reason else abs(math.log(last / base)) * 100 <= band
    return WeekOne(dates[-HORIZON_SESSIONS - 1], (last / base - 1) * 100, band, inside, reason)


def _suppression(plan: WeekPlan | None) -> str | None:
    if plan is None or plan.state in ("none", "combined"):
        return None
    return {"unknown": "unknown", "several": "several"}.get(plan.state, "not_adjusted")
