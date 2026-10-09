"""The company feed log: its own SQLite file, apart from `app.db` and `debate_log.db`.

`app.db` is rebuildable by reloading tickers and `debate_log.db` stores no
third-party headline text. This log is neither: the vendor returns at most 50 items
per call and the RSS feeds hold about four days, so an item not recorded now cannot
be fetched later. It therefore has its own file and its own init, run on the
writer's connection at first write. `init_db` and `schema.py` do not know it.

Both tables are append-only: the company feed inserts, never updates or deletes.
"""

import sqlite3
from pathlib import Path

COMPANY_FEED_LOG_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "company_feed_log.db"

# Two overlapping runs wait for each other's write instead of failing on a locked file.
BUSY_TIMEOUT_SECONDS = 30.0

# One row per fetch attempt, including empty and failed ones. `ticker` is '' for an RSS
# feed. `error_class` is an exception class name only, never its message.
CREATE_COMPANY_FEED_FETCH_TABLE = """
CREATE TABLE IF NOT EXISTS company_feed_fetch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    status TEXT NOT NULL,
    items_returned INTEGER,
    items_new INTEGER,
    error_class TEXT,
    vnstock_version TEXT
)
"""

# One row per distinct item version. The UNIQUE key doubles as the de-duplication rule
# (`INSERT OR IGNORE`) and as the index the read helpers filter on.
CREATE_COMPANY_FEED_ITEM_TABLE = """
CREATE TABLE IF NOT EXISTS company_feed_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetch_id INTEGER NOT NULL REFERENCES company_feed_fetch (id),
    ticker TEXT NOT NULL,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    item_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    published_at TEXT,
    title TEXT,
    fields TEXT NOT NULL,
    UNIQUE (ticker, source, kind, item_id, content_hash)
)
"""


def get_company_feed_log_connection() -> sqlite3.Connection:
    COMPANY_FEED_LOG_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(COMPANY_FEED_LOG_DB_PATH, timeout=BUSY_TIMEOUT_SECONDS)


def init_company_feed_log_db(conn: sqlite3.Connection) -> None:
    conn.execute(CREATE_COMPANY_FEED_FETCH_TABLE)
    conn.execute(CREATE_COMPANY_FEED_ITEM_TABLE)
    conn.commit()
