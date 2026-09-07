import sqlite3
from datetime import date

import pandas as pd
import pytest

import app.services.ticker_universe as ticker_universe
from app.db.schema import (
    CREATE_OHLCV_QUALITY_FLAGS_TABLE,
    CREATE_TICKER_UNIVERSE_TABLE,
)
from app.services.ticker_universe import (
    INGESTION_STATE_OK,
    record_ingestion_result,
    universe_entry,
    DELISTED_EXCHANGE,
    HOSE_EXCHANGE,
    LISTING_STATUS_DELISTED,
    LISTING_STATUS_LISTED,
    UniverseConstructionError,
    build_universe_entries,
    construct_universe,
    stock_rows,
    universe_as_of,
)


def _listing_row(symbol, exchange, instrument_type="STOCK", icb_code2="8300"):
    return {
        "symbol": symbol,
        "exchange": exchange,
        "type": instrument_type,
        "icb_code2": icb_code2,
    }


def _listing(*rows):
    return pd.DataFrame(list(rows))


@pytest.fixture
def universe_db(monkeypatch, tmp_path):
    """A database with only the universe tables, wired into the service."""
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.commit()
    conn.close()
    monkeypatch.setattr(
        ticker_universe, "get_connection", lambda: sqlite3.connect(db_path)
    )
    return db_path


# --- instrument-type filtering (task 2.1) ---


def test_non_stock_instrument_types_are_excluded():
    """The listing shares one response across every instrument the exchanges
    trade; only ordinary stocks are tickers for this system."""
    listing = _listing(
        _listing_row("AAA", HOSE_EXCHANGE),
        _listing_row("CAAA", HOSE_EXCHANGE, "CW"),
        _listing_row("FUEVN", HOSE_EXCHANGE, "ETF"),
        _listing_row("BOND1", HOSE_EXCHANGE, "BOND"),
        _listing_row("VN30F", HOSE_EXCHANGE, "FU"),
        _listing_row("UT1", HOSE_EXCHANGE, "UNIT_TRUST"),
        _listing_row("DEB1", HOSE_EXCHANGE, "DEBENTURE"),
    )
    assert list(stock_rows(listing)["symbol"]) == ["AAA"]
    assert [e["symbol"] for e in build_universe_entries(listing)] == ["AAA"]


def test_unknown_future_instrument_type_is_excluded_not_admitted():
    """Filtering positively on STOCK means a type vnstock adds later defaults
    to excluded rather than silently becoming a ticker."""
    listing = _listing(
        _listing_row("AAA", HOSE_EXCHANGE),
        _listing_row("NEW1", HOSE_EXCHANGE, "SOME_NEW_TYPE"),
    )
    assert [e["symbol"] for e in build_universe_entries(listing)] == ["AAA"]


def test_listing_without_type_column_is_a_construction_failure():
    listing = pd.DataFrame([{"symbol": "AAA", "exchange": HOSE_EXCHANGE}])
    with pytest.raises(UniverseConstructionError, match="`type` column"):
        build_universe_entries(listing)


# --- exchange filtering and plausibility (task 2.2) ---


def test_only_hose_and_delisted_stocks_are_admitted():
    listing = _listing(
        _listing_row("AAA", HOSE_EXCHANGE),
        _listing_row("HNX1", "HNX"),
        _listing_row("UPC1", "UPCOM"),
        _listing_row("OLD1", DELISTED_EXCHANGE),
    )
    entries = {e["symbol"]: e for e in build_universe_entries(listing)}
    assert sorted(entries) == ["AAA", "OLD1"]
    assert entries["AAA"]["listing_status"] == LISTING_STATUS_LISTED
    assert entries["OLD1"]["listing_status"] == LISTING_STATUS_DELISTED


def test_zero_hose_stocks_is_a_construction_failure_not_an_empty_universe():
    """Persisting an empty universe would silently break every later step;
    the previous universe should stay in place instead."""
    listing = _listing(_listing_row("HNX1", "HNX"))
    with pytest.raises(UniverseConstructionError, match="zero HOSE stock rows"):
        build_universe_entries(listing)


def test_construction_failure_leaves_the_existing_universe_untouched(universe_db):
    construct_universe(_listing(_listing_row("AAA", HOSE_EXCHANGE)))
    with pytest.raises(UniverseConstructionError):
        construct_universe(_listing(_listing_row("HNX1", "HNX")))
    conn = sqlite3.connect(universe_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM ticker_universe").fetchone()[0] == 1
    finally:
        conn.close()


# --- delisted handling (task 2.3) ---


def test_delisted_entries_carry_no_asserted_exchange():
    """`DELISTED` is a status, not a venue — these rows have no exchange
    field, so inventing one would be an assertion the data cannot support
    (design Decision 2, open question 2)."""
    entries = {
        e["symbol"]: e
        for e in build_universe_entries(
            _listing(
                _listing_row("AAA", HOSE_EXCHANGE),
                _listing_row("VSP", DELISTED_EXCHANGE),
            )
        )
    }
    assert entries["VSP"]["exchange"] is None
    assert entries["VSP"]["listing_status"] == LISTING_STATUS_DELISTED
    assert entries["AAA"]["exchange"] == HOSE_EXCHANGE


def test_every_entry_marks_its_exchange_as_an_unverified_fallback():
    """The listing gives current state only and symbols migrate between
    exchanges, so no entry may claim verified dated membership."""
    entries = build_universe_entries(
        _listing(
            _listing_row("AAA", HOSE_EXCHANGE),
            _listing_row("VSP", DELISTED_EXCHANGE),
        )
    )
    assert all(e["exchange_is_unverified_fallback"] == 1 for e in entries)


# --- null icb_code2 (task 2.4) ---


@pytest.mark.parametrize("missing", [None, float("nan"), "", "   "])
def test_missing_icb_code2_stores_null_and_keeps_the_symbol(missing):
    listing = _listing(
        _listing_row("AAA", HOSE_EXCHANGE, icb_code2=missing),
        _listing_row("BBB", HOSE_EXCHANGE, icb_code2="8300"),
    )
    entries = {e["symbol"]: e for e in build_universe_entries(listing)}
    assert sorted(entries) == ["AAA", "BBB"]
    assert entries["AAA"]["icb_code2"] is None
    assert entries["BBB"]["icb_code2"] == "8300"


def test_listing_without_icb_code2_column_still_builds():
    listing = pd.DataFrame(
        [{"symbol": "AAA", "exchange": HOSE_EXCHANGE, "type": "STOCK"}]
    )
    assert build_universe_entries(listing)[0]["icb_code2"] is None


# --- persistence ---


def test_construct_universe_persists_and_summarises(universe_db):
    summary = construct_universe(
        _listing(
            _listing_row("AAA", HOSE_EXCHANGE),
            _listing_row("BBB", HOSE_EXCHANGE, icb_code2=None),
            _listing_row("VSP", DELISTED_EXCHANGE),
            _listing_row("CAAA", HOSE_EXCHANGE, "CW"),
        )
    )
    assert summary == {
        "total": 3,
        "listed": 2,
        "delisted": 1,
        "missing_icb_code2": 1,
    }
    conn = sqlite3.connect(universe_db)
    try:
        rows = dict(
            conn.execute("SELECT symbol, ingestion_state FROM ticker_universe")
        )
    finally:
        conn.close()
    assert rows == {"AAA": "pending", "BBB": "pending", "VSP": "pending"}


def test_reconstruction_refreshes_listing_columns_but_preserves_ingestion_state(
    universe_db,
):
    """Universe construction owns the listing-sourced columns; ingestion owns
    observed ranges, measurements, and state. A re-run must not wipe the
    second group — that would reset the batch runner's resume point."""
    construct_universe(_listing(_listing_row("AAA", HOSE_EXCHANGE, icb_code2="8300")))
    conn = sqlite3.connect(universe_db)
    try:
        conn.execute(
            """
            UPDATE ticker_universe
               SET first_observed_session = '2018-01-02',
                   last_observed_session = '2026-08-27',
                   observed_session_count = 2100,
                   stale_close_fraction = 0.04,
                   ingestion_state = 'ok'
             WHERE symbol = 'AAA'
            """
        )
        conn.commit()
    finally:
        conn.close()

    construct_universe(_listing(_listing_row("AAA", HOSE_EXCHANGE, icb_code2="8600")))

    conn = sqlite3.connect(universe_db)
    try:
        row = conn.execute(
            """
            SELECT icb_code2, first_observed_session, last_observed_session,
                   observed_session_count, stale_close_fraction, ingestion_state
              FROM ticker_universe WHERE symbol = 'AAA'
            """
        ).fetchone()
    finally:
        conn.close()
    assert row == ("8600", "2018-01-02", "2026-08-27", 2100, 0.04, "ok")


# --- point-in-time reconstruction (task 2.5) ---


@pytest.fixture
def universe_with_ranges(universe_db):
    construct_universe(
        _listing(
            _listing_row("OLDCO", HOSE_EXCHANGE),
            _listing_row("MIDCO", HOSE_EXCHANGE),
            _listing_row("NEWCO", HOSE_EXCHANGE),
            _listing_row("GONECO", DELISTED_EXCHANGE),
            _listing_row("NEVERLOADED", HOSE_EXCHANGE),
        )
    )
    conn = sqlite3.connect(universe_db)
    try:
        for symbol, first, last in (
            ("OLDCO", "2010-01-04", "2026-08-27"),
            ("MIDCO", "2020-06-01", "2026-08-27"),
            ("NEWCO", "2025-03-10", "2026-08-27"),
            # Trading at 2021-01-04, delisted well before today.
            ("GONECO", "2015-02-02", "2022-07-28"),
        ):
            conn.execute(
                """
                UPDATE ticker_universe
                   SET first_observed_session = ?, last_observed_session = ?
                 WHERE symbol = ?
                """,
                (first, last, symbol),
            )
        conn.commit()
    finally:
        conn.close()
    return universe_db


def test_point_in_time_excludes_symbols_not_yet_listed(universe_with_ranges):
    assert universe_as_of(date(2021, 1, 4)) == ["GONECO", "MIDCO", "OLDCO"]
    assert "NEWCO" not in universe_as_of(date(2021, 1, 4))


def test_point_in_time_includes_symbols_later_delisted(universe_with_ranges):
    """The whole point of ingesting delisted symbols: a backtest as of a past
    date must see the companies that existed then, not just the survivors."""
    assert "GONECO" in universe_as_of(date(2021, 1, 4))
    assert "GONECO" in universe_as_of("2026-08-27")


def test_point_in_time_includes_a_symbol_on_its_first_session(universe_with_ranges):
    assert "NEWCO" in universe_as_of(date(2025, 3, 10))
    assert "NEWCO" not in universe_as_of(date(2025, 3, 9))


def test_point_in_time_excludes_symbols_that_were_never_loaded(universe_with_ranges):
    """A symbol with no observed range cannot be placed in time; excluding it
    is honest, whereas assuming it existed would fabricate history."""
    assert "NEVERLOADED" not in universe_as_of("2026-08-27")


def test_point_in_time_accepts_a_date_or_an_iso_string(universe_with_ranges):
    assert universe_as_of(date(2021, 1, 4)) == universe_as_of("2021-01-04")


# --- modelling-universe filters (tasks 7.3, 7.4) ---


def _filtered_universe_rows(conn):
    """Four symbols: one clean, one illiquid, one too short, one never
    ingested."""
    rows = [
        ("CLEAN", "listed", "ok", 0, None, 2000, "2018-01-02", "2026-09-04"),
        ("ILLIQUID", "listed", "ok", 1, None, 2000, "2018-01-02", "2026-09-04"),
        ("SHORT", "listed", "ok", 0, None, 68, "2026-06-01", "2026-09-04"),
        ("NEVER", "listed", "pending", None, None, None, None, None),
        ("DEAD", "delisted", "ok", 0, None, 1600, "2016-01-07", "2022-07-28"),
    ]
    for row in rows:
        conn.execute(
            "INSERT INTO ticker_universe (symbol, listing_status, "
            "ingestion_state, fails_liquidity_filter, below_minimum_history, "
            "observed_session_count, first_observed_session, "
            "last_observed_session, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '2026-09-07T00:00:00')",
            row,
        )
    conn.commit()


def test_minimum_history_filter_flags_rather_than_deletes(universe_db):
    """Task 7.4: the exclusion must stay visible and reversible, and the
    measured count must survive so the threshold can be re-tuned."""
    conn = sqlite3.connect(universe_db)
    _filtered_universe_rows(conn)
    conn.close()

    summary = ticker_universe.apply_minimum_history_filter(250)

    assert summary["below_minimum"] == 1
    conn = sqlite3.connect(universe_db)
    try:
        rows = dict(
            conn.execute(
                "SELECT symbol, below_minimum_history FROM ticker_universe"
            ).fetchall()
        )
        counts = dict(
            conn.execute(
                "SELECT symbol, observed_session_count FROM ticker_universe"
            ).fetchall()
        )
    finally:
        conn.close()
    assert rows["SHORT"] == 1
    assert rows["CLEAN"] == 0
    # Never ingested is not "too short" — it has not been measured at all.
    assert rows["NEVER"] is None
    assert counts["SHORT"] == 68


def test_modelling_universe_excludes_filtered_symbols_but_keeps_their_data(
    universe_db,
):
    conn = sqlite3.connect(universe_db)
    _filtered_universe_rows(conn)
    conn.close()
    ticker_universe.apply_minimum_history_filter(250)

    assert ticker_universe.modelling_universe() == ["CLEAN", "DEAD"]

    # The rows themselves are untouched — filtering happens on read.
    conn = sqlite3.connect(universe_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM ticker_universe").fetchone()[0] == 5
    finally:
        conn.close()


def test_modelling_universe_keeps_delisted_symbols_by_default(universe_db):
    """Excluding them is precisely the survivorship bias this change exists
    to remove."""
    conn = sqlite3.connect(universe_db)
    _filtered_universe_rows(conn)
    conn.close()

    assert "DEAD" in ticker_universe.modelling_universe()
    assert "DEAD" not in ticker_universe.modelling_universe(include_delisted=False)


def test_modelling_universe_as_of_requires_the_symbol_to_have_been_trading(
    universe_db,
):
    """Stricter than `universe_as_of`, which implements the spec's "includes
    or precedes D" and so keeps a long-dead symbol in the set. For
    cross-sectional ranking on a shared as-of date, a company delisted in
    2022 cannot be ranked in 2026."""
    conn = sqlite3.connect(universe_db)
    _filtered_universe_rows(conn)
    conn.close()
    ticker_universe.apply_minimum_history_filter(250)

    # Both were trading in 2020; only one of them still is in 2026.
    assert ticker_universe.modelling_universe(as_of="2020-06-01") == ["CLEAN", "DEAD"]
    assert ticker_universe.modelling_universe(as_of="2026-09-01") == ["CLEAN"]
    # Before CLEAN listed, only the one that already existed.
    assert ticker_universe.modelling_universe(as_of="2017-01-01") == ["DEAD"]
    # The looser primitive still answers the question it was specified for.
    assert "DEAD" in universe_as_of("2026-09-01")


# --- what ingestion writes back (task 4.3) ---


def test_universe_entry_returns_the_row_as_a_dict(universe_db):
    construct_universe(_listing(_listing_row("AAA", HOSE_EXCHANGE)))
    entry = universe_entry("AAA")
    assert entry["symbol"] == "AAA"
    assert entry["exchange"] == HOSE_EXCHANGE
    assert entry["exchange_is_unverified_fallback"] == 1


def test_universe_entry_of_a_symbol_outside_the_universe_is_none(universe_db):
    assert universe_entry("NOPE") is None


def test_universe_entry_reads_through_a_supplied_connection(tmp_path):
    """Callers holding a connection must be able to pass it, or this would
    open a second one against the real DB_PATH."""
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    conn.execute(
        "INSERT INTO ticker_universe (symbol, listing_status, updated_at) "
        "VALUES ('BBB', 'listed', '2026-09-03T00:00:00')"
    )
    conn.commit()
    try:
        assert universe_entry("BBB", conn)["listing_status"] == "listed"
    finally:
        conn.close()


def test_record_ingestion_result_writes_the_observed_range(universe_db):
    construct_universe(_listing(_listing_row("AAA", HOSE_EXCHANGE)))

    assert record_ingestion_result(
        "AAA",
        first_observed_session="2018-01-02",
        last_observed_session="2026-08-27",
        observed_session_count=2100,
        ingestion_state=INGESTION_STATE_OK,
    )

    conn = sqlite3.connect(universe_db)
    try:
        row = conn.execute(
            "SELECT first_observed_session, last_observed_session, "
            "observed_session_count, ingestion_state, ingestion_last_error, "
            "ingestion_attempted_at FROM ticker_universe WHERE symbol = 'AAA'"
        ).fetchone()
    finally:
        conn.close()
    assert row[:5] == ("2018-01-02", "2026-08-27", 2100, "ok", None)
    assert row[5] is not None


def test_record_ingestion_result_reports_a_symbol_outside_the_universe(universe_db):
    """False rather than an insert: fabricating a row here would invent a
    listing status and exchange only the listing can supply. Nor an error —
    the load itself succeeded and its data is stored."""
    assert not record_ingestion_result(
        "NOPE",
        first_observed_session="2018-01-02",
        last_observed_session="2026-08-27",
        observed_session_count=2100,
        ingestion_state=INGESTION_STATE_OK,
    )

    conn = sqlite3.connect(universe_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM ticker_universe").fetchone() == (0,)
    finally:
        conn.close()
