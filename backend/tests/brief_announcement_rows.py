"""Synthetic announcement rows for `add-announcement-tags-and-insider-sizing`, shaped like the stored ones.

Fictional tickers and counterparties, the stored title patterns (`<name> - Đăng kí Bán|Mua [qty] <TICKER>`,
`<TICKER>: <text>`) and the stored field names. Titles are short synthetic or keyword-only phrases; no real
announcement title, holding or counterparty is here. Nothing here calls the vendor or the real log.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np

from app.services.brief.feed_source import Announcement, IssueClass
from app.services.company_feed import store
from app.services.company_feed.normalise import frame_to_records
from app.services.company_feed.store import FetchRow

from .company_feed_helpers import events_frame, events_row, news_frame, news_row

FETCHED_AT = datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc)
_NAN = np.nan


def insider_row(
    ticker: str, n: int, *, name: str = "Fictional Capital Ltd", act: str = "Sell", qty: str | None = "1,000,000",
    published: str = "2026-10-08", start: str | None = "2026-10-12", end: str | None = "2026-11-10", code: str = "DDIND",
    title: str | None = None,
) -> dict:
    """A registered trade of a major shareholder or insider; `n` keeps same-day filers distinct."""
    word = "Bán" if act == "Sell" else "Mua"
    amount = f" {qty}" if qty else ""
    return events_row(
        ticker=ticker, event_code=code, event_title_vi=title or f"{name} {n} - Đăng kí {word}{amount} {ticker}",
        public_date=published, display_date2=published, start_date=start or _NAN, end_date=end or _NAN,
        action_type_en=act, exright_date=_NAN, record_date=_NAN, payout_date=_NAN, value_per_share=_NAN,
        exercise_ratio=_NAN, category="INSIDER",
    )


def event_row(ticker: str, code: str, title: str, *, published: str = "2026-10-08", **fields) -> dict:
    base = dict(
        ticker=ticker, event_code=code, event_title_vi=title, public_date=published, exright_date=_NAN, record_date=_NAN,
        payout_date=_NAN, value_per_share=_NAN, exercise_ratio=_NAN, issue_date=_NAN, listing_date=_NAN,
    )
    return events_row(**{**base, **fields})


def news_item(ticker: str, text: str, *, n: int = 0, published: str = "2026-10-08T09:00:00") -> dict:
    """A company filing (`<TICKER>: <text>`)."""
    return news_row(news_id=2000 + n, news_title=f"{ticker}: {text}", public_date=published, ticker=ticker)


def press_item(text: str, *, n: int = 0, published: str = "2026-10-08T09:00:00") -> dict:
    return news_row(news_id=3000 + n, news_title=text, public_date=published, ticker=None)


def store_rows(ticker: str, kind: str, rows: list[dict], *, fetched_at: datetime = FETCHED_AT) -> None:
    frame = events_frame(*rows) if kind == "events" else news_frame(*rows)
    records = frame_to_records(frame, kind=kind, ticker=ticker, source="vci").records
    store.record_fetch(
        FetchRow(ticker=ticker, source="vci", kind=kind, status="ok", items_returned=len(rows)), records, fetched_at=fetched_at,
    )


def store_status(ticker: str, kind: str, status: str, *, fetched_at: datetime = FETCHED_AT, error: BaseException | None = None) -> None:
    store.record_fetch(
        FetchRow(ticker=ticker, source="vci", kind=kind, status=status, items_returned=0, error=error), (), fetched_at=fetched_at,
    )


# --- typed announcements, for the pure modules (no log involved) ------------------------------------------
def d(text: str) -> date:
    return date.fromisoformat(text)


def make_announcement(kind: str = "events", title: str = "placeholder", *, published: str = "2026-10-08", **fields) -> Announcement:
    """An `Announcement`; `first_seen` defaults to the publication date and the item is not from the first fetch."""
    base = dict(kind=kind, published_at=d(published), first_seen=d(published), from_first_fetch=False, title=title)
    parsed = {k: (d(v) if isinstance(v, str) and k.endswith("_date") else v) for k, v in fields.items()}
    return Announcement(**{**base, **parsed})


def make_trade_item(
    ticker: str = "AAA", *, name: str = "Fictional Capital Ltd", act: str = "Sell", qty: str | None = "1,000,000",
    published: str = "2026-10-08", start: str | None = "2026-10-12", end: str | None = "2026-11-10", code: str = "DDIND",
    title: str | None = None, action: str | None = "same",
) -> Announcement:
    word = "Bán" if act == "Sell" else "Mua"
    text = title or f"{name} - Đăng kí {word}{' ' + qty if qty else ''} {ticker}"
    return make_announcement(
        "events", text, published=published, event_code=code, start_date=start, end_date=end,
        action_type_en=act if action == "same" else action,
    )


def make_issue_item(
    issue_class: IssueClass, ratio: float | None, *, published: str = "2026-10-08", ex: str | None = None,
    record: str | None = None, code: str = "ISS", title: str = "placeholder issue",
) -> Announcement:
    return make_announcement(
        "events", title, published=published, event_code=code, exright_date=ex, record_date=record, exercise_ratio=ratio,
        issue_class=issue_class if code == "ISS" else None,
    )


# --- the COMPANY block's inputs, without a feed log ----------------------------------------------------------------
def health(kind_status: str = "fetched", *, answered: str = "2026-10-10", n: int | None = 3, newest: str | None = "2026-10-08",
           failed: bool = False, error: str | None = None, attempt: str = "2026-10-11T08:00:00") -> "SourceHealth":
    from app.services.brief.feed_source import SourceHealth

    if kind_status != "fetched":
        return SourceHealth(kind_status)
    moment = datetime.fromisoformat(answered + "T12:11:00").replace(tzinfo=timezone.utc)
    return SourceHealth(
        "fetched", last_success_at=moment, latest_attempt_at=datetime.fromisoformat(attempt).replace(tzinfo=timezone.utc),
        latest_attempt_failed=failed, error_class=error, items_returned=None if failed else n,
        newest_published=d(newest) if newest else None,
    )


def make_company(
    items=(), *, news=None, events=None, previous: str | None = "2026-10-02", run: str = "2026-10-12", sizing=None, enabled=frozenset(),
    unreadable: int = 0,
):
    """`CompanyFacts` over typed announcements; both kinds are fetched unless a health is passed."""
    from app.services.brief.company_facts import CompanyFacts
    from app.services.brief.feed_source import AnnouncementRead
    from app.services.brief.sizing import MODE_OFF, SizingInput

    read = AnnouncementRead(tuple(items), news or health(), events or health(), unreadable)
    return CompanyFacts(read, d(run), d(previous) if previous else None, sizing or SizingInput(MODE_OFF), frozenset(enabled))
