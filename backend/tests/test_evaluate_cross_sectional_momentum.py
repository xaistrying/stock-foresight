"""Tests for `backend/scripts/evaluate_cross_sectional_momentum.py`
(`cross-sectional-momentum-evaluation` change), covering the three explicit
"Test:" items in tasks.md: universe membership is read live (1.3), the
generalized purge matches `training.py`'s own machinery at horizon 5 (2.3),
and demeaning is cross-sectional rather than per-ticker (3.4).

The script lives under `backend/scripts/`, which is not a package (matching
every other script there), so it is loaded by file path rather than a
normal package import.
"""

import importlib.util
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from app.db.schema import CREATE_OHLCV_QUALITY_FLAGS_TABLE, CREATE_TICKER_UNIVERSE_TABLE
from app.ml.training import _label_dates_by_ticker, purge_training_rows

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "evaluate_cross_sectional_momentum.py"
)
_spec = importlib.util.spec_from_file_location("evaluate_cross_sectional_momentum", _SCRIPT_PATH)
ecsm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ecsm)


# --- 1.3: universe membership is read live ---


@pytest.fixture
def universe_db(monkeypatch, tmp_path):
    """A database holding only `ticker_universe`, matching
    test_ticker_universe.py's fixture pattern."""
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.commit()
    conn.close()
    return db_path


def _insert_universe_row(conn, symbol, *, ok=True, fails_liquidity=0, below_history=0):
    conn.execute(
        """
        INSERT INTO ticker_universe
            (symbol, listing_status, ingestion_state, fails_liquidity_filter,
             below_minimum_history, updated_at)
        VALUES (?, 'listed', ?, ?, ?, '2026-01-01T00:00:00')
        """,
        (symbol, "ok" if ok else "pending", fails_liquidity, below_history),
    )


def test_universe_membership_is_read_live(universe_db):
    # tasks.md 1.3: a symbol added to or removed from the modelling universe
    # changes what load_universe() returns without any code change — proven
    # by calling it twice against the same live connection, mutating the
    # table in between.
    conn = sqlite3.connect(universe_db)
    _insert_universe_row(conn, "AAA")
    _insert_universe_row(conn, "BBB", fails_liquidity=1)  # excluded
    conn.commit()

    first = ecsm.load_universe(conn=conn)
    assert first == ["AAA"]

    # Newly passes the filters.
    conn.execute(
        "UPDATE ticker_universe SET fails_liquidity_filter = 0 WHERE symbol = 'BBB'"
    )
    # Newly added symbol.
    _insert_universe_row(conn, "CCC")
    conn.commit()

    second = ecsm.load_universe(conn=conn)
    assert second == ["AAA", "BBB", "CCC"]

    conn.close()


# --- 2.3: known-answer check against training.py's own purge machinery ---


def _make_full_df(n_dates_per_ticker: int) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n_dates_per_ticker, freq="D").strftime("%Y-%m-%d")
    frames = []
    for ticker in ["AAA", "BBB", "CCC"]:
        frames.append(pd.DataFrame({"ticker": ticker, "date": dates}))
    return pd.concat(frames, ignore_index=True)


def test_purge_matches_training_module_at_target_horizon():
    # tasks.md 2.3: at horizon = TARGET_HORIZON (5), this script's local,
    # horizon-parameterized purge must reproduce exactly what calling
    # training._label_dates_by_ticker / training.purge_training_rows
    # directly on the same data produces — the check design.md Decision 1's
    # risk entry asks for, verified directly rather than assumed correct
    # from code inspection.
    full_df = _make_full_df(n_dates_per_ticker=40)
    clean_df = full_df.copy()  # every row is a "clean" candidate here
    boundary = sorted(full_df["date"].unique())[20]
    horizon = 5

    expected_label_dates = _label_dates_by_ticker(full_df)
    actual_label_dates = ecsm.label_dates_by_ticker(full_df, horizon)
    pd.testing.assert_frame_equal(
        actual_label_dates.sort_values(["ticker", "date"]).reset_index(drop=True),
        expected_label_dates.sort_values(["ticker", "date"]).reset_index(drop=True),
    )

    expected_purged = purge_training_rows(full_df, clean_df, boundary)
    actual_purged = ecsm.purge_rows(full_df, clean_df, boundary, horizon)
    pd.testing.assert_frame_equal(
        actual_purged.sort_values(["ticker", "date"]).reset_index(drop=True),
        expected_purged.sort_values(["ticker", "date"]).reset_index(drop=True),
    )


def test_purge_at_other_horizons_differs_from_fixed_horizon_5():
    # Sanity check that the generalization actually varies with horizon
    # (not silently pinned to 5) — a different horizon purges a different
    # *set* of rows near the same boundary (row count alone can coincide on
    # a symmetric fixture like this one, since NaN label dates at the tail
    # are kept regardless of horizon).
    full_df = _make_full_df(n_dates_per_ticker=40)
    clean_df = full_df.copy()
    boundary = sorted(full_df["date"].unique())[20]

    purged_5 = ecsm.purge_rows(full_df, clean_df, boundary, 5)
    purged_10 = ecsm.purge_rows(full_df, clean_df, boundary, 10)

    kept_5 = set(zip(purged_5["ticker"], purged_5["date"]))
    kept_10 = set(zip(purged_10["ticker"], purged_10["date"]))
    assert kept_5 != kept_10


# --- 3.4: demeaning is cross-sectional, not per-ticker ---


def test_demeaning_is_cross_sectional_not_per_ticker():
    # tasks.md 3.4: on a synthetic fixture where a per-ticker historical
    # mean and a same-date cross-sectional mean disagree, the demeaned
    # value must match the cross-sectional (same-date) construction.
    frame = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA", "BBB", "BBB"],
            "date": ["2024-01-01", "2024-01-02", "2024-01-01", "2024-01-02"],
            "signal": [1.0, 3.0, 5.0, 5.0],
            "forward_target": [0.10, 0.30, 0.50, 0.50],
        }
    )
    # AAA's own historical mean signal is 2.0 — if demeaning were per-ticker,
    # 2024-01-01's AAA row would become 1.0 - 2.0 = -1.0. Cross-sectionally,
    # 2024-01-01's mean across AAA/BBB is (1.0 + 5.0) / 2 = 3.0, so AAA's row
    # should become 1.0 - 3.0 = -2.0 instead — the two disagree, which is
    # the point of this fixture.
    demeaned = ecsm.demean_cross_sectionally(frame)

    aaa_jan1 = demeaned[(demeaned["ticker"] == "AAA") & (demeaned["date"] == "2024-01-01")]
    assert aaa_jan1["signal_demeaned"].iloc[0] == pytest.approx(-2.0)
    assert aaa_jan1["signal_demeaned"].iloc[0] != pytest.approx(-1.0)

    # Every date's demeaned signal must sum to (approximately) zero across
    # that date's symbols — the defining property of cross-sectional
    # demeaning.
    for _, day in demeaned.groupby("date"):
        assert day["signal_demeaned"].sum() == pytest.approx(0.0, abs=1e-9)
        assert day["forward_target_demeaned"].sum() == pytest.approx(0.0, abs=1e-9)
