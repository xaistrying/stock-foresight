"""The company feed log's file and schema (`company-feed`, "own file").

Every test runs against a temporary file: `conftest._temporary_company_feed_log`
redirects `COMPANY_FEED_LOG_DB_PATH` for the whole session.
"""

import importlib.util
import sqlite3
from pathlib import Path

from app.db import company_feed_log, connection, debate_log

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REAL_LOG_PATH = BACKEND_ROOT / "data" / "company_feed_log.db"
LOG_TABLES = {"company_feed_item", "company_feed_fetch"}


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()


def _pristine(module) -> object:
    """The module as shipped, before any fixture patched its path constant."""
    spec = importlib.util.spec_from_file_location(f"_pristine_{module.__name__}", module.__file__)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    return fresh


def _insert_fetch_row(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO company_feed_fetch (ticker, source, kind, fetched_at, status) "
        "VALUES ('SAB', 'vci', 'news', '2026-10-09T00:00:00+00:00', 'ok')"
    )
    conn.commit()


def test_first_write_creates_the_file_with_both_tables():
    """Scenario: First write creates the file."""
    path = company_feed_log.COMPANY_FEED_LOG_DB_PATH
    assert not path.exists()

    conn = company_feed_log.get_company_feed_log_connection()
    try:
        company_feed_log.init_company_feed_log_db(conn)
    finally:
        conn.close()

    assert _tables(path) == LOG_TABLES | {"sqlite_sequence"}


def test_item_table_carries_the_documented_columns_and_unique_key():
    conn = company_feed_log.get_company_feed_log_connection()
    try:
        company_feed_log.init_company_feed_log_db(conn)
        item_columns = [row[1] for row in conn.execute("PRAGMA table_info(company_feed_item)")]
        fetch_columns = [row[1] for row in conn.execute("PRAGMA table_info(company_feed_fetch)")]
        unique_indexes = [
            [info[2] for info in conn.execute(f"PRAGMA index_info({index[1]})")]
            for index in conn.execute("PRAGMA index_list(company_feed_item)")
            if index[2]
        ]
    finally:
        conn.close()

    assert item_columns == [
        "id", "fetch_id", "ticker", "source", "kind", "item_id", "content_hash",
        "fetched_at", "published_at", "title", "fields",
    ]
    assert fetch_columns == [
        "id", "ticker", "source", "kind", "fetched_at", "status", "items_returned",
        "items_new", "error_class", "vnstock_version",
    ]
    assert ["ticker", "source", "kind", "item_id", "content_hash"] in unique_indexes


def test_reinitialising_a_populated_log_keeps_its_rows():
    """Scenario: Re-initialising a populated log."""
    conn = company_feed_log.get_company_feed_log_connection()
    try:
        company_feed_log.init_company_feed_log_db(conn)
        _insert_fetch_row(conn)
        company_feed_log.init_company_feed_log_db(conn)
        company_feed_log.init_company_feed_log_db(conn)
        rows = conn.execute("SELECT ticker, status FROM company_feed_fetch").fetchall()
    finally:
        conn.close()

    assert rows == [("SAB", "ok")]


def test_app_db_init_does_not_create_the_log_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "DB_PATH", tmp_path / "app.db")

    connection.init_db()

    tables = _tables(tmp_path / "app.db")
    assert tables and not tables & LOG_TABLES
    assert not company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists()


def test_rebuilding_app_db_leaves_the_log_untouched(tmp_path, monkeypatch):
    """Scenario: Rebuilding app.db."""
    conn = company_feed_log.get_company_feed_log_connection()
    try:
        company_feed_log.init_company_feed_log_db(conn)
        _insert_fetch_row(conn)
    finally:
        conn.close()
    before = company_feed_log.COMPANY_FEED_LOG_DB_PATH.read_bytes()

    app_db = tmp_path / "app.db"
    monkeypatch.setattr(connection, "DB_PATH", app_db)
    connection.init_db()
    app_db.unlink()
    connection.init_db()

    assert company_feed_log.COMPANY_FEED_LOG_DB_PATH.read_bytes() == before


def test_log_path_differs_from_the_other_two_databases():
    shipped_log = _pristine(company_feed_log).COMPANY_FEED_LOG_DB_PATH
    shipped_debate_log = _pristine(debate_log).DEBATE_LOG_DB_PATH

    assert shipped_log == REAL_LOG_PATH
    assert len({shipped_log, shipped_debate_log, connection.DB_PATH}) == 3


def test_tests_run_against_a_temporary_file_not_the_real_log():
    """Scenario: Tests do not write to the real log. The real file's state is the same before and after a write."""
    def state():
        return (REAL_LOG_PATH.stat().st_mtime_ns, REAL_LOG_PATH.stat().st_size) if REAL_LOG_PATH.exists() else None

    before = state()
    assert company_feed_log.COMPANY_FEED_LOG_DB_PATH != REAL_LOG_PATH

    conn = company_feed_log.get_company_feed_log_connection()
    try:
        company_feed_log.init_company_feed_log_db(conn)
        _insert_fetch_row(conn)
    finally:
        conn.close()

    assert state() == before
    assert company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists()
