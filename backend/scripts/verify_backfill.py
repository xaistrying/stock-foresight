"""
Verification for the already-loaded-ticker backfill (hose-universe-ingestion,
tasks 5.2 and 5.3).

Asserts EXACT numbers, against the known-answer case the design establishes
for the original 15 tickers. Groups 1-3 left the flag-persistence and
flag-consumption paths wired but inert — `ohlcv_quality_flags` and
`ticker_universe.stale_close_fraction` were both empty — so this is the first
check that they actually carry data end to end.

Task 5.2 — persistence:
- 1 hard flag: `VHM` 2018-08-14.
- 24 soft flags, all in `ACB` (7), `VIB` (5), `VND` (12).
- 15 stale-close fractions, one per loaded ticker.
- 15 observed ranges and `ingestion_state = 'ok'`.

Task 5.3 — consumption. Both of Decision 9's effects, on `VHM`:
- the 5 targets before 2018-08-14 (previously about -0.68 to -0.70) are null;
- every indicator column is null for the 78 sessions from 2018-08-14 on;
- the first session past that lookback is computed normally again.

WHERE THE TASK TEXT IS OFF BY ONE. Task 5.3 says "four pre-split targets".
Measured, there are five: 2018-08-07 through 2018-08-13, which is
`TARGET_HORIZON` = 5 rows, exactly what Decision 9 and `compute_target`
describe. Five is the correct count; the task's "four" is a miscount, not a
behaviour difference.

DATABASE-DEPENDENT — reads backend/data/app.db. Writes nothing. Run manually
after `backfill_loaded_tickers.py`, not in CI.

Run from the project root: python backend/scripts/verify_backfill.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.ml.feature_engineering import (  # noqa: E402
    HARD_FLAG_BLACKOUT_SESSIONS,
    INDICATOR_COLUMNS,
    TARGET_HORIZON,
)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

EXPECTED_LOADED = 15
EXPECTED_HARD = [("VHM", "2018-08-14")]
EXPECTED_SOFT_BY_TICKER = {"ACB": 7, "VIB": 5, "VND": 12}
EXPECTED_SOFT_TOTAL = 24
EXPECTED_CLEAN_TICKERS = 11

FLAGGED_TICKER = "VHM"
FLAGGED_DATE = "2018-08-14"


def _check(passed: bool, label: str, detail: str = "") -> bool:
    print(f"  {'PASS' if passed else 'FAIL'}  {label}{f' — {detail}' if detail else ''}")
    return passed


def verify_persistence(conn: sqlite3.Connection) -> bool:
    print("Task 5.2 — flags and measurements persisted")
    ok = True

    loaded = [r[0] for r in conn.execute("SELECT ticker FROM tickers ORDER BY ticker")]
    ok &= _check(
        len(loaded) == EXPECTED_LOADED,
        f"{EXPECTED_LOADED} loaded tickers",
        f"found {len(loaded)}",
    )

    hard = conn.execute(
        "SELECT ticker, date FROM ohlcv_quality_flags WHERE flag_tier = 'hard' "
        "ORDER BY ticker, date"
    ).fetchall()
    ok &= _check(hard == EXPECTED_HARD, "exactly one hard flag", str(hard))

    soft = dict(
        conn.execute(
            "SELECT ticker, COUNT(*) FROM ohlcv_quality_flags "
            "WHERE flag_tier = 'soft' GROUP BY ticker ORDER BY ticker"
        )
    )
    ok &= _check(
        soft == EXPECTED_SOFT_BY_TICKER,
        f"{EXPECTED_SOFT_TOTAL} soft flags in ACB/VIB/VND only",
        str(soft),
    )

    # Every soft flag on these 15 is an unverified-fallback evaluation: they
    # are pre-migration rows judged against the exchange each trades on *now*
    # (`ticker-universe` requires the fallback be explicit).
    unverified = conn.execute(
        "SELECT COUNT(*) FROM ohlcv_quality_flags "
        "WHERE flag_tier = 'soft' AND limit_is_unverified_fallback = 1"
    ).fetchone()[0]
    ok &= _check(
        unverified == EXPECTED_SOFT_TOTAL,
        "every soft flag marked an unverified fallback",
        f"{unverified}/{EXPECTED_SOFT_TOTAL}",
    )

    flagged_tickers = {row[0] for row in hard} | set(soft)
    ok &= _check(
        len(loaded) - len(flagged_tickers) == EXPECTED_CLEAN_TICKERS,
        f"{EXPECTED_CLEAN_TICKERS} tickers entirely clean",
        f"{len(loaded) - len(flagged_tickers)}",
    )

    placeholders = ",".join("?" * len(loaded))
    stale, ranges, states = conn.execute(
        f"""
        SELECT SUM(stale_close_fraction IS NOT NULL),
               SUM(first_observed_session IS NOT NULL
                   AND last_observed_session IS NOT NULL
                   AND observed_session_count IS NOT NULL),
               SUM(ingestion_state = 'ok')
          FROM ticker_universe WHERE symbol IN ({placeholders})
        """,
        loaded,
    ).fetchone()
    ok &= _check(
        stale == EXPECTED_LOADED,
        f"{EXPECTED_LOADED} stale-close fractions recorded",
        f"{stale}",
    )
    ok &= _check(
        ranges == EXPECTED_LOADED,
        f"{EXPECTED_LOADED} observed ranges recorded",
        f"{ranges}",
    )
    ok &= _check(
        states == EXPECTED_LOADED,
        f"{EXPECTED_LOADED} marked ingestion_state = 'ok'",
        f"{states}",
    )

    # The observed range has to agree with what is actually stored, or
    # point-in-time reconstruction (design Decision 2) is reading a fiction.
    mismatched = conn.execute(
        f"""
        SELECT u.symbol FROM ticker_universe u
          JOIN (SELECT ticker, MIN(date) lo, MAX(date) hi, COUNT(*) n
                  FROM ohlcv GROUP BY ticker) o ON o.ticker = u.symbol
         WHERE u.symbol IN ({placeholders})
           AND (u.first_observed_session != o.lo
                OR u.last_observed_session != o.hi
                OR u.observed_session_count != o.n)
        """,
        loaded,
    ).fetchall()
    ok &= _check(
        not mismatched,
        "every observed range matches the stored ohlcv",
        str([r[0] for r in mismatched]),
    )
    return bool(ok)


def verify_feature_effects(conn: sqlite3.Connection) -> bool:
    print("\nTask 5.3 — both flag effects visible in `features`")
    ok = True

    dates = [
        row[0]
        for row in conn.execute(
            "SELECT date FROM ohlcv WHERE ticker = ? ORDER BY date", (FLAGGED_TICKER,)
        )
    ]
    position = dates.index(FLAGGED_DATE)

    # Effect 1: the TARGET_HORIZON targets *before* the flag, whose lookahead
    # spans the spurious step.
    before = dates[position - TARGET_HORIZON : position]
    placeholders = ",".join("?" * len(before))
    nulled = conn.execute(
        f"SELECT COUNT(*) FROM features WHERE ticker = ? AND date IN "
        f"({placeholders}) AND target IS NULL",
        [FLAGGED_TICKER, *before],
    ).fetchone()[0]
    ok &= _check(
        nulled == TARGET_HORIZON,
        f"the {TARGET_HORIZON} targets before {FLAGGED_DATE} are null",
        f"{nulled}/{TARGET_HORIZON} ({before[0]}..{before[-1]})",
    )
    ok &= _check(
        conn.execute(
            "SELECT target FROM features WHERE ticker = ? AND date = ?",
            (FLAGGED_TICKER, dates[position - TARGET_HORIZON - 1]),
        ).fetchone()[0]
        is not None,
        "the target one row earlier is untouched",
        dates[position - TARGET_HORIZON - 1],
    )
    ok &= _check(
        conn.execute(
            "SELECT target FROM features WHERE ticker = ? AND date = ?",
            (FLAGGED_TICKER, FLAGGED_DATE),
        ).fetchone()[0]
        is not None,
        "the flagged session's own target stays valid",
        "spans two closes on the far side of the step",
    )

    # Effect 2: every indicator column null for the longest lookback, from the
    # flagged session on.
    blackout = dates[position : position + HARD_FLAG_BLACKOUT_SESSIONS]
    placeholders = ",".join("?" * len(blackout))
    columns = ", ".join(INDICATOR_COLUMNS)
    populated = conn.execute(
        f"SELECT COUNT(*) FROM features WHERE ticker = ? AND date IN "
        f"({placeholders}) AND COALESCE({columns}) IS NOT NULL",
        [FLAGGED_TICKER, *blackout],
    ).fetchone()[0]
    ok &= _check(
        len(blackout) == HARD_FLAG_BLACKOUT_SESSIONS and populated == 0,
        f"all {len(INDICATOR_COLUMNS)} indicator columns null across "
        f"{HARD_FLAG_BLACKOUT_SESSIONS} sessions",
        f"{blackout[0]}..{blackout[-1]}, {populated} rows still populated",
    )

    first_clear = dates[position + HARD_FLAG_BLACKOUT_SESSIONS]
    clear_row = conn.execute(
        f"SELECT {columns} FROM features WHERE ticker = ? AND date = ?",
        (FLAGGED_TICKER, first_clear),
    ).fetchone()
    ok &= _check(
        all(value is not None for value in clear_row),
        "the first session past the lookback is computed normally",
        first_clear,
    )

    # The consequence the task text did not anticipate. `near_gap`'s warm-up
    # band covers rows 0..76 of VHM; the blackout covers 10..87, so its tail
    # falls on rows `near_gap` already cleared. Those rows stay in the
    # training set (`near_gap = 0`, target not null) but now carry null
    # features. Reported, not asserted away — see the session notes.
    leaked = conn.execute(
        f"SELECT COUNT(*) FROM features WHERE ticker = ? AND date IN "
        f"({placeholders}) AND near_gap = 0 AND target IS NOT NULL",
        [FLAGGED_TICKER, *blackout],
    ).fetchone()[0]
    print(
        f"  NOTE  {leaked} blacked-out rows are near_gap = 0 with a non-null "
        "target, so they remain in the training set with null features"
    )
    return bool(ok)


def main() -> int:
    if not DB_PATH.exists():
        print(f"FAIL: no database at {DB_PATH}")
        return 1
    conn = sqlite3.connect(DB_PATH)
    try:
        ok = verify_persistence(conn)
        ok = verify_feature_effects(conn) and ok
    finally:
        conn.close()
    print(f"\n{'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
