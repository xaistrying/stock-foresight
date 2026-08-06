import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest
from dateutil.relativedelta import relativedelta
from tenacity import RetryError
from vnstock.core.exceptions import RateLimitError

import app.ml.feature_engineering as feature_engineering
import app.services.ticker_ingestion as ticker_ingestion
from app.db.schema import CREATE_FEATURES_TABLE, CREATE_OHLCV_TABLE, CREATE_TICKERS_TABLE
from app.services.ticker_ingestion import UPSERT_OHLCV, load_ticker


def _load_with_fake_fetch(monkeypatch, tmp_path, df):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_TICKERS_TABLE)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        ticker_ingestion, "get_connection", lambda: sqlite3.connect(db_path)
    )
    monkeypatch.setattr(
        feature_engineering, "get_connection", lambda: sqlite3.connect(db_path)
    )

    class FakeEquity:
        def ohlcv(self, **kwargs):
            return df.copy()

    monkeypatch.setattr(ticker_ingestion.mkt, "equity", lambda ticker: FakeEquity())

    return load_ticker("VIB"), db_path


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

    with caplog.at_level("WARNING"):
        result, db_path = _load_with_fake_fetch(monkeypatch, tmp_path, df)

    assert "Gap of" in caplog.text
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
    conn.commit()

    row = conn.execute(
        "SELECT * FROM tickers WHERE ticker = 'NEVERLOADED'"
    ).fetchone()
    conn.close()
    assert row is None
