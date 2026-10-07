"""Tests for assess_eligibility (openspec change `debate-data-guards`, data-eligibility).

Every test runs on a temp SQLite file with the real schema and an injected clock.
Calendar used: Friday 2026-10-09 is the newest session of a "current" ticker, and
the clock reads Monday 2026-10-12 10:00 in Vietnam, so a current ticker has age 0.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.db.schema import (
    CREATE_FEATURES_TABLE,
    CREATE_OHLCV_QUALITY_FLAGS_TABLE,
    CREATE_OHLCV_TABLE,
    CREATE_TICKER_UNIVERSE_TABLE,
    CREATE_TICKERS_TABLE,
)

END = "2026-10-09"  # Friday
MONDAY_MORNING = datetime.fromisoformat("2026-10-12T10:00:00+07:00")
INDICATORS = ("rsi", "macd_histogram", "tenkan_sen", "kijun_sen")
ALL_PRESENT = {"rsi": 55.0, "macd_histogram": 0.1, "tenkan_sen": 20.0, "kijun_sen": 19.0, "senkou_span_b": 18.0}


def weekdays(end: str, count: int, skip: frozenset[str] = frozenset()) -> list[str]:
    """`count` weekday dates ending on `end` (inclusive), oldest first, never `skip`."""
    found, day = [], date.fromisoformat(end)
    while len(found) < count:
        if day.weekday() < 5 and day.isoformat() not in skip:
            found.append(day.isoformat())
        day -= timedelta(days=1)
    return found[::-1]


@pytest.fixture
def db(tmp_path, monkeypatch):
    from app.services import data_eligibility

    path = tmp_path / "app.db"
    conn = sqlite3.connect(path)
    for ddl in (
        CREATE_OHLCV_TABLE, CREATE_TICKERS_TABLE, CREATE_FEATURES_TABLE,
        CREATE_TICKER_UNIVERSE_TABLE, CREATE_OHLCV_QUALITY_FLAGS_TABLE,
    ):
        conn.execute(ddl)
    conn.commit()
    monkeypatch.setattr(data_eligibility, "get_connection", lambda: sqlite3.connect(path))
    yield conn
    conn.close()


def seed(conn, ticker, dates, *, zero=(), status="listed", features=True, indicators=None, flags=()):
    """Insert a ticker. `flags` is a list of (date, tier, reason)."""
    conn.executemany(
        "INSERT INTO ohlcv VALUES (?, ?, 10, 10, 10, ?, 1000)",
        [(ticker, d, 0.0 if d in zero else 10.0) for d in dates],
    )
    if features:
        values = {**ALL_PRESENT, **(indicators or {})}
        conn.execute(
            "INSERT INTO features (ticker, date, rsi, macd_histogram, tenkan_sen, kijun_sen,"
            " senkou_span_b, near_gap, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, '2026-10-09')",
            (ticker, max(dates), values["rsi"], values["macd_histogram"],
             values["tenkan_sen"], values["kijun_sen"], values["senkou_span_b"]),
        )
    if status:
        conn.execute(
            "INSERT INTO ticker_universe (symbol, listing_status, updated_at) VALUES (?, ?, '2026-10-09')",
            (ticker, status),
        )
    conn.executemany(
        "INSERT INTO ohlcv_quality_flags VALUES (?, ?, ?, ?, 0.5, 'HOSE', 0, '2026-10-09')",
        [(ticker, d, tier, reason) for d, tier, reason in flags],
    )
    conn.commit()


def assess(ticker="AAA", now=MONDAY_MORNING):
    from app.services.data_eligibility import assess_eligibility

    return assess_eligibility(ticker, now=now)


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------

def test_healthy_current_ticker_is_eligible(db):
    seed(db, "AAA", weekdays(END, 80))

    result = assess()

    assert result == {"eligible": True, "reasons": [], "as_of": END, "age_sessions": 0}


def test_several_reasons_are_listed_in_the_fixed_order(db):
    old = weekdays("2026-09-08", 80)
    seed(db, "AAA", old, status="delisted")
    seed(db, "MKT", weekdays(END, 120), features=False)  # the rest of the market kept trading

    result = assess()

    assert result["reasons"] == ["delisted", "stale"]
    assert result["eligible"] is False
    assert result["as_of"] == "2026-09-08"
    assert result["age_sessions"] >= 21


def test_no_features_row_reports_insufficient_history_with_null_dates(db):
    seed(db, "AAA", weekdays(END, 80), features=False)

    assert assess() == {
        "eligible": False, "reasons": ["insufficient_history"], "as_of": None, "age_sessions": None,
    }


def test_unknown_ticker_has_no_features_row_either(db):
    assert assess("NOPE")["reasons"] == ["insufficient_history"]


def test_a_naive_clock_is_rejected(db):
    seed(db, "AAA", weekdays(END, 80))

    with pytest.raises(ValueError, match="timezone-aware"):
        assess(now=datetime(2026, 10, 12, 10, 0))


def test_the_service_does_not_import_the_prediction_api():
    code = "import app.services.data_eligibility, sys; sys.exit('app.api.predictions' in sys.modules)"

    backend = Path(__file__).resolve().parent.parent

    assert subprocess.run([sys.executable, "-c", code], cwd=backend).returncode == 0


# ---------------------------------------------------------------------------
# delisted / insufficient_history
# ---------------------------------------------------------------------------

def test_delisted_listing_status_is_reported(db):
    seed(db, "AAA", weekdays(END, 80), status="delisted")

    assert assess()["reasons"] == ["delisted"]


def test_a_ticker_missing_from_the_universe_is_not_called_delisted(db):
    seed(db, "AAA", weekdays(END, 80), status=None)

    assert assess()["reasons"] == []


@pytest.mark.parametrize("sessions, expected", [(64, ["insufficient_history"]), (65, [])])
def test_history_threshold_is_65_priced_sessions(db, sessions, expected):
    seed(db, "AAA", weekdays(END, sessions))

    assert assess()["reasons"] == expected


def test_zero_closes_are_not_priced_sessions(db):
    dates = weekdays(END, 70)
    seed(db, "AAA", dates, zero=set(dates[:10]))  # 70 rows, 60 priced

    assert "insufficient_history" in assess()["reasons"]


# ---------------------------------------------------------------------------
# age in sessions
# ---------------------------------------------------------------------------

def test_up_to_date_after_a_weekend_is_age_zero(db):
    seed(db, "AAA", weekdays(END, 80))

    result = assess(now=datetime.fromisoformat("2026-10-12T10:00:00+07:00"))  # Monday

    assert result["age_sessions"] == 0 and "stale" not in result["reasons"]


def test_behind_by_stored_sessions_counts_each_stored_date(db):
    seed(db, "AAA", weekdays("2026-09-07", 80))
    seed(db, "MKT", weekdays("2026-10-09", 120), features=False)
    stored_after = sum(1 for d in weekdays("2026-10-09", 120) if d > "2026-09-07")

    result = assess()

    assert result["age_sessions"] == stored_after
    assert "stale" in result["reasons"]


def test_a_holiday_inside_the_stored_range_is_not_counted(db):
    # Monday-Tuesday closure: nobody has a row on 10-05 or 10-06.
    seed(db, "AAA", weekdays("2026-10-02", 80))
    seed(db, "MKT", [*weekdays("2026-10-02", 80), "2026-10-07"], features=False)

    result = assess(now=datetime.fromisoformat("2026-10-07T19:00:00+07:00"))  # Wednesday evening

    assert result["age_sessions"] == 1  # the Wednesday, not 3 weekdays


def test_a_stale_database_is_not_read_as_fresh(db):
    seed(db, "AAA", weekdays("2026-09-18", 80))  # nothing refreshed since

    result = assess()  # Monday 2026-10-12

    assert result["age_sessions"] == 15  # 15 weekdays 09-21..10-09, none stored
    assert "stale" in result["reasons"]


@pytest.mark.parametrize(
    "clock, age, stale",
    [
        ("2026-10-08T10:00:00+07:00", 3, False),  # Thu: Mon, Tue, Wed after the Friday as_of
        ("2026-10-09T10:00:00+07:00", 4, True),   # Fri: Mon..Thu
    ],
)
def test_age_boundary_is_three_sessions(db, clock, age, stale):
    seed(db, "AAA", weekdays("2026-10-02", 80))

    result = assess(now=datetime.fromisoformat(clock))

    assert result["age_sessions"] == age
    assert ("stale" in result["reasons"]) is stale


@pytest.mark.parametrize(
    "clock, age",
    [
        ("2026-10-09T10:00:00+07:00", 4),  # 5th weekday of a Mon-Fri closure: stale (documented limitation)
        ("2026-10-12T10:00:00+07:00", 5),  # reopening Monday, nothing stored yet: still stale
    ],
)
def test_long_closure_with_nothing_stored_beyond_it_reads_stale(db, clock, age):
    seed(db, "AAA", weekdays("2026-10-02", 80))  # closed 10-05..10-09, no later session stored

    result = assess(now=datetime.fromisoformat(clock))

    assert result["age_sessions"] == age and "stale" in result["reasons"]


def test_a_three_weekday_closure_does_not_read_stale(db):
    seed(db, "AAA", weekdays("2026-08-28", 80))  # closed Mon-Wed 08-31..09-02

    result = assess(now=datetime.fromisoformat("2026-09-03T10:00:00+07:00"))  # Thursday morning

    assert result["age_sessions"] == 3 and "stale" not in result["reasons"]


# ---------------------------------------------------------------------------
# near_gap: missing market sessions, never the stored flag
# ---------------------------------------------------------------------------

def test_a_holiday_gap_is_not_a_gap(db):
    holiday = frozenset({"2026-08-31", "2026-09-01", "2026-09-02"})  # 6-calendar-day closure
    dates = weekdays(END, 80, skip=holiday)
    seed(db, "AAA", dates)
    seed(db, "MKT", dates, features=False)

    assert "near_gap" not in assess()["reasons"]


@pytest.mark.parametrize("omitted, flagged", [(2, False), (3, True), (6, True)])
def test_missing_market_sessions_over_two_are_a_gap(db, omitted, flagged):
    market = weekdays(END, 90)
    own = [d for d in market if d not in set(market[-30:-30 + omitted])]  # interior, inside the last 65
    seed(db, "AAA", own)
    seed(db, "MKT", market, features=False)

    assert ("near_gap" in assess()["reasons"]) is flagged


@pytest.mark.parametrize(
    "omitted_slice, flagged",
    [
        # Three market sessions the ticker lacks, relative to its last 65 priced ones.
        # The 65-session span stretches over omitted sessions, so these sit between the
        # 64th and 65th latest priced sessions: inside the span (a 64-session window
        # would miss them) ...
        (slice(-67, -64), True),
        # ... and these sit beyond the 65th priced session: outside it (a 78-session
        # window, the hard-flag one, would wrongly count them).
        (slice(-70, -67), False),
    ],
)
def test_near_gap_looks_back_exactly_65_priced_sessions(db, omitted_slice, flagged):
    market = weekdays(END, 100)
    omitted = set(market[omitted_slice])
    assert len(omitted) == 3
    seed(db, "AAA", [d for d in market if d not in omitted])
    seed(db, "MKT", market, features=False)

    assert ("near_gap" in assess()["reasons"]) is flagged


def test_the_stored_near_gap_column_is_not_consulted(db):
    dates = weekdays(END, 80)
    seed(db, "AAA", dates)
    db.execute("UPDATE features SET near_gap = 1")
    db.commit()

    assert "near_gap" not in assess()["reasons"]


# ---------------------------------------------------------------------------
# hard quality flags: the last 78 priced sessions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reason", ["price_limit", "invalid_close"])
def test_hard_flag_on_the_78th_latest_session_is_inside_the_window(db, reason):
    dates = weekdays(END, 100)
    seed(db, "AAA", dates, flags=[(dates[-78], "hard", reason)])

    assert assess()["reasons"] == ["hard_quality_flag"]


def test_hard_flag_older_than_78_sessions_is_outside_the_window(db):
    dates = weekdays(END, 100)
    seed(db, "AAA", dates, flags=[(dates[-79], "hard", "price_limit")])

    assert assess()["reasons"] == []


def test_soft_flags_do_not_count(db):
    dates = weekdays(END, 100)
    seed(db, "AAA", dates, flags=[(dates[-5], "soft", "price_limit")])

    assert assess()["reasons"] == []


# ---------------------------------------------------------------------------
# indicators: the four the Technical agent reads
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("column", INDICATORS)
def test_any_missing_agent_indicator_is_reported(db, column):
    seed(db, "AAA", weekdays(END, 80), indicators={column: None})

    assert assess()["reasons"] == ["indicators_missing"]


def test_an_indicator_the_agent_does_not_read_is_ignored(db):
    seed(db, "AAA", weekdays(END, 80), indicators={"senkou_span_b": None})

    assert assess()["reasons"] == []


# ---------------------------------------------------------------------------
# assess_eligibility_many: one pass for a whole catalog
# (openspec change `dashboard-rail-stage-verdict`, ticker-catalog)
# ---------------------------------------------------------------------------

def _seed_catalog(db):
    """One market of ~100 sessions plus a ticker per reason, each at a boundary.

    Returns the symbols whose reasons are asserted by hand, so the equivalence
    test cannot pass by both implementations being wrong the same way.
    """
    market = weekdays(END, 100)
    seed(db, "OK", market)
    seed(db, "DELIST", market, status="delisted")
    seed(db, "H64", weekdays(END, 64))
    seed(db, "H65", weekdays(END, 65))
    seed(db, "AGE3", weekdays("2026-10-06", 80))  # Mon, Tue... 3 stored sessions after: not stale
    seed(db, "AGE4", weekdays("2026-10-05", 80))  # 4 stored sessions after: stale
    for name, omitted in (("GAP2", 2), ("GAP3", 3)):
        gone = set(market[-30:-30 + omitted])
        seed(db, name, [d for d in market if d not in gone])
    seed(db, "FLAGIN", market, flags=[(market[-78], "hard", "price_limit")])
    seed(db, "FLAGOUT", market, flags=[(market[-79], "hard", "price_limit")])
    seed(db, "SOFT", market, flags=[(market[-5], "soft", "price_limit")])
    seed(db, "NOIND", market, indicators={"rsi": None})
    seed(db, "NOFEAT", market, features=False)
    seed(db, "NOUNI", market, status=None)
    seed(db, "MANY", weekdays("2026-09-08", 80), status="delisted")  # delisted and stale
    return {
        "OK": [], "DELIST": ["delisted"], "H64": ["insufficient_history"], "H65": [],
        "AGE3": [], "AGE4": ["stale"], "GAP2": [], "GAP3": ["near_gap"],
        "FLAGIN": ["hard_quality_flag"], "FLAGOUT": [], "SOFT": [],
        "NOIND": ["indicators_missing"], "NOFEAT": ["insufficient_history"],
        "NOUNI": [], "MANY": ["delisted", "stale"],
    }


def test_assess_many_equals_the_single_ticker_assessment_for_every_reason(db):
    from app.services.data_eligibility import assess_eligibility, assess_eligibility_many

    expected = _seed_catalog(db)
    tickers = [*expected, "NEVER"]  # a symbol with no rows at all

    many = assess_eligibility_many(tickers, now=MONDAY_MORNING)

    assert list(many) == tickers
    for ticker in tickers:
        assert many[ticker] == assess_eligibility(ticker, now=MONDAY_MORNING), ticker
    for ticker, reasons in expected.items():
        assert many[ticker]["reasons"] == reasons, ticker
        assert many[ticker]["eligible"] is (not reasons), ticker
    assert many["NEVER"] == {
        "eligible": False, "reasons": ["insufficient_history"], "as_of": None, "age_sessions": None,
    }


def test_assess_many_keeps_several_reasons_in_the_fixed_order(db):
    from app.services.data_eligibility import assess_eligibility_many

    _seed_catalog(db)

    result = assess_eligibility_many(["MANY"], now=MONDAY_MORNING)["MANY"]

    assert result["reasons"] == ["delisted", "stale"]
    assert result["age_sessions"] == 23  # 23 stored sessions after 2026-09-08 in the 100-session market


def test_assess_many_of_nothing_is_empty_and_reads_nothing(db):
    from app.services.data_eligibility import assess_eligibility_many

    assert assess_eligibility_many([], now=MONDAY_MORNING) == {}


def test_assess_many_rejects_a_naive_clock(db):
    from app.services.data_eligibility import assess_eligibility_many

    with pytest.raises(ValueError, match="timezone-aware"):
        assess_eligibility_many(["AAA"], now=datetime(2026, 10, 12, 10, 0))


def test_session_dates_are_scanned_once_for_a_whole_batch(db, tmp_path, monkeypatch):
    from app.services import data_eligibility

    expected = _seed_catalog(db)
    path = db.execute("PRAGMA database_list").fetchone()[2]
    statements: list[str] = []

    def traced():
        conn = sqlite3.connect(path)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(data_eligibility, "get_connection", traced)

    data_eligibility.assess_eligibility_many(list(expected), now=MONDAY_MORNING)

    scans = [s for s in statements if "SELECT DISTINCT date FROM ohlcv" in s]
    assert len(expected) > 10 and len(scans) == 1
