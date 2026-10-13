"""Run-time facts about a bar: is it provisional, is it stale.

There is no trading calendar in the repository, so staleness is a stated heuristic in calendar days.
Vietnam has no daylight saving, so a fixed UTC+7 offset stands in for a timezone database.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

ICT = timezone(timedelta(hours=7))
PROVISIONAL_BEFORE = time(15, 15)  # end-of-day values are final from here (the review's figure, not an exchange rule)
STALE_AFTER_CALENDAR_DAYS = 5


def ict_now(now: datetime) -> datetime:
    return now.astimezone(ICT)


def provisional_bar(last_bar: str | None, now: datetime) -> bool:
    """True when the bar is today's (ICT) and the session may still be open."""
    local = ict_now(now)
    return last_bar == local.date().isoformat() and local.time() < PROVISIONAL_BEFORE


def stale_reasons(last_bar: str | None, newest_bar: str | None, now: datetime) -> tuple[str, ...]:
    """`behind_newest` and/or `old` for a holding whose bar is stale; empty when fresh or no bar."""
    if last_bar is None:
        return ()
    reasons = []
    if newest_bar is not None and last_bar < newest_bar:
        reasons.append("behind_newest")
    if (ict_now(now).date() - date.fromisoformat(last_bar)).days > STALE_AFTER_CALENDAR_DAYS:
        reasons.append("old")
    return tuple(reasons)
