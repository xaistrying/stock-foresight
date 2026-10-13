"""Tags, listing and the "needs a look" split for one ticker's announcements (`add-announcement-tags-and-insider-sizing`).

Pure functions over `Announcement` values. Event-record tags come from the event code only; keyword tags apply only
to news titles that start with the held ticker and a colon (a company filing), and only for the classes the caller
enables (none by default). Anything else is "Other announcement, not classified". No tag calls an announcement
routine, minor or administrative. Press items are never classified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from app.services.brief import announcement_keywords as kw
from app.services.brief import issue_size
from app.services.brief.feed_source import KIND_NEWS, Announcement
from app.services.brief.insider import window_is_open

FIRST_BRIEF_LOOKBACK_DAYS = 14  # non-price constant: the listing period with no previous brief
INFO_ITEMS_MAX = 10  # "For information" shows the newest this many
NEEDS_ITEMS_MAX = 10  # so does "Needs a look"; the rest is counted, and the triggers line counts every listed item


class Tag(Enum):
    TRADE = "trade"
    CAPITAL = "capital"
    DIVIDEND = "dividend"
    MEETING = "meeting"
    RESULTS = "results"
    PERSONNEL = "personnel"
    UNCLASSIFIED = "unclassified"
    PRESS = "press"


BASIS_RECORD, BASIS_KEYWORD = "event record", "title keyword"
EVENT_CODE_TAGS = {
    "DDIND": Tag.TRADE, "DDINS": Tag.TRADE, "DDRP": Tag.TRADE, "ISS": Tag.CAPITAL, "AIS": Tag.CAPITAL,
    "DIV": Tag.DIVIDEND, "AGME": Tag.MEETING, "EGME": Tag.MEETING,
}
_KEYWORD_TAGS = {
    kw.CAPITAL: Tag.CAPITAL, kw.DIVIDEND: Tag.DIVIDEND, kw.MEETING: Tag.MEETING, kw.RESULTS: Tag.RESULTS,
    kw.PERSONNEL: Tag.PERSONNEL,
}
ADDITIONAL_LISTING = "AIS"


@dataclass(frozen=True)
class Classified:
    item: Announcement
    tag: Tag
    basis: str | None  # BASIS_RECORD, BASIS_KEYWORD, or None when nothing tagged it


def is_company_filing(item: Announcement, ticker: str) -> bool:
    """A news title that starts with the held ticker and a colon; any other news title is a press item."""
    return item.title.strip().startswith(f"{ticker}:")


def classify(item: Announcement, ticker: str, enabled: frozenset[str] = kw.ENABLED_KEYWORD_CLASSES) -> Classified:
    """The tag and its basis: the event code for an event row; for a news title, a keyword class (only for a company filing,
    only a class in `enabled`); a press item and anything unmatched are never given a class."""
    if item.kind != KIND_NEWS:
        tag = EVENT_CODE_TAGS.get(item.event_code or "")
        return Classified(item, tag, BASIS_RECORD) if tag else Classified(item, Tag.UNCLASSIFIED, None)
    if not is_company_filing(item, ticker):
        return Classified(item, Tag.PRESS, None)
    matches = kw.matching_classes(item.title, enabled)
    if kw.CAPITAL in matches:  # over-flagging a capital change is the safer error
        return Classified(item, Tag.CAPITAL, BASIS_KEYWORD)
    if len(matches) == 1:
        return Classified(item, _KEYWORD_TAGS[matches[0]], BASIS_KEYWORD)
    return Classified(item, Tag.UNCLASSIFIED, None)


@dataclass(frozen=True)
class Listed:
    classified: Classified
    is_new: bool  # newer than the previous brief (or inside the first-brief lookback)
    relisted: bool  # not new, listed again because an insider trade's window has not ended


@dataclass(frozen=True)
class Listing:
    needs_look: tuple[Listed, ...]
    information: tuple[Listed, ...]  # every qualifying item, newest first; show `information_shown`
    small_issues: tuple[Announcement, ...]  # issues below the material ratio, counted not listed
    lookback: bool  # no previous brief: the first-brief lookback was used

    @property
    def needs_shown(self) -> tuple[Listed, ...]:
        return self.needs_look[:NEEDS_ITEMS_MAX]

    @property
    def needs_more(self) -> int:
        return max(len(self.needs_look) - NEEDS_ITEMS_MAX, 0)

    @property
    def information_shown(self) -> tuple[Listed, ...]:
        return self.information[:INFO_ITEMS_MAX]

    @property
    def information_more(self) -> int:
        return max(len(self.information) - INFO_ITEMS_MAX, 0)


def is_new(item: Announcement, last_bar: date, previous_last_bar: date | None) -> bool:
    """Dated after the previous brief's last bar, or first seen after it in a fetch that was not the first."""
    if previous_last_bar is None:
        return item.published_at >= last_bar - timedelta(days=FIRST_BRIEF_LOOKBACK_DAYS)
    late = item.first_seen is not None and item.first_seen > previous_last_bar and not item.from_first_fetch
    return item.published_at > previous_last_bar or late


def build_listing(
    items: tuple[Announcement, ...], ticker: str, last_bar: date, previous_last_bar: date | None,
    enabled: frozenset[str] = kw.ENABLED_KEYWORD_CLASSES,
) -> Listing:
    """What the COMPANY block lists for one ticker: the new items (and trades whose window is still open), split into "needs
    a look" and "for information", with small share issues set aside to be counted."""
    needs, info, small = [], [], []
    for item in items:
        classified = classify(item, ticker, enabled)
        new = is_new(item, last_bar, previous_last_bar)
        relisted = not new and classified.tag is Tag.TRADE and window_is_open(item, last_bar)
        if not (new or relisted):
            continue
        if _is_small_issue(classified):
            small.append(item)
            continue
        (needs if _needs_a_look(classified) else info).append(Listed(classified, new, relisted))
    newest = lambda listed: (listed.classified.item.published_at, listed.classified.item.title)  # noqa: E731
    return Listing(
        tuple(sorted(needs, key=newest, reverse=True)), tuple(sorted(info, key=newest, reverse=True)), tuple(small),
        lookback=previous_last_bar is None,
    )


def _is_issue_event(classified: Classified) -> bool:
    return classified.item.event_code == "ISS"


def _is_small_issue(classified: Classified) -> bool:
    return _is_issue_event(classified) and issue_size.is_small(classified.item)


def _needs_a_look(classified: Classified) -> bool:
    """Only an insider trade and a share issue or capital change; an additional listing has no ratio to test."""
    if classified.tag is Tag.TRADE:
        return True
    return classified.tag is Tag.CAPITAL and classified.item.event_code != ADDITIONAL_LISTING
