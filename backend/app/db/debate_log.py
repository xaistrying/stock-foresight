"""The debate outcome log: its own SQLite file, apart from `app.db`.

`app.db` is rebuildable by reloading tickers. A logged debate is not (News and
Macro read live data), so the log has its own file and its own init, run on the
writer's connection at first write. `init_db` and `schema.py` do not know it.
"""

import sqlite3
from pathlib import Path

DEBATE_LOG_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "debate_log.db"

# No index: the table grows by tens of rows a day at most.
CREATE_DEBATE_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS debate_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    as_of TEXT NOT NULL,
    run_at TEXT NOT NULL,
    close_at_asof REAL,
    data_age_sessions INTEGER,
    eligible INTEGER NOT NULL,
    eligibility_reasons TEXT,
    agents_degraded TEXT,
    sigma_daily_pct REAL,
    range_5s_pct REAL,
    range_k REAL,
    range_coverage REAL,
    r1_technical TEXT,
    r1_news TEXT,
    r1_macro TEXT,
    r2_technical TEXT,
    r2_news TEXT,
    r2_macro TEXT,
    verdict TEXT NOT NULL,
    agreement_level TEXT,
    model_sha256 TEXT,
    llm_provider TEXT,
    llm_model TEXT,
    llm_effort TEXT,
    code_rev TEXT,
    evidence TEXT,
    outcome_status TEXT,
    scored_at TEXT,
    date_t5 TEXT,
    close_asof_at_scoring REAL,
    close_t5 REAL,
    r5 REAL,
    inside_band INTEGER,
    direction_hit INTEGER
)
"""


def get_debate_log_connection() -> sqlite3.Connection:
    DEBATE_LOG_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DEBATE_LOG_DB_PATH)


def init_debate_log_db(conn: sqlite3.Connection) -> None:
    conn.execute(CREATE_DEBATE_LOG_TABLE)
    conn.commit()
