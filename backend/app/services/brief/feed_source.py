"""The brief's one reader of the company feed (`add-dividend-and-ex-date-lines`).

This is the only file under `backend/app/services/brief/` that names the feed. It imports the store
module of the feed package and nothing else from it, uses only the two read-only helpers
(`latest_items`, `last_fetch`), and returns typed events. It cannot start a fetch, cannot import the
vendor library, and writes nothing: the log is opened `mode=ro` by the store, and a missing or
unreadable log reads as "never fetched".

No stored text leaves this module through an `Event`. The one value derived from a title is an
`IssueClass`, computed here from keywords and returned as an enumeration; the title itself is dropped.
`read_announcements` (`add-announcement-tags-and-insider-sizing`) is the one other reader: it returns the
stored title with the dates and event fields the brief names, as a separate `Announcement` type, and never
the source name, source link, author or snippet. The brief shows a title only through the sanitiser.
The command that fetches the events is text only: the brief prints it for the owner to run by hand and
never runs it.
"""

from __future__ import annotations

import logging
import math
import re
import shlex
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum

from app.services.brief.timing import ICT
from app.services.company_feed import store

logger = logging.getLogger(__name__)

KIND_EVENTS = "events"
KIND_NEWS = "news"
# The source returns at most this many items per call (a test ties it to the fetch module's cap).
FEED_ITEM_CAP = 50
NEVER_FETCHED, NEVER_SUCCEEDED, FETCHED = "never_fetched", "never_succeeded", "fetched"
UNREADABLE = "unreadable"  # the log exists but could not be read this run: not the same as never fetched
_FAILED_STATUSES = (store.STATUS_RATE_LIMITED, store.STATUS_ERROR)
_DATE_CHARS = len("YYYY-MM-DD")
# Plausibility bounds: a value outside them is an unreadable cell, so an absurd number is never printed.
_MIN_DATE, _MAX_DATE = date(1990, 1, 1), date(2100, 1, 1)
_MAX_VND_PER_SHARE = 10_000_000.0
_MAX_RATIO = 10.0  # new shares per share held
_ERROR_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,63}")  # a class name, so nothing else is ever printed from the log
_SNAPSHOT_COMMAND = "python backend/scripts/snapshot_company_feed.py --tickers "


class IssueClass(Enum):
    """The class of an `ISS` event, from the title's keywords. N3 reuses these names."""

    BONUS = "BONUS"
    STOCK_DIVIDEND = "STOCK_DIVIDEND"
    RIGHTS_OFFER = "RIGHTS_OFFER"
    PRIVATE_PLACEMENT = "PRIVATE_PLACEMENT"
    EMPLOYEE = "EMPLOYEE"
    OTHER = "OTHER"


# First match wins, in this order. Keywords are written in NFC and casefolded when compared.
_KEYWORDS: tuple[tuple[IssueClass, str], ...] = (
    (IssueClass.STOCK_DIVIDEND, "Trả Cổ tức bằng Cổ phiếu"),
    (IssueClass.BONUS, "Cổ phiếu thưởng"),
    (IssueClass.RIGHTS_OFFER, "Quyền mua"),
    (IssueClass.PRIVATE_PLACEMENT, "riêng lẻ"),
    (IssueClass.EMPLOYEE, "CBCNV"),
)


@dataclass(frozen=True)
class Event:
    """One stored company event: codes, dates and numbers only. `value_per_share` is VND."""

    event_code: str
    exright_date: date | None
    record_date: date | None
    payout_date: date | None
    value_per_share: float | None
    exercise_ratio: float | None  # new shares per share held, for an issue
    published_at: date | None
    issue_class: IssueClass | None  # only for event code ISS


@dataclass(frozen=True)
class FeedSnapshot:
    """What the feed holds for one ticker, and how fresh it is."""

    status: str  # never_fetched | never_succeeded | fetched | unreadable
    events: tuple[Event, ...] = ()
    oldest_event_date: date | None = None  # oldest `published_at` over every stored event, whatever its code
    unreadable: int = 0  # rows or cells that could not be read
    last_success_at: datetime | None = None  # UTC
    latest_attempt_at: datetime | None = None  # UTC
    latest_attempt_failed: bool = False


@dataclass(frozen=True)
class Announcement:
    """One stored announcement (a news item or an event row): the stored title, to be shown only as
    sanitised third-party text, and the dates and event fields the brief reads. No source name, link,
    author or snippet."""

    kind: str  # news | events
    published_at: date
    first_seen: date | None  # the Vietnam date on which the log first stored the item, like the bar dates
    from_first_fetch: bool  # it arrived in the first successful fetch of its ticker and kind: history, not news
    title: str
    event_code: str | None = None  # events only
    action_type_en: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    exright_date: date | None = None
    issue_date: date | None = None
    listing_date: date | None = None
    record_date: date | None = None
    exercise_ratio: float | None = None
    issue_class: IssueClass | None = None  # only for event code ISS


@dataclass(frozen=True)
class SourceHealth:
    """When one kind (news or events) was last answered, and how old its newest stored item is."""

    status: str  # never_fetched | never_succeeded | fetched | unreadable
    last_success_at: datetime | None = None  # UTC
    latest_attempt_at: datetime | None = None
    latest_attempt_failed: bool = False
    error_class: str | None = None  # of a failed latest attempt
    items_returned: int | None = None  # of the latest attempt, only when it succeeded
    newest_published: date | None = None


@dataclass(frozen=True)
class AnnouncementRead:
    items: tuple[Announcement, ...] = ()
    news: SourceHealth = SourceHealth(NEVER_FETCHED)
    events: SourceHealth = SourceHealth(NEVER_FETCHED)
    unreadable: int = 0  # rows that could not be read or carry no date or title


def snapshot_command(tickers: Sequence[str]) -> str:
    """The command that fetches events for `tickers`; printed for the owner, never run."""
    return _SNAPSHOT_COMMAND + ",".join(shlex.quote(ticker) for ticker in tickers)


def read_events(ticker: str) -> FeedSnapshot:
    """The stored events of `ticker` and the feed state; never raises (an unreadable log is "never fetched")."""
    try:
        latest = store.last_fetch(ticker, KIND_EVENTS)
        if latest is None:
            return FeedSnapshot(NEVER_FETCHED)
        attempt = dict(latest_attempt_at=_utc(latest.latest.fetched_at), latest_attempt_failed=latest.latest.status in _FAILED_STATUSES)
        if latest.last_success_at is None:
            return FeedSnapshot(NEVER_SUCCEEDED, **attempt)
        fetched = _utc(latest.last_success_at)
        if fetched is None:  # a time the brief cannot state is not a fetch it can vouch for
            return FeedSnapshot(UNREADABLE)
        events, unreadable, oldest = _typed(store.latest_items(ticker, KIND_EVENTS))
        return FeedSnapshot(
            FETCHED, events=events, oldest_event_date=oldest, unreadable=unreadable, last_success_at=fetched, **attempt,
        )
    except Exception:  # noqa: BLE001 - a feed problem must never remove a holding's block
        logger.exception("reading the stored events for %s failed", ticker)
        return FeedSnapshot(UNREADABLE)


def _typed(items: Iterable[store.StoredItem]) -> tuple[tuple[Event, ...], int, date | None]:
    events: list[Event] = []
    unreadable = 0
    published: list[date] = []
    for item in items:
        try:
            event, bad = _event(item)
        except Exception:  # noqa: BLE001 - one malformed row is counted, never allowed to hide the others
            logger.warning("a stored event row of %s could not be read", item.ticker, exc_info=True)
            event, bad = None, 1
        unreadable += bad
        if event is not None:
            events.append(event)
        if (day := _parse_date(item.published_at)) is not None:
            published.append(day)
    return tuple(events), unreadable, min(published, default=None)


def _event(item: store.StoredItem) -> tuple[Event | None, int]:
    """The typed event for a stored row and the number of cells that could not be read; None without an event code."""
    fields = item.fields
    if not isinstance(fields, dict):
        return None, 1
    code = fields.get("event_code")
    if not isinstance(code, str) or not code.strip():
        return None, 1
    bad = 0
    dates = {}
    for name in ("exright_date", "record_date", "payout_date"):
        dates[name] = _parse_date(fields.get(name))
        bad += fields.get(name) is not None and dates[name] is None
    published = _parse_date(item.published_at)
    bad += item.published_at is not None and published is None
    numbers = {}
    for name, ceiling in (("value_per_share", _MAX_VND_PER_SHARE), ("exercise_ratio", _MAX_RATIO)):
        numbers[name] = _number(fields.get(name), ceiling)
        bad += fields.get(name) is not None and numbers[name] is None
    issue_class = _issue_class(item.title) if code.strip() == "ISS" else None
    return Event(
        event_code=code.strip(), published_at=published, issue_class=issue_class, **dates, **numbers,
    ), bad


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        day = date.fromisoformat(value[:_DATE_CHARS])
    except ValueError:
        return None
    return day if _MIN_DATE <= day <= _MAX_DATE else None


def _number(value: object, ceiling: float) -> float | None:
    """A finite number within `[-ceiling, ceiling]`, else None (a huge integer overflows to None too)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) and abs(number) <= ceiling else None


def _utc(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


_FOLDED_KEYWORDS = tuple((issue_class, _fold(keyword)) for issue_class, keyword in _KEYWORDS)


def _issue_class(title: str | None) -> IssueClass:
    """The class of an issue title; the title is not kept. NFD input is composed first, so it still matches."""
    if not title:
        return IssueClass.OTHER
    folded = _fold(title)
    return next((issue_class for issue_class, keyword in _FOLDED_KEYWORDS if keyword in folded), IssueClass.OTHER)


# --- announcements (`add-announcement-tags-and-insider-sizing`) -------------------------------------------
_ANNOUNCEMENT_DATES = ("start_date", "end_date", "exright_date", "issue_date", "listing_date", "record_date")


def read_announcements(ticker: str) -> AnnouncementRead:
    """The stored news and event announcements of `ticker` and the health of each kind; never raises."""
    items: list[Announcement] = []
    unreadable = 0
    health: dict[str, SourceHealth] = {}
    for kind in (KIND_NEWS, KIND_EVENTS):
        try:
            found, bad, health[kind] = _kind(ticker, kind)
        except Exception:  # noqa: BLE001 - a feed problem must never remove a holding's block
            logger.exception("reading the stored %s of %s failed", kind, ticker)
            found, bad, health[kind] = (), 0, SourceHealth(UNREADABLE)
        items += found
        unreadable += bad
    return AnnouncementRead(tuple(items), health[KIND_NEWS], health[KIND_EVENTS], unreadable)


def _kind(ticker: str, kind: str) -> tuple[tuple[Announcement, ...], int, SourceHealth]:
    latest = store.last_fetch(ticker, kind)
    if latest is None:
        return (), 0, SourceHealth(NEVER_FETCHED)
    record = latest.latest
    failed = record.status in _FAILED_STATUSES
    attempt = dict(latest_attempt_at=_utc(record.fetched_at), latest_attempt_failed=failed, error_class=_error_class(record.error_class) if failed else None)
    if latest.last_success_at is None:
        return (), 0, SourceHealth(NEVER_SUCCEEDED, **attempt)
    fetched = _utc(latest.last_success_at)
    if fetched is None:
        return (), 0, SourceHealth(UNREADABLE)
    items, bad = _announcements(store.latest_items(ticker, kind))
    newest = max((a.published_at for a in items), default=None)
    health = SourceHealth(
        FETCHED, last_success_at=fetched, items_returned=None if failed else record.items_returned, newest_published=newest, **attempt,
    )
    return items, bad, health


def _error_class(text: str | None) -> str:
    return text if isinstance(text, str) and _ERROR_CLASS.fullmatch(text) else "error"


def _announcements(rows: Iterable[store.StoredItem]) -> tuple[tuple[Announcement, ...], int]:
    found: list[Announcement] = []
    bad = 0
    for row in rows:
        try:
            item = _announcement(row)
        except Exception:  # noqa: BLE001 - one malformed row is counted, never allowed to hide the others
            logger.warning("a stored announcement row of %s could not be read", row.ticker, exc_info=True)
            item = None
        if item is None:
            bad += 1
        else:
            found.append(item)
    return tuple(found), bad


def _announcement(row: store.StoredItem) -> Announcement | None:
    """The announcement for a stored row, or None when it has no readable date or title."""
    published, title = _parse_date(row.published_at), row.title
    if published is None or not isinstance(title, str) or not title.strip():
        return None
    first_seen = _utc(row.first_seen_at)
    common = dict(
        kind=row.kind, published_at=published, first_seen=first_seen.astimezone(ICT).date() if first_seen else None,
        from_first_fetch=bool(row.from_first_fetch), title=title,
    )
    if row.kind == KIND_NEWS or not isinstance(row.fields, dict):
        return Announcement(**common)
    fields = row.fields
    code = fields.get("event_code")
    code = code.strip() if isinstance(code, str) and code.strip() else None
    action = fields.get("action_type_en")
    dates = {name: _parse_date(fields.get(name)) for name in _ANNOUNCEMENT_DATES}
    return Announcement(
        **common, event_code=code, action_type_en=action.strip() if isinstance(action, str) and action.strip() else None,
        exercise_ratio=_number(fields.get("exercise_ratio"), _MAX_RATIO),
        issue_class=_issue_class(title) if code == "ISS" else None, **dates,
    )
