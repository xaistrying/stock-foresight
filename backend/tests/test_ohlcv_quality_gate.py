import math
import sqlite3
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import app.services.ohlcv_quality_gate as quality_gate
from app.db.schema import CREATE_OHLCV_QUALITY_FLAGS_TABLE, CREATE_TICKER_UNIVERSE_TABLE
from app.services.ohlcv_quality_gate import (
    DAILY_PRICE_LIMITS,
    FLAG_REASON_INVALID_CLOSE,
    FLAG_REASON_POST_HALT_RESUMPTION,
    FLAG_REASON_PRICE_LIMIT,
    FLAG_TIER_HARD,
    FLAG_TIER_SOFT,
    HARD_GATE_LIMIT,
    PRICE_LIMIT_TOLERANCE,
    STALE_CLOSE_FRACTION_THRESHOLD,
    evaluate_price_limits,
    hard_flagged_dates,
    log_return_bounds,
    neutralise_hard_flagged_returns,
    price_grid_step,
    persist_quality_gate_result,
    run_quality_gate,
    soft_limit_for_exchange,
    stale_close_fraction,
)


def _series_from_moves(first_close, moves):
    """Closes produced by applying successive *simple* returns, with dates."""
    closes = [float(first_close)]
    for move in moves:
        closes.append(closes[-1] * (1.0 + move))
    dates = [f"2020-01-{day:02d}" for day in range(1, len(closes) + 1)]
    return pd.DataFrame({"date": dates, "close": closes})


# --- limits as named constants (task 3.1) ---


def test_price_limits_are_the_real_exchange_limits():
    assert DAILY_PRICE_LIMITS == {"HSX": 0.07, "HNX": 0.10, "UPCOM": 0.15}


def test_hard_gate_uses_the_widest_limit_in_the_table():
    """The hard gate must not depend on which exchange a row belonged to on
    its date, which is exactly what cannot be reconstructed."""
    assert HARD_GATE_LIMIT == max(DAILY_PRICE_LIMITS.values()) == 0.15


def test_unknown_exchange_has_no_soft_limit():
    assert soft_limit_for_exchange(None) is None
    assert soft_limit_for_exchange("NOT_AN_EXCHANGE") is None
    assert soft_limit_for_exchange("HSX") == 0.07


# --- bounds conversion (tasks 3.2, 3.3) ---


def test_bounds_convert_each_side_of_the_limit_exactly():
    lower, upper = log_return_bounds(0.07, tolerance=0.0)
    assert lower == pytest.approx(math.log(0.93))
    assert upper == pytest.approx(math.log(1.07))


def test_tolerance_widens_both_sides():
    lower, upper = log_return_bounds(0.07, tolerance=0.002)
    assert lower == pytest.approx(math.log(0.93) - 0.002)
    assert upper == pytest.approx(math.log(1.07) + 0.002)


@pytest.mark.parametrize("exchange,limit", sorted(DAILY_PRICE_LIMITS.items()))
def test_a_legitimate_limit_down_session_is_never_hard_flagged(exchange, limit):
    """The reason bounds are converted per side rather than compared against
    `|log_return|`: a genuine UPCOM limit-down is `ln(0.85) = -0.1625`, which
    a flat `|log| > 0.15` test would call corrupt data."""
    df = _series_from_moves(100.0, [-limit])
    flags = evaluate_price_limits(df["date"], df["close"], exchange)
    assert [f["flag_tier"] for f in flags] == []


@pytest.mark.parametrize("exchange,limit", sorted(DAILY_PRICE_LIMITS.items()))
def test_a_legitimate_limit_up_session_is_never_flagged(exchange, limit):
    df = _series_from_moves(100.0, [limit])
    assert evaluate_price_limits(df["date"], df["close"], exchange) == []


# --- hard gate (task 3.2) ---


def test_a_move_past_the_widest_limit_is_hard_flagged():
    df = _series_from_moves(100.0, [-0.50])
    flags = evaluate_price_limits(df["date"], df["close"], "HSX")
    assert len(flags) == 1
    assert flags[0]["flag_tier"] == FLAG_TIER_HARD
    assert flags[0]["date"] == df["date"].iloc[1]
    assert flags[0]["log_return"] == pytest.approx(math.log(0.5))


def test_hard_flag_records_no_exchange_because_it_needs_none():
    """Recording one would imply a dated-membership claim the data cannot
    support."""
    df = _series_from_moves(100.0, [-0.50])
    flag = evaluate_price_limits(df["date"], df["close"], "HSX")[0]
    assert flag["limit_exchange"] is None
    assert flag["limit_is_unverified_fallback"] == 0


def test_hard_gate_applies_even_with_no_known_exchange():
    """A delisted symbol carries no exchange field, but the hard gate does not
    depend on one."""
    df = _series_from_moves(100.0, [-0.50])
    flags = evaluate_price_limits(df["date"], df["close"], None)
    assert [f["flag_tier"] for f in flags] == [FLAG_TIER_HARD]


# --- soft flag (task 3.3) ---


def test_a_move_past_the_current_exchange_limit_is_soft_flagged():
    df = _series_from_moves(100.0, [-0.11])
    flags = evaluate_price_limits(df["date"], df["close"], "HSX")
    assert len(flags) == 1
    assert flags[0]["flag_tier"] == FLAG_TIER_SOFT
    assert flags[0]["limit_exchange"] == "HSX"


def test_soft_flag_marks_itself_as_an_unverified_fallback():
    """The `ticker-universe` spec requires the fallback be explicit rather
    than silently asserting current exchange as historical fact."""
    df = _series_from_moves(100.0, [-0.11])
    flag = evaluate_price_limits(df["date"], df["close"], "HSX")[0]
    assert flag["limit_is_unverified_fallback"] == 1


def test_soft_flag_can_record_a_verified_membership_when_one_is_known():
    df = _series_from_moves(100.0, [-0.11])
    flag = evaluate_price_limits(
        df["date"], df["close"], "HSX", exchange_is_unverified_fallback=False
    )[0]
    assert flag["limit_is_unverified_fallback"] == 0


def test_a_pre_migration_move_legal_on_a_wider_exchange_is_soft_not_hard():
    """`VIB`'s real -11.6% pre-migration session was legal under UPCOM's
    limit. It must be surfaced for review but never treated as corrupt."""
    df = _series_from_moves(100.0, [-0.116])
    flags = evaluate_price_limits(df["date"], df["close"], "HSX")
    assert [f["flag_tier"] for f in flags] == [FLAG_TIER_SOFT]


def test_no_soft_evaluation_without_a_known_exchange():
    """A move breaching HOSE's limit but not the hard gate cannot be soft
    flagged for a symbol whose exchange is unknown — there is no limit to
    evaluate against."""
    df = _series_from_moves(100.0, [-0.11])
    assert evaluate_price_limits(df["date"], df["close"], None) == []


def test_first_row_has_no_return_and_is_never_flagged():
    df = pd.DataFrame({"date": ["2020-01-01"], "close": [100.0]})
    assert evaluate_price_limits(df["date"], df["close"], "HSX") == []


def test_a_zero_close_is_hard_flagged_rather_than_skipped():
    """Found by the first batch dry run: `VKP` has a single `close = 0.0`.
    The returns either side of it are ±inf, which the gate used to discard
    along with the row — so the most corrupt row shape in the data was the
    one row the hard gate ignored.
    """
    df = pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02", "2020-01-03"],
         "close": [100.0, 0.0, 100.0]}
    )

    flags = evaluate_price_limits(df["date"], df["close"], "HSX")

    assert [(f["date"], f["flag_tier"], f["flag_reason"]) for f in flags] == [
        ("2020-01-02", FLAG_TIER_HARD, FLAG_REASON_INVALID_CLOSE)
    ]
    # -inf is the true measured ratio and stores faithfully in SQLite.
    assert flags[0]["log_return"] == float("-inf")


def test_an_unparseable_close_is_hard_flagged_with_a_storable_return():
    """NaN cannot reach the sidecar — sqlite3 turns it into NULL, which the
    column rejects — so a row with no computable return records 0.0 and says
    why in `flag_reason`."""
    df = pd.DataFrame(
        {"date": ["2020-01-01", "2020-01-02", "2020-01-03"],
         "close": [100.0, np.nan, 100.0]}
    )

    flags = evaluate_price_limits(df["date"], df["close"], "HSX")

    assert [(f["date"], f["flag_tier"], f["flag_reason"]) for f in flags] == [
        ("2020-01-02", FLAG_TIER_HARD, FLAG_REASON_INVALID_CLOSE)
    ]
    assert flags[0]["log_return"] == 0.0


def _dated(closes: list[float]) -> pd.DataFrame:
    """Consecutive daily sessions for `closes`, long enough that a grid can
    actually be established (`MIN_GRID_STEP_OBSERVATIONS`)."""
    start = date(2020, 1, 1)
    return pd.DataFrame(
        {
            "date": [(start + timedelta(days=i)).isoformat() for i in range(len(closes))],
            "close": closes,
        }
    )


def test_one_price_grid_step_is_never_a_violation():
    """`VKP`'s real shape: five distinct closes in 2,001 sessions, moving in
    0.1 steps. One step on a 0.4 stock is 25% against a 15% limit, so the
    gate flagged 43 sessions for doing the only thing that price level
    allows — voiding the whole history through the 78-session blackout."""
    df = _dated([0.3, 0.4] * 15)

    assert evaluate_price_limits(df["date"], df["close"], None) == []


def test_two_price_grid_steps_in_one_session_is_still_flagged():
    """Widening the limit to one grid step must not widen it to any move: a
    coarse-grid symbol jumping two steps is still an anomaly."""
    closes = [0.3, 0.4] * 14 + [0.3, 0.5]
    df = _dated(closes)

    flags = evaluate_price_limits(df["date"], df["close"], None)

    assert [(f["date"], f["flag_tier"], f["flag_reason"]) for f in flags] == [
        (df["date"].iloc[-1], FLAG_TIER_HARD, FLAG_REASON_PRICE_LIMIT)
    ]


def test_no_grid_widening_without_enough_history_to_establish_one():
    """A two-row series moving 100 -> 50 would otherwise "establish" a grid
    of 50 and excuse its own anomaly."""
    df = pd.DataFrame({"date": ["2020-01-01", "2020-01-02"], "close": [100.0, 50.0]})

    flags = evaluate_price_limits(df["date"], df["close"], "HSX")

    assert [f["flag_tier"] for f in flags] == [FLAG_TIER_HARD]


def test_grid_widening_leaves_a_high_priced_symbol_untouched():
    """`VHM`'s known-answer case: at 60.30 the limit allows 4.2 against a
    grid of ~0.1, so the 2018-08-14 halving stays hard-flagged."""
    closes = [60.0 + 0.1 * (i % 4) for i in range(28)] + [30.23, 30.3, 30.1]
    df = _dated(closes)

    flags = evaluate_price_limits(df["date"], df["close"], "HSX")

    assert [(f["date"], f["flag_tier"]) for f in flags] == [
        (df["date"].iloc[28], FLAG_TIER_HARD)
    ]


def test_price_grid_step_ignores_a_single_odd_print():
    """A low percentile rather than the outright minimum, because `VKP` has
    exactly one 0.49 close among 0.3/0.4/0.5 — the minimum would read its
    grid as 0.01 and undo the whole correction."""
    closes = pd.Series([0.3, 0.4] * 14 + [0.49, 0.5, 0.4, 0.3])

    assert price_grid_step(closes) == pytest.approx(0.1, abs=0.02)


def test_a_resumption_after_a_long_halt_is_soft_not_hard():
    """A daily limit applies session-over-session, so a months-long halt
    resets the reference price: the move across it is neither a breach nor
    corrupt. Hard-flagging it would neutralise a real return and black out 78
    sessions of valid history."""
    df = pd.DataFrame(
        {"date": ["2020-01-02", "2020-06-30"], "close": [100.0, 50.0]}
    )

    flags = evaluate_price_limits(df["date"], df["close"], "HSX")

    assert [(f["flag_tier"], f["flag_reason"]) for f in flags] == [
        (FLAG_TIER_SOFT, FLAG_REASON_POST_HALT_RESUMPTION)
    ]


def test_an_ordinary_holiday_gap_keeps_the_price_limit_in_force():
    """Tet closes the market ~10 days, and the first session back is still
    limited against the last close before it — so a 50% step there is exactly
    as corrupt as one on consecutive days."""
    df = pd.DataFrame(
        {"date": ["2020-01-22", "2020-02-01"], "close": [100.0, 50.0]}
    )

    flags = evaluate_price_limits(df["date"], df["close"], "HSX")

    assert [(f["flag_tier"], f["flag_reason"]) for f in flags] == [
        (FLAG_TIER_HARD, FLAG_REASON_PRICE_LIMIT)
    ]


def test_a_move_within_limits_after_a_halt_is_not_flagged_at_all():
    """Recording every post-halt session would drown the sidecar; only a move
    the limit would otherwise have caught is worth a note."""
    df = pd.DataFrame(
        {"date": ["2020-01-02", "2020-06-30"], "close": [100.0, 101.0]}
    )

    assert evaluate_price_limits(df["date"], df["close"], "HSX") == []


# --- stale-close fraction (task 3.4) ---


def test_stale_close_fraction_matches_the_screening_script_definition():
    """`(close == close.shift(1)).mean()` — the first row compares against
    NaN and so counts as not-stale."""
    closes = pd.Series([10.0, 10.0, 11.0, 11.0, 11.0])
    assert stale_close_fraction(closes) == pytest.approx(3 / 5)


def test_stale_close_fraction_of_a_never_repeating_series_is_zero():
    assert stale_close_fraction(pd.Series([1.0, 2.0, 3.0])) == 0.0


def test_stale_close_fraction_of_an_empty_series_is_zero():
    assert stale_close_fraction(pd.Series([], dtype="float64")) == 0.0


def test_liquidity_filter_compares_against_the_retained_threshold():
    assert STALE_CLOSE_FRACTION_THRESHOLD == 0.15
    illiquid = pd.DataFrame(
        {"date": [f"2020-01-{d:02d}" for d in range(1, 11)],
         "close": [10.0] * 5 + [11.0] * 5}
    )
    result = run_quality_gate("STALE", illiquid, "HSX")
    assert result["stale_close_fraction"] == pytest.approx(0.8)
    assert result["fails_liquidity_filter"] is True


def test_a_liquid_symbol_does_not_fail_the_filter():
    df = _series_from_moves(100.0, [0.01, -0.01, 0.02, -0.02])
    result = run_quality_gate("LIQUID", df, "HSX")
    assert result["stale_close_fraction"] == 0.0
    assert result["fails_liquidity_filter"] is False


def test_empty_ohlcv_produces_an_empty_result_rather_than_an_error():
    result = run_quality_gate("EMPTY", pd.DataFrame(columns=["date", "close"]), "HSX")
    assert result["flags"] == []
    assert result["hard_flag_count"] == 0
    assert result["stale_close_fraction"] == 0.0


def test_run_quality_gate_counts_each_tier_separately():
    df = _series_from_moves(100.0, [-0.11, 0.0, -0.50, 0.0, 0.005])
    result = run_quality_gate("MIXED", df, "HSX")
    assert result["hard_flag_count"] == 1
    assert result["soft_flag_count"] == 1
    assert len(result["flags"]) == 2


# --- persistence (task 3.5) ---


@pytest.fixture
def gate_db(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.execute(
        "INSERT INTO ticker_universe (symbol, listing_status, updated_at) "
        "VALUES ('MIXED', 'listed', '2026-08-28T00:00:00')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(
        quality_gate, "get_connection", lambda: sqlite3.connect(db_path)
    )
    return db_path


def test_flags_and_liquidity_measurement_are_persisted(gate_db):
    df = _series_from_moves(100.0, [-0.11, 0.0, -0.50])
    persist_quality_gate_result(run_quality_gate("MIXED", df, "HSX"))
    conn = sqlite3.connect(gate_db)
    try:
        flags = conn.execute(
            "SELECT date, flag_tier, limit_exchange, limit_is_unverified_fallback "
            "FROM ohlcv_quality_flags WHERE ticker = 'MIXED' ORDER BY date"
        ).fetchall()
        universe = conn.execute(
            "SELECT stale_close_fraction, fails_liquidity_filter "
            "FROM ticker_universe WHERE symbol = 'MIXED'"
        ).fetchone()
    finally:
        conn.close()
    assert flags == [
        ("2020-01-02", FLAG_TIER_SOFT, "HSX", 1),
        ("2020-01-04", FLAG_TIER_HARD, None, 0),
    ]
    # 1 of this 4-row fixture's sessions repeats its close, so it reads as
    # 25% stale and trips the 15% liquidity threshold. That is an artifact of
    # the fixture's size, not the point of this test — it is asserted so the
    # persisted pair is fully pinned rather than partly.
    assert universe == (pytest.approx(0.25), 1)


def test_only_flagged_rows_reach_the_sidecar(gate_db):
    """Design Decision 4: an expected few hundred rows across the universe,
    not a flag per stored row."""
    df = _series_from_moves(100.0, [0.01] * 20 + [-0.50])
    persist_quality_gate_result(run_quality_gate("MIXED", df, "HSX"))
    conn = sqlite3.connect(gate_db)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM ohlcv_quality_flags"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_a_reload_that_clears_a_violation_clears_its_flag(gate_db):
    """The gate recomputes over the whole history on every load, so a row the
    vendor has since corrected must lose its flag rather than linger."""
    bad = _series_from_moves(100.0, [-0.50])
    persist_quality_gate_result(run_quality_gate("MIXED", bad, "HSX"))
    good = _series_from_moves(100.0, [0.01])
    persist_quality_gate_result(run_quality_gate("MIXED", good, "HSX"))
    conn = sqlite3.connect(gate_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM ohlcv_quality_flags").fetchone()[0] == 0
    finally:
        conn.close()


def test_persisting_for_a_symbol_outside_the_universe_still_records_flags(gate_db):
    """Flags must stay inspectable; the missing universe row is what task
    5.1's backfill exists to resolve."""
    df = _series_from_moves(100.0, [-0.50])
    persist_quality_gate_result(run_quality_gate("NOTINUNIVERSE", df, "HSX"))
    conn = sqlite3.connect(gate_db)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM ohlcv_quality_flags WHERE ticker = 'NOTINUNIVERSE'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_hard_flagged_dates_returns_only_the_hard_tier(gate_db):
    df = _series_from_moves(100.0, [-0.11, 0.0, -0.50])
    persist_quality_gate_result(run_quality_gate("MIXED", df, "HSX"))
    assert hard_flagged_dates("MIXED") == {"2020-01-04"}


def test_persist_writes_through_a_supplied_connection(tmp_path, monkeypatch):
    """tasks.md 5.7: the same hazard `hard_flagged_dates` already guards —
    without a `conn` parameter this opens its own connection to `DB_PATH` and
    writes to the real database even where the caller holds another one."""
    db_path = tmp_path / "other.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.execute(
        "INSERT INTO ticker_universe (symbol, listing_status, updated_at) "
        "VALUES ('X', 'listed', '2026-08-28T00:00:00')"
    )
    conn.commit()

    def fail_if_called():
        raise AssertionError("opened its own connection despite being given one")

    monkeypatch.setattr(quality_gate, "get_connection", fail_if_called)

    df = _series_from_moves(100.0, [-0.50])
    try:
        persist_quality_gate_result(run_quality_gate("X", df, "HSX"), conn)
        assert hard_flagged_dates("X", conn) == {"2020-01-02"}
        # Left open for the caller to close, as `hard_flagged_dates` does.
        assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        conn.close()


def test_hard_flagged_dates_reads_through_a_supplied_connection(tmp_path):
    """Callers holding a connection must be able to pass it, or this would
    read the real database instead of theirs."""
    db_path = tmp_path / "other.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.execute(
        "INSERT INTO ohlcv_quality_flags (ticker, date, flag_tier, log_return, "
        "limit_is_unverified_fallback, flagged_at) "
        "VALUES ('X', '2021-05-05', 'hard', -0.7, 0, '2026-08-28T00:00:00')"
    )
    conn.commit()
    try:
        assert hard_flagged_dates("X", conn) == {"2021-05-05"}
    finally:
        conn.close()


# --- neutralisation (task 3.6) ---


def test_neutralise_nulls_the_return_at_a_flagged_date():
    dates = ["2020-01-01", "2020-01-02", "2020-01-03"]
    returns = pd.Series([np.nan, -0.5, 0.01])
    out = neutralise_hard_flagged_returns(dates, returns, {"2020-01-02"})
    assert pd.isna(out.iloc[1])
    assert out.iloc[2] == pytest.approx(0.01)


def test_neutralise_leaves_a_clean_series_untouched():
    dates = ["2020-01-01", "2020-01-02"]
    returns = pd.Series([np.nan, 0.01])
    out = neutralise_hard_flagged_returns(dates, returns, set())
    pd.testing.assert_series_equal(out, returns)


def test_neutralise_keeps_one_bad_return_out_of_the_standard_deviation():
    """A ~50% step inside a 60-session window inflates its standard deviation
    roughly tenfold, which would drive every Advice in that window to HOLD."""
    dates = [f"2020-{m:02d}-01" for m in range(1, 13)]
    returns = pd.Series([np.nan] + [0.01] * 5 + [-0.5] + [0.01] * 5)
    polluted = returns.dropna().std()
    clean = neutralise_hard_flagged_returns(dates, returns, {dates[6]}).dropna().std()
    assert polluted > 10 * max(clean, 1e-12)
    assert clean == pytest.approx(0.0, abs=1e-12)
