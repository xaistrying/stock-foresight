"""The size of a registered trade against the shares outstanding, and its benchmark (`add-announcement-tags-and-insider-sizing`).

Pure. A size is shown only when the trade states a quantity, a cross-checked vendor count is available and no recent
issue makes the count unsafe. The count is withheld when an issue that changes the company's count by at least
`ISSUE_MATERIAL_RATIO` is dated after the cached value was fetched or within `SETTLING_DAYS` before the run date; every
issue class counts, employee issues under 1% are ignored and a non-employee issue of unknown size counts as material
(`issue_size`). The rule is company-wide and is not the investor's count-changing rule of `corporate_actions`, which is
used only for the benchmark's cumulative factor. The fallback (no size) is as complete as the sized line.

The benchmark compares the trade with earlier registrations of the same direction that state a quantity, each against
the share count at its own date (today's count divided by the factor of the count-changing issues since that date),
inside a comparable period that starts at the latest issue that the factor does not cover. It needs
`BENCHMARK_MIN_RECORDS` records and is never shown without a size. The effect of showing a size on a real reader is
untested: the no-size path is first-class.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.services.brief import corporate_actions as ca
from app.services.brief import issue_size
from app.services.brief.feed_source import Event
from app.services.brief.insider import Trade
from app.services.brief.share_cache import ShareCount

# Policy constant resting on one example (VPB's ratio_summary() moved within about 17 days of an ex-date while
# overview() had not converged at 18); the true settling window is not measured.
SETTLING_DAYS = 30
BENCHMARK_MIN_RECORDS = 5  # fewer earlier records than this is not a comparison

# What the share count input is, before any rule is applied.
MODE_OK, MODE_OFF, MODE_UNAVAILABLE, MODE_DISAGREE = "ok", "off", "unavailable", "disagree"
# What a trade's size line can be.
SHOWN, NO_QUANTITY, OFF, UNAVAILABLE, DISAGREE, CHANGING = "shown", "no_quantity", "off", "unavailable", "disagree", "changing"
UNREADABLE, IMPLAUSIBLE = "unreadable", "implausible"  # the title could not be read; the quantity exceeds the share count


@dataclass(frozen=True)
class SizingInput:
    mode: str  # MODE_*
    count: ShareCount | None = None  # set when mode is MODE_OK


@dataclass(frozen=True)
class Benchmark:
    compared: int
    shown: bool  # at least BENCHMARK_MIN_RECORDS
    first_year: int | None = None
    larger: int = 0
    largest_other_pct: float | None = None  # the largest of the records that were not larger; None when all were larger


@dataclass(frozen=True)
class Size:
    state: str  # SHOWN | NO_QUANTITY | OFF | UNAVAILABLE | DISAGREE | CHANGING | UNREADABLE | IMPLAUSIBLE
    percent: float | None = None
    count: ShareCount | None = None
    issue_on: date | None = None  # CHANGING: the date of the issue that makes the count unsafe
    benchmark: Benchmark | None = None


def changing_issue_date(events: Iterable[Event], fetched_on: date | None, run_date: date) -> date | None:
    """The latest date of a material issue dated after `fetched_on` or within `SETTLING_DAYS` before `run_date`."""
    found = []
    for event in events:
        if event.event_code != "ISS" or issue_size.is_small(event):
            continue
        day = issue_size.issue_date(event)
        if day is not None and ((fetched_on is not None and day > fetched_on) or day >= run_date - timedelta(days=SETTLING_DAYS)):
            found.append(day)
    return max(found, default=None)


def size_for(
    trade: Trade, sizing: SizingInput, events: Sequence[Event], run_date: date, history: Sequence[Trade],
) -> Size:
    """The size state of `trade`; `history` is every parsed trade of the ticker (the trade itself may be in it)."""
    if trade.direction is None:
        return Size(UNREADABLE)  # the title is not trusted, so neither is a quantity read from it
    if trade.quantity is None:
        return Size(NO_QUANTITY)
    if sizing.mode == MODE_OFF:
        return Size(OFF)
    if sizing.mode != MODE_DISAGREE and (sizing.mode != MODE_OK or sizing.count is None):
        return Size(UNAVAILABLE)  # unavailable, or any mode that did not produce a count
    fetched_on = sizing.count.fetched_at.date() if sizing.count is not None else None
    changing = changing_issue_date(events, fetched_on, run_date)
    if changing is not None:
        return Size(CHANGING, issue_on=changing)
    if sizing.mode == MODE_DISAGREE:
        return Size(DISAGREE)
    percent = trade.quantity / sizing.count.count * 100
    if percent > 100:
        return Size(IMPLAUSIBLE)  # more shares than the company has: the title or the count is wrong
    return Size(SHOWN, percent=percent, count=sizing.count, benchmark=benchmark(trade, history, events, sizing.count.count, run_date, percent))


def _uncovered_issue_start(events: Sequence[Event]) -> date | None:
    """The latest material issue that the count-changing factor does not cover: a rights offer, a placement, another
    class, or a bonus or stock dividend without an ex-date. Everything earlier has an unknowable count."""
    days = [
        issue_size.issue_date(e) for e in events
        if e.event_code == "ISS" and issue_size.is_material(e) and not ca.count_changing_issues((e,))
    ]
    return max((day for day in days if day is not None), default=None)


def benchmark(
    current: Trade, history: Sequence[Trade], events: Sequence[Event], count: int, run_date: date, current_percent: float,
) -> Benchmark:
    start = _uncovered_issue_start(events)
    earlier = [
        t for t in history
        if t.item is not current.item and t.direction == current.direction and t.quantity is not None
        and t.item.published_at < current.item.published_at and (start is None or t.item.published_at > start)
    ]
    if len(earlier) < BENCHMARK_MIN_RECORDS:
        return Benchmark(compared=len(earlier), shown=False)
    percents = [t.quantity / (count / ca.share_issues_between(events, t.item.published_at, run_date).factor) * 100 for t in earlier]
    others = [p for p in percents if p <= current_percent]
    return Benchmark(
        compared=len(earlier), shown=True, first_year=min(t.item.published_at.year for t in earlier),
        larger=len(percents) - len(others), largest_other_pct=max(others, default=None),
    )


def fmt_percent(value: float) -> str:
    """At most two significant figures, never in exponent form: 2.3, 0.016, 150."""
    return format(Decimal(f"{value:.2g}"), "f")
