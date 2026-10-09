"""Write fetches and items to the company feed log, and read them back.

Free of `vnstock`, directly and transitively. Parameterised SQL only. The writers raise on any
problem: the caller (`snapshot.py`) decides a failed write must not stop the run and must not be
silent. Nothing here updates or deletes a row.

The read helpers open the file `mode=ro` and treat a missing file (or one with no tables yet) as
"never fetched", which is what lets a later coverage line tell "none found" (an `ok` or `empty`
fetch, no item) from "not fetched" and "fetch failed".
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Sequence

from app.db import company_feed_log
from app.db.connection import open_readonly
from app.services.company_feed.normalise import ItemRecord

STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_ERROR = "error"
STATUSES = (STATUS_OK, STATUS_EMPTY, STATUS_RATE_LIMITED, STATUS_ERROR)
SUCCESS_STATUSES = (STATUS_OK, STATUS_EMPTY)

_ITEM_KEY = "ticker = ? AND source = ? AND kind = ? AND item_id = ? AND content_hash = ?"


@dataclass(frozen=True)
class FetchRow:
    """What one fetch attempt reports. `error` is the exception itself so that only its class name
    can ever be stored: vnai's rate-limit message is long and promotional."""

    ticker: str  # '' for an RSS feed
    source: str  # 'vci', or the feed URL
    kind: str  # 'news', 'events' or 'rss'
    status: str
    items_returned: int | None = None
    error: BaseException | None = None
    vnstock_version: str | None = None  # None for RSS


@dataclass(frozen=True)
class PlannedFetch:
    """A fetch attempt and the item versions it produced, ready for `record_fetch`."""

    row: FetchRow
    records: tuple[ItemRecord, ...] = ()


@dataclass(frozen=True)
class StoredFetch:
    fetch_id: int
    items_new: int
    fetched_at: str


@dataclass(frozen=True)
class StoredItem:
    """The latest recorded version of one item.

    `first_seen_at` is when this log first saw the item, not when it was announced.
    `from_first_fetch` is true when the item arrived in the first successful fetch of its ticker,
    kind and source: it is history and must not be treated as known on its own date."""

    ticker: str
    source: str
    kind: str
    item_id: str
    content_hash: str
    published_at: str | None
    title: str | None
    fields: dict[str, Any]
    fetched_at: str
    first_seen_at: str
    from_first_fetch: bool


@dataclass(frozen=True)
class FetchRecord:
    id: int
    ticker: str
    source: str
    kind: str
    fetched_at: str
    status: str
    items_returned: int | None
    items_new: int | None
    error_class: str | None
    vnstock_version: str | None


@dataclass(frozen=True)
class LastFetch:
    """`latest` is the most recent attempt whatever its outcome; `last_success_at` is the time of the
    most recent `ok` or `empty` one (None if there has been none), so a caller can tell "none found"
    from "fetch failed"."""

    latest: FetchRecord
    last_success_at: str | None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("fetched_at must be timezone-aware")
    return moment.astimezone(timezone.utc).isoformat()


def open_log_for_write() -> sqlite3.Connection:
    """Connection to the log, created with both tables on first use (the module's own init)."""
    conn = company_feed_log.get_company_feed_log_connection()
    try:
        company_feed_log.init_company_feed_log_db(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def _is_new(conn: sqlite3.Connection, record: ItemRecord) -> bool:
    key = (record.ticker, record.source, record.kind, record.item_id, record.content_hash)
    return conn.execute(f"SELECT 1 FROM company_feed_item WHERE {_ITEM_KEY}", key).fetchone() is None


def record_fetch(
    fetch: FetchRow, records: Sequence[ItemRecord] = (), *, fetched_at: datetime | None = None
) -> StoredFetch:
    """Store one fetch attempt and its new item versions in a single transaction.

    The write lock is taken up front, so `items_new` is exact and two overlapping runs writing the
    same items wait for each other (busy timeout) and leave no duplicate. A failure rolls the whole
    fetch back and raises.
    """
    if fetch.status not in STATUSES:
        raise ValueError(f"unknown fetch status {fetch.status!r}; expected one of {STATUSES}")
    stamp = _utc_iso(fetched_at or utc_now())
    error_class = type(fetch.error).__name__ if fetch.error is not None else None

    conn = open_log_for_write()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            new_records = [record for record in records if _is_new(conn, record)]
            cursor = conn.execute(
                "INSERT INTO company_feed_fetch "
                "(ticker, source, kind, fetched_at, status, items_returned, items_new, error_class, vnstock_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (fetch.ticker, fetch.source, fetch.kind, stamp, fetch.status, fetch.items_returned,
                 len(new_records), error_class, fetch.vnstock_version),
            )
            fetch_id = cursor.lastrowid
            for record in new_records:
                conn.execute(
                    "INSERT OR IGNORE INTO company_feed_item "
                    "(fetch_id, ticker, source, kind, item_id, content_hash, fetched_at, published_at, title, fields) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (fetch_id, record.ticker, record.source, record.kind, record.item_id,
                     record.content_hash, stamp, record.published_at, record.title, record.fields_json),
                )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()
    return StoredFetch(fetch_id=fetch_id, items_new=len(new_records), fetched_at=stamp)


# --- reading -----------------------------------------------------------------------------------


def open_log_readonly() -> sqlite3.Connection:
    """The log opened `mode=ro`: a write through it fails."""
    return open_readonly(company_feed_log.COMPANY_FEED_LOG_DB_PATH)


def _read(query: str, params: dict[str, Any]) -> list[tuple]:
    """Rows for a read-only query; a missing file, or a file with no tables yet, reads as none."""
    if not company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists():
        return []
    conn = open_log_readonly()
    try:
        return conn.execute(query, params).fetchall()
    except sqlite3.OperationalError as error:
        if "no such table" in str(error):
            return []
        raise
    finally:
        conn.close()


def new_records(records: Sequence[ItemRecord]) -> list[ItemRecord]:
    """The records the log does not hold yet, read-only (what a dry run would store). A missing log, or
    one with no tables yet, holds nothing."""
    if not company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists():
        return list(records)
    conn = open_log_readonly()
    try:
        return [record for record in records if _is_new(conn, record)]
    except sqlite3.OperationalError as error:
        if "no such table" in str(error):
            return list(records)
        raise
    finally:
        conn.close()


_LATEST_ITEMS = """
WITH first_success AS (
    SELECT source, MIN(id) AS fetch_id
    FROM company_feed_fetch
    WHERE ticker = :ticker AND kind = :kind AND status IN ('ok', 'empty')
    GROUP BY source
)
SELECT i.ticker, i.source, i.kind, i.item_id, i.content_hash, i.published_at, i.title, i.fields, i.fetched_at,
       (SELECT MIN(v.fetched_at) FROM company_feed_item v
         WHERE v.ticker = i.ticker AND v.source = i.source AND v.kind = i.kind AND v.item_id = i.item_id),
       EXISTS (SELECT 1 FROM company_feed_item v JOIN first_success f
                 ON f.source = v.source AND f.fetch_id = v.fetch_id
                WHERE v.ticker = i.ticker AND v.source = i.source AND v.kind = i.kind AND v.item_id = i.item_id)
FROM company_feed_item i
WHERE i.ticker = :ticker AND i.kind = :kind
  AND i.id = (SELECT MAX(v.id) FROM company_feed_item v
               WHERE v.ticker = i.ticker AND v.source = i.source AND v.kind = i.kind AND v.item_id = i.item_id)
  AND (:since IS NULL OR i.published_at >= :since)
ORDER BY i.published_at DESC, i.id DESC
"""


def _since_text(since: str | date | datetime | None) -> str | None:
    return since.isoformat() if isinstance(since, (date, datetime)) else since


def latest_items(ticker: str, kind: str, since: str | date | datetime | None = None) -> list[StoredItem]:
    """One row per `item_id`, its latest recorded version, newest published first. `since` keeps items
    published on or after it (compared as ISO text). A missing log reads as an empty list."""
    rows = _read(_LATEST_ITEMS, {"ticker": ticker, "kind": kind, "since": _since_text(since)})
    return [
        StoredItem(
            ticker=r[0], source=r[1], kind=r[2], item_id=r[3], content_hash=r[4], published_at=r[5],
            title=r[6], fields=json.loads(r[7]), fetched_at=r[8], first_seen_at=r[9], from_first_fetch=bool(r[10]),
        )
        for r in rows
    ]


_FETCH_COLUMNS = (
    "id, ticker, source, kind, fetched_at, status, items_returned, items_new, error_class, vnstock_version"
)


def last_fetch(ticker: str, kind: str, source: str | None = None) -> LastFetch | None:
    """The latest fetch row for a ticker and kind (an RSS feed is told apart by `source`), and the time
    of the latest `ok` or `empty` one. None when never fetched or the log does not exist."""
    params = {"ticker": ticker, "kind": kind, "source": source}
    where = "ticker = :ticker AND kind = :kind AND (:source IS NULL OR source = :source)"
    latest = _read(f"SELECT {_FETCH_COLUMNS} FROM company_feed_fetch WHERE {where} ORDER BY id DESC LIMIT 1", params)
    if not latest:
        return None
    success = _read(
        f"SELECT fetched_at FROM company_feed_fetch WHERE {where} AND status IN ('ok', 'empty') ORDER BY id DESC LIMIT 1",
        params,
    )
    return LastFetch(latest=FetchRecord(*latest[0]), last_success_at=success[0][0] if success else None)
