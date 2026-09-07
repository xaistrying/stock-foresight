import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest
from dateutil.relativedelta import relativedelta
from tenacity import RetryError
from vnstock.core.exceptions import RateLimitError

import app.ml.feature_engineering as feature_engineering
import app.services.ohlcv_quality_gate as ohlcv_quality_gate
import app.services.ticker_ingestion as ticker_ingestion
import app.services.ticker_universe as ticker_universe
from app.db.schema import (
    CREATE_FEATURES_TABLE,
    CREATE_OHLCV_QUALITY_FLAGS_TABLE,
    CREATE_OHLCV_TABLE,
    CREATE_TICKER_UNIVERSE_TABLE,
    CREATE_TICKERS_TABLE,
)
from app.services.ticker_ingestion import UPSERT_OHLCV, load_ticker


def _load_with_fake_fetch(monkeypatch, tmp_path, df, universe_row=None, ticker="VIB"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_TICKERS_TABLE)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    if universe_row is not None:
        conn.execute(
            "INSERT INTO ticker_universe (symbol, exchange, icb_code2, "
            "listing_status, updated_at) VALUES (?, ?, NULL, ?, ?)",
            (
                universe_row["symbol"],
                universe_row.get("exchange"),
                universe_row.get("listing_status", "listed"),
                "2026-09-03T00:00:00",
            ),
        )
    conn.commit()
    conn.close()

    # `load_ticker` now reaches the quality gate and the universe as well, and
    # each module holds its own `get_connection` — every one of them has to be
    # redirected or the load writes to the real database.
    for module in (
        ticker_ingestion,
        feature_engineering,
        ohlcv_quality_gate,
        ticker_universe,
    ):
        monkeypatch.setattr(
            module, "get_connection", lambda: sqlite3.connect(db_path)
        )

    class FakeEquity:
        def ohlcv(self, **kwargs):
            return df.copy()

    monkeypatch.setattr(ticker_ingestion.mkt, "equity", lambda t: FakeEquity())

    return load_ticker(ticker), db_path


def _single_row_df(session_date):
    return pd.DataFrame(
        {
            "time": pd.to_datetime([f"{session_date.isoformat()} 07:00:00"]),
            "open": [10.0],
            "high": [10.5],
            "low": [9.5],
            "close": [10.2],
            "volume": [1000],
        }
    )


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute(CREATE_OHLCV_TABLE)
    yield connection
    connection.close()


def test_upsert_on_reload_updates_existing_row_without_duplicating(conn):
    conn.execute(UPSERT_OHLCV, ("VIB", "2024-01-02", 10.0, 11.0, 9.5, 10.5, 1000))
    conn.commit()

    conn.execute(UPSERT_OHLCV, ("VIB", "2024-01-02", 20.0, 21.0, 19.5, 20.5, 2000))
    conn.commit()

    rows = conn.execute(
        "SELECT ticker, date, open, high, low, close, volume FROM ohlcv"
    ).fetchall()

    assert rows == [("VIB", "2024-01-02", 20.0, 21.0, 19.5, 20.5, 2000)]


def test_strips_seven_am_quirk_to_date_only_iso_text():
    df = pd.DataFrame(
        {
            "time": pd.to_datetime(
                ["2024-01-02 07:00:00", "2024-01-03 07:00:00"]
            ),
        }
    )

    df["time"] = df["time"].dt.date.astype(str)

    assert df["time"].tolist() == ["2024-01-02", "2024-01-03"]


def test_gap_over_five_days_is_logged_but_does_not_fail_load(monkeypatch, caplog, tmp_path):
    df = pd.DataFrame(
        {
            "time": pd.to_datetime(
                ["2024-01-02 07:00:00", "2024-01-20 07:00:00"]
            ),
            "open": [10.0, 11.0],
            "high": [10.5, 11.5],
            "low": [9.5, 10.5],
            "close": [10.2, 11.2],
            "volume": [1000, 1100],
        }
    )

    with caplog.at_level("INFO"):
        result, db_path = _load_with_fake_fetch(monkeypatch, tmp_path, df)

    # One aggregated line per ticker, not one per gap: Vietnamese market
    # holidays give every symbol ~13 a decade, so per-gap logging across 634
    # symbols buries a batch run's real errors under ~8,000 lines.
    assert "1 calendar gap(s) over 5 days" in caplog.text
    assert "widest 18 days between 2024-01-02 and 2024-01-20" in caplog.text
    assert result["rows_loaded"] == 2

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT date FROM ohlcv ORDER BY date").fetchall()
    conn.close()
    assert rows == [("2024-01-02",), ("2024-01-20",)]


def test_possibly_truncated_by_tier_set_at_boundary(monkeypatch, tmp_path):
    end = date.today()
    tier_floor = end - relativedelta(years=8)
    available_since = tier_floor + timedelta(days=30)  # exactly 30 days away

    df = _single_row_df(available_since)
    result, db_path = _load_with_fake_fetch(monkeypatch, tmp_path, df)

    assert result["possibly_truncated_by_tier"] is True

    conn = sqlite3.connect(db_path)
    ticker_row = conn.execute(
        "SELECT possibly_truncated_by_tier FROM tickers WHERE ticker = 'VIB'"
    ).fetchone()
    ohlcv_rows = conn.execute("SELECT date FROM ohlcv").fetchall()
    conn.close()

    assert ticker_row == (1,)
    assert ohlcv_rows == [(available_since.isoformat(),)]


def test_possibly_truncated_by_tier_unset_outside_boundary(monkeypatch, tmp_path):
    end = date.today()
    tier_floor = end - relativedelta(years=8)
    available_since = tier_floor + timedelta(days=31)  # just outside the 30-day tolerance

    df = _single_row_df(available_since)
    result, db_path = _load_with_fake_fetch(monkeypatch, tmp_path, df)

    assert result["possibly_truncated_by_tier"] is False

    conn = sqlite3.connect(db_path)
    ticker_row = conn.execute(
        "SELECT possibly_truncated_by_tier FROM tickers WHERE ticker = 'VIB'"
    ).fetchone()
    ohlcv_rows = conn.execute("SELECT date FROM ohlcv").fetchall()
    conn.close()

    assert ticker_row == (0,)
    assert ohlcv_rows == [(available_since.isoformat(),)]


def test_load_ticker_triggers_feature_computation_for_the_loaded_ticker(
    monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setattr(
        ticker_ingestion, "recompute_features_for_ticker", calls.append
    )

    df = _single_row_df(date(2024, 1, 2))
    result, _db_path = _load_with_fake_fetch(monkeypatch, tmp_path, df)

    assert calls == ["VIB"]
    assert result["features_computed"] is True


def test_load_ticker_reports_features_computed_false_without_failing_the_load(
    monkeypatch, tmp_path
):
    def _boom(ticker):
        raise RuntimeError("feature computation exploded")

    monkeypatch.setattr(ticker_ingestion, "recompute_features_for_ticker", _boom)

    df = _single_row_df(date(2024, 1, 2))
    result, db_path = _load_with_fake_fetch(monkeypatch, tmp_path, df)

    assert result["rows_loaded"] == 1
    assert result["features_computed"] is False

    conn = sqlite3.connect(db_path)
    ohlcv_rows = conn.execute("SELECT date FROM ohlcv").fetchall()
    conn.close()
    assert ohlcv_rows == [("2024-01-02",)]


def test_load_ticker_persists_features_computed_1_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ticker_ingestion, "recompute_features_for_ticker", lambda ticker: None
    )

    df = _single_row_df(date(2024, 1, 2))
    _result, db_path = _load_with_fake_fetch(monkeypatch, tmp_path, df)

    conn = sqlite3.connect(db_path)
    ticker_row = conn.execute(
        "SELECT features_computed FROM tickers WHERE ticker = 'VIB'"
    ).fetchone()
    conn.close()
    assert ticker_row == (1,)


def test_load_ticker_persists_features_computed_0_on_failure(monkeypatch, tmp_path):
    def _boom(ticker):
        raise RuntimeError("feature computation exploded")

    monkeypatch.setattr(ticker_ingestion, "recompute_features_for_ticker", _boom)

    df = _single_row_df(date(2024, 1, 2))
    _result, db_path = _load_with_fake_fetch(monkeypatch, tmp_path, df)

    conn = sqlite3.connect(db_path)
    ticker_row = conn.execute(
        "SELECT features_computed FROM tickers WHERE ticker = 'VIB'"
    ).fetchone()
    conn.close()
    assert ticker_row == (0,)


class _FakeLastAttempt:
    """Minimal stand-in for tenacity's Future — RetryError only relies on
    `.last_attempt.exception()`, so that's all this fakes."""

    def __init__(self, exc):
        self._exc = exc

    def exception(self):
        return self._exc


def _load_with_raising_fetch(monkeypatch, exc):
    class RaisingEquity:
        def ohlcv(self, **kwargs):
            raise exc

    monkeypatch.setattr(ticker_ingestion.mkt, "equity", lambda ticker: RaisingEquity())
    return load_ticker("VIB")


def test_rate_limit_reports_status_rate_limited(monkeypatch):
    result = _load_with_raising_fetch(monkeypatch, RateLimitError("rate limited"))

    assert result["status"] == "rate_limited"
    assert result["rows_loaded"] == 0


def test_invalid_symbol_format_reports_status_invalid_symbol(monkeypatch):
    result = _load_with_raising_fetch(
        monkeypatch,
        ValueError("Invalid symbol. Your symbol format is not recognized!"),
    )

    assert result["status"] == "invalid_symbol"
    assert result["rows_loaded"] == 0


def test_invalid_symbol_length_reports_status_invalid_symbol(monkeypatch):
    result = _load_with_raising_fetch(
        monkeypatch,
        ValueError("Symbol must be between 3 and 12 characters long."),
    )

    assert result["status"] == "invalid_symbol"
    assert result["rows_loaded"] == 0


def test_well_formed_ticker_with_no_data_reports_status_no_data(monkeypatch):
    underlying = ValueError(
        "Không tìm thấy dữ liệu. Vui lòng kiểm tra lại mã chứng khoán hoặc "
        "thời gian truy xuất."
    )
    exc = RetryError(_FakeLastAttempt(underlying))

    result = _load_with_raising_fetch(monkeypatch, exc)

    assert result["status"] == "no_data"
    assert result["rows_loaded"] == 0


def test_unrecognized_value_error_is_not_misclassified(monkeypatch):
    with pytest.raises(ValueError, match="some other problem"):
        _load_with_raising_fetch(monkeypatch, ValueError("some other problem"))


def test_successful_load_reports_status_ok(monkeypatch, tmp_path):
    df = _single_row_df(date(2024, 1, 2))
    result, _db_path = _load_with_fake_fetch(monkeypatch, tmp_path, df)

    assert result["status"] == "ok"


def test_never_loaded_ticker_has_no_tickers_row_at_all(tmp_path):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_TICKERS_TABLE)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.commit()

    row = conn.execute(
        "SELECT * FROM tickers WHERE ticker = 'NEVERLOADED'"
    ).fetchone()
    conn.close()
    assert row is None


# --- quality gate wired into the load (hose-universe-ingestion tasks 4.1-4.6) ---


def _series_df(start: date, closes: list[float]) -> pd.DataFrame:
    """A fetch-shaped frame: consecutive weekday-ish sessions, one close each.

    Sessions are one calendar day apart so no `near_gap`-style gap warning
    fires and the only thing under test is the quality gate.
    """
    return pd.DataFrame(
        {
            "time": pd.to_datetime(
                [f"{(start + timedelta(days=i)).isoformat()} 07:00:00"
                 for i in range(len(closes))]
            ),
            "open": closes,
            "high": [c * 1.001 for c in closes],
            "low": [c * 0.999 for c in closes],
            "close": closes,
            "volume": [1000] * len(closes),
        }
    )


def test_load_runs_the_quality_gate_and_reports_its_counts(monkeypatch, tmp_path):
    """The gate is part of the load, not a follow-up pass
    (`ohlcv-quality-gate`: results available immediately after load)."""
    # A halving mid-series, modelled on VHM 2018-08-14 — past the widest
    # exchange limit, so hard-flagged.
    df = _series_df(date(2024, 1, 2), [100.0, 100.1, 50.0, 50.1, 50.2])
    result, _db_path = _load_with_fake_fetch(
        monkeypatch, tmp_path, df, universe_row={"symbol": "VIB", "exchange": "HSX"}
    )

    assert result["status"] == "ok"
    assert result["hard_flag_count"] == 1
    assert result["soft_flag_count"] == 0
    assert result["stale_close_fraction"] == 0.0


def test_flagged_rows_are_persisted_rather_than_rejecting_the_whole_load(
    monkeypatch, tmp_path
):
    """Task 4.2: the data stays inspectable — every fetched row lands in
    `ohlcv`, and the flag lands beside it in the sidecar."""
    df = _series_df(date(2024, 1, 2), [100.0, 100.1, 50.0, 50.1, 50.2])
    result, db_path = _load_with_fake_fetch(
        monkeypatch, tmp_path, df, universe_row={"symbol": "VIB", "exchange": "HSX"}
    )

    assert result["rows_loaded"] == 5

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone() == (5,)
        flags = conn.execute(
            "SELECT date, flag_tier FROM ohlcv_quality_flags WHERE ticker = 'VIB'"
        ).fetchall()
    finally:
        conn.close()
    assert flags == [("2024-01-04", "hard")]


def test_soft_flag_uses_the_universe_entry_s_exchange(monkeypatch, tmp_path):
    """A -9% session is legal on HNX and illegal on HOSE, so which flag it
    gets proves the gate read the universe's exchange rather than guessing."""
    df = _series_df(date(2024, 1, 2), [100.0, 91.0, 91.1])
    _hose, hose_db = _load_with_fake_fetch(
        monkeypatch, tmp_path / "hose", df,
        universe_row={"symbol": "VIB", "exchange": "HSX"},
    )
    _hnx, hnx_db = _load_with_fake_fetch(
        monkeypatch, tmp_path / "hnx", df,
        universe_row={"symbol": "VIB", "exchange": "HNX"},
    )

    def tiers(db_path):
        conn = sqlite3.connect(db_path)
        try:
            return conn.execute(
                "SELECT flag_tier FROM ohlcv_quality_flags WHERE ticker = 'VIB'"
            ).fetchall()
        finally:
            conn.close()

    assert tiers(hose_db) == [("soft",)]
    assert tiers(hnx_db) == []


def test_load_updates_the_universe_entry_s_observed_range_and_state(
    monkeypatch, tmp_path
):
    """Task 4.3. Universe construction cannot know these — the listing carries
    no dates — so a load is the only thing that populates them."""
    df = _series_df(date(2024, 1, 2), [100.0, 100.5, 101.0, 101.5])
    _result, db_path = _load_with_fake_fetch(
        monkeypatch, tmp_path, df, universe_row={"symbol": "VIB", "exchange": "HSX"}
    )

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT first_observed_session, last_observed_session, "
            "observed_session_count, ingestion_state, ingestion_last_error, "
            "stale_close_fraction FROM ticker_universe WHERE symbol = 'VIB'"
        ).fetchone()
    finally:
        conn.close()

    assert row[:5] == ("2024-01-02", "2024-01-05", 4, "ok", None)
    assert row[5] == 0.0


def test_a_refresh_with_a_narrower_window_keeps_flags_outside_it(
    monkeypatch, tmp_path
):
    """The regression guard for task 6.9's refresh.

    The community tier's ~8-year window slides forward, so a refetch returns
    *less* history than is stored, and `ohlcv` rows are never deleted. The
    gate therefore has to read the stored series: gating the fetched frame
    would see no flagged session, and `persist_quality_gate_result` deletes
    the ticker's flags before writing — so `VHM`'s 2018-08-14 hard flag, now
    older than the tier floor, would vanish on every refresh, taking the
    78-session blackout and the nulled targets with it.
    """
    first_fetch = _series_df(date(2024, 1, 2), [100.0, 100.1, 50.0, 50.1, 50.2])
    _result, db_path = _load_with_fake_fetch(
        monkeypatch, tmp_path, first_fetch,
        universe_row={"symbol": "VIB", "exchange": "HSX"},
    )

    def flags():
        conn = sqlite3.connect(db_path)
        try:
            return conn.execute(
                "SELECT date, flag_tier FROM ohlcv_quality_flags "
                "WHERE ticker = 'VIB' ORDER BY date"
            ).fetchall()
        finally:
            conn.close()

    assert flags() == [("2024-01-04", "hard")]

    # A second load whose window starts after the flagged session — exactly
    # what the sliding tier floor produces.
    narrower = _series_df(date(2024, 1, 6), [50.3, 50.4, 50.5])

    class FakeEquity:
        def ohlcv(self, **kwargs):
            return narrower.copy()

    monkeypatch.setattr(ticker_ingestion.mkt, "equity", lambda t: FakeEquity())
    result = load_ticker("VIB")

    assert result["status"] == "ok"
    assert flags() == [("2024-01-04", "hard")], (
        "the refresh deleted a flag it could no longer see"
    )
    assert result["hard_flag_count"] == 1

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT first_observed_session, last_observed_session, "
            "observed_session_count FROM ticker_universe WHERE symbol = 'VIB'"
        ).fetchone()
    finally:
        conn.close()
    # The observed range describes the stored history, not the last fetch
    # (docs/DATA_DICTIONARY.md), or point-in-time reconstruction would think
    # the symbol came into existence when the tier window moved.
    # The two windows overlap on 2024-01-06, so the union is 7 sessions.
    assert row == ("2024-01-02", "2024-01-08", 7)


def test_a_delisted_symbol_whose_last_session_is_years_old_loads_cleanly(
    monkeypatch, tmp_path
):
    """Task 4.4. Nothing compares `last_observed_session` against today, so an
    old final session is just an old final session — the whole point of
    ingesting delisted names (design Decision 2)."""
    df = _series_df(date(2018, 3, 1), [20.0, 20.1, 20.2])
    result, db_path = _load_with_fake_fetch(
        monkeypatch,
        tmp_path,
        df,
        universe_row={
            "symbol": "VSP",
            "exchange": None,
            "listing_status": "delisted",
        },
        ticker="VSP",
    )

    assert result["status"] == "ok"
    assert result["rows_loaded"] == 3
    # No exchange on a delisted row, so no soft tier — but the hard gate needs
    # none and still ran, which the reported count (not None) shows.
    assert result["hard_flag_count"] == 0
    assert result["soft_flag_count"] == 0

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT last_observed_session, ingestion_state, listing_status "
            "FROM ticker_universe WHERE symbol = 'VSP'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("2018-03-03", "ok", "delisted")


def test_a_symbol_outside_the_universe_still_loads_and_still_gets_the_hard_gate(
    monkeypatch, tmp_path
):
    """The originally-loaded 15 predate the universe table (task 5.1 backfills
    them). A missing universe row must not fail the load, and the hard gate
    needs no exchange to be correct."""
    df = _series_df(date(2024, 1, 2), [100.0, 100.1, 50.0])
    result, db_path = _load_with_fake_fetch(monkeypatch, tmp_path, df)

    assert result["status"] == "ok"
    assert result["hard_flag_count"] == 1

    conn = sqlite3.connect(db_path)
    try:
        flags = conn.execute(
            "SELECT date FROM ohlcv_quality_flags WHERE ticker = 'VIB'"
        ).fetchall()
        universe = conn.execute("SELECT COUNT(*) FROM ticker_universe").fetchone()
    finally:
        conn.close()
    assert flags == [("2024-01-04",)]
    assert universe == (0,)


def test_a_gate_failure_does_not_fail_the_load(monkeypatch, tmp_path):
    """Losing the measurement is a smaller harm than discarding a successful
    fetch, and the rows are already stored by the time the gate runs."""
    def _boom(*args, **kwargs):
        raise RuntimeError("gate exploded")

    monkeypatch.setattr(ticker_ingestion, "run_quality_gate", _boom)

    df = _series_df(date(2024, 1, 2), [100.0, 100.1])
    result, db_path = _load_with_fake_fetch(monkeypatch, tmp_path, df)

    assert result["status"] == "ok"
    assert result["rows_loaded"] == 2
    assert result["hard_flag_count"] is None

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone() == (2,)
    finally:
        conn.close()


def test_the_gate_runs_before_feature_recomputation_reads_its_flags(
    monkeypatch, tmp_path
):
    """Ordering is load-bearing: `recompute_features_for_ticker` reads the
    flags back out of the sidecar, so a gate that ran afterwards would leave
    every load's first feature computation using un-neutralised data."""
    df = _series_df(date(2024, 1, 2), [100.0, 100.1, 50.0, 50.1])

    seen = {}
    real = ticker_ingestion.recompute_features_for_ticker

    def _spy(ticker):
        conn = sqlite3.connect(db_path_holder["path"])
        try:
            seen["flags"] = conn.execute(
                "SELECT COUNT(*) FROM ohlcv_quality_flags WHERE ticker = ?",
                (ticker,),
            ).fetchone()[0]
        finally:
            conn.close()
        return real(ticker)

    db_path_holder = {"path": tmp_path / "app.db"}
    monkeypatch.setattr(ticker_ingestion, "recompute_features_for_ticker", _spy)

    _result, _db_path = _load_with_fake_fetch(
        monkeypatch, tmp_path, df, universe_row={"symbol": "VIB", "exchange": "HSX"}
    )

    assert seen["flags"] == 1


def test_the_single_call_fetch_contract_is_unchanged(monkeypatch, tmp_path):
    """Task 4.5 / the existing `ticker-data-ingestion` requirement: exactly one
    `ohlcv` call per load, with `count=5000` and `source="vci"` through
    `vnstock.ui.Market`. Wiring the gate in must not add a second fetch or
    start chunking."""
    calls = []

    class RecordingEquity:
        def ohlcv(self, **kwargs):
            calls.append(kwargs)
            return _series_df(date(2024, 1, 2), [100.0, 100.5]).copy()

    equity_calls = []

    def _equity(ticker):
        equity_calls.append(ticker)
        return RecordingEquity()

    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_TICKERS_TABLE)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    conn.commit()
    conn.close()
    for module in (
        ticker_ingestion,
        feature_engineering,
        ohlcv_quality_gate,
        ticker_universe,
    ):
        monkeypatch.setattr(module, "get_connection", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(ticker_ingestion.mkt, "equity", _equity)

    load_ticker("VIB")

    assert equity_calls == ["VIB"]
    assert len(calls) == 1
    assert calls[0]["count"] == 5000
    assert calls[0]["source"] == "vci"
    assert calls[0]["start"] == "2000-01-01"
    assert calls[0]["end"] == date.today().isoformat()
