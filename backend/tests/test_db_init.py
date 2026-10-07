import sqlite3

from app.db import connection
from app.db import debate_log as debate_log_mod

# The table the retired direction model wrote. `init_db()` no longer defines it, so the test
# carries its own copy of the legacy shape.
LEGACY_BACKTEST_PREDICTIONS_DDL = """
CREATE TABLE backtest_predictions (
    ticker TEXT NOT NULL, date TEXT NOT NULL, fold INTEGER NOT NULL,
    predicted REAL NOT NULL, actual REAL NOT NULL, hit INTEGER NOT NULL,
    PRIMARY KEY (ticker, date)
)
"""


def _isolate(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    monkeypatch.setattr(connection, "DB_PATH", db_path)
    monkeypatch.setattr(debate_log_mod, "DEBATE_LOG_DB_PATH", tmp_path / "debate_log.db")
    return db_path


def test_init_db_leaves_backtest_predictions_rows_untouched(tmp_path, monkeypatch):
    db_path = _isolate(monkeypatch, tmp_path)
    seeded = [("TCB", "2026-08-01", 1, 0.01, -0.02, 0), ("VIB", "2026-08-05", 5, -0.03, -0.01, 1)]
    conn = sqlite3.connect(db_path)
    conn.execute(LEGACY_BACKTEST_PREDICTIONS_DDL)
    conn.executemany("INSERT INTO backtest_predictions VALUES (?, ?, ?, ?, ?, ?)", seeded)
    conn.commit()
    conn.close()

    connection.init_db()
    connection.init_db()  # a second start must not change them either

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT * FROM backtest_predictions ORDER BY ticker").fetchall()
    conn.close()
    assert rows == seeded


def test_fresh_db_has_no_backtest_predictions_table(tmp_path, monkeypatch):
    db_path = _isolate(monkeypatch, tmp_path)

    connection.init_db()

    conn = sqlite3.connect(db_path)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    conn.close()
    assert "backtest_predictions" not in names
    assert {"ohlcv", "tickers", "features", "ticker_universe"} <= names
