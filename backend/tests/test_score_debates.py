"""Tests for `backend/scripts/score_debates.py` (`debate-outcome-log`, task groups 4-5).

The script lives under `backend/scripts/`, which is not a package, so it is loaded
by path (the precedent in `test_evaluate_cross_sectional_momentum.py`).
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.db.debate_log import CREATE_DEBATE_LOG_TABLE
from app.db.schema import CREATE_TICKER_UNIVERSE_TABLE

BACKEND = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("score_debates", BACKEND / "scripts" / "score_debates.py")
sd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sd)


def day(n: int) -> str:
    """Session n of a synthetic calendar (the script derives the calendar from the data)."""
    return f"2026-09-{n:02d}"


@pytest.fixture()
def dbs(tmp_path):
    app, log = tmp_path / "app.db", tmp_path / "debate_log.db"
    conn = sqlite3.connect(app)
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, close REAL)")
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    conn.commit()
    conn.close()
    conn = sqlite3.connect(log)
    conn.execute(CREATE_DEBATE_LOG_TABLE)
    conn.commit()
    conn.close()
    return {"app": app, "log": log}


def add_bars(dbs, ticker: str, bars: dict[int, float]) -> None:
    conn = sqlite3.connect(dbs["app"])
    conn.executemany("INSERT INTO ohlcv VALUES (?, ?, ?)", [(ticker, day(d), c) for d, c in bars.items()])
    conn.commit()
    conn.close()


def add_row(dbs, **fields) -> int:
    row = {
        "ticker": "VCB", "as_of": day(1), "run_at": "2026-09-01T10:00:00+00:00", "eligible": 1,
        "eligibility_reasons": "[]", "agents_degraded": "[]", "data_age_sessions": 0,
        "close_at_asof": 100.0, "range_5s_pct": 5.0, "range_coverage": 0.68, "range_k": 1.3,
        "verdict": "BUY_SIGNAL", "agreement_level": "majority",
        "r1_technical": "bull", "r1_news": "bull", "r1_macro": "neutral",
        "r2_technical": "bull", "r2_news": "bull", "r2_macro": "neutral",
    }
    row.update(fields)
    conn = sqlite3.connect(dbs["log"])
    cursor = conn.execute(
        f"INSERT INTO debate_log ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", list(row.values())
    )
    conn.commit()
    conn.close()
    return cursor.lastrowid


def calendar_through(dbs, last_day: int) -> None:
    """A market ticker that trades every session: it fixes the calendar."""
    add_bars(dbs, "MKT", {d: 50.0 for d in range(1, last_day + 1)})


def run_scoring(dbs, **kwargs):
    app, log = sd.open_app_db(dbs["app"]), sd.open_log_db(dbs["log"])
    try:
        return sd.score_pending(app, log, **kwargs)
    finally:
        app.close()
        log.close()


def fetch(dbs, row_id: int) -> dict:
    conn = sqlite3.connect(dbs["log"])
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM debate_log WHERE id = ?", (row_id,)).fetchone())
    finally:
        conn.close()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- 4.1: readiness is the fifth market session ---

def test_a_row_is_not_scored_with_only_four_later_sessions(dbs):
    calendar_through(dbs, 5)  # sessions 1..5: only four after as_of
    add_bars(dbs, "VCB", {d: 100.0 for d in range(1, 6)})
    row_id = add_row(dbs)

    summary = run_scoring(dbs)

    assert fetch(dbs, row_id)["outcome_status"] is None
    assert summary["scored"] == 0 and summary["pending"] == 1


def test_a_row_is_scored_with_the_fifth_session_and_every_field_is_exact(dbs):
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {1: 100.0, 2: 101.0, 3: 99.0, 4: 100.0, 5: 102.0, 6: 103.0, 7: 104.0})
    row_id = add_row(dbs, range_5s_pct=5.0, verdict="BUY_SIGNAL")

    summary = run_scoring(dbs)
    row = fetch(dbs, row_id)

    assert summary["scored"] == 1
    assert row["outcome_status"] == "scored" and row["date_t5"] == day(6)
    assert row["close_asof_at_scoring"] == 100.0 and row["close_t5"] == 103.0
    assert row["r5"] == pytest.approx(math.log(1.03))
    assert row["inside_band"] == 1 and row["direction_hit"] == 1
    assert row["scored_at"] is not None


def test_a_ticker_that_skipped_the_fifth_session_is_void_gap(dbs):
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {1: 100.0, 2: 100.0, 3: 100.0, 4: 100.0, 5: 100.0, 7: 110.0})  # no bar on 6
    row_id = add_row(dbs)

    summary = run_scoring(dbs)

    assert fetch(dbs, row_id)["outcome_status"] == "void_gap" and summary["void_gap"] == 1
    assert fetch(dbs, row_id)["r5"] is None


def test_a_ticker_with_no_later_bar_stays_pending_and_is_listed_for_refresh(dbs):
    calendar_through(dbs, 6)
    add_bars(dbs, "VCB", {d: 100.0 for d in range(1, 6)})  # not refreshed past session 5
    row_id = add_row(dbs)

    summary = run_scoring(dbs)

    assert fetch(dbs, row_id)["outcome_status"] is None
    assert summary["refresh"] == ["VCB"]


def test_a_fifth_session_bar_with_nothing_after_it_may_be_provisional_and_is_not_scored(dbs):
    calendar_through(dbs, 7)  # the market moved on, but VCB was pulled mid-session 6 and not since
    add_bars(dbs, "VCB", {d: 100.0 for d in range(1, 7)})
    row_id = add_row(dbs)

    summary = run_scoring(dbs)

    assert fetch(dbs, row_id)["outcome_status"] is None
    assert summary["scored"] == 0 and summary["refresh"] == ["VCB"]


def test_the_row_is_scored_once_the_ticker_has_a_bar_after_its_fifth_session(dbs):
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {d: 100.0 for d in range(1, 7)})
    row_id = add_row(dbs)
    run_scoring(dbs)
    assert fetch(dbs, row_id)["outcome_status"] is None

    add_bars(dbs, "VCB", {7: 100.0})  # refreshed after session 7 closed

    assert run_scoring(dbs)["scored"] == 1 and fetch(dbs, row_id)["outcome_status"] == "scored"


def test_a_missing_as_of_bar_is_void_no_bar(dbs):
    calendar_through(dbs, 6)
    add_bars(dbs, "VCB", {d: 100.0 for d in range(2, 7)})  # nothing on as_of (session 1)
    row_id = add_row(dbs)

    run_scoring(dbs)

    assert fetch(dbs, row_id)["outcome_status"] == "void_no_bar"


@pytest.mark.parametrize("bad_close", [0.0, -3.0])
def test_a_non_positive_close_is_void_no_bar(dbs, bad_close):
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {1: bad_close, 2: 100.0, 3: 100.0, 4: 100.0, 5: 100.0, 6: 100.0, 7: 100.0})
    row_id = add_row(dbs)

    run_scoring(dbs)

    assert fetch(dbs, row_id)["outcome_status"] == "void_no_bar"


def test_readiness_does_not_depend_on_the_system_clock(dbs, monkeypatch):
    class FarFuture:
        @staticmethod
        def now(tz=None):
            from datetime import datetime

            return datetime(2099, 1, 1, tzinfo=tz)

    monkeypatch.setattr(sd, "datetime", FarFuture)
    calendar_through(dbs, 5)
    add_bars(dbs, "VCB", {d: 100.0 for d in range(1, 6)})
    row_id = add_row(dbs)

    run_scoring(dbs)

    assert fetch(dbs, row_id)["outcome_status"] is None


def test_the_script_imports_no_vnstock_module():
    code = (
        "import importlib.util, sys;"
        f"s = importlib.util.spec_from_file_location('sd', r'{BACKEND / 'scripts' / 'score_debates.py'}');"
        "m = importlib.util.module_from_spec(s); s.loader.exec_module(m);"
        "bad = [n for n in sys.modules if n.split('.')[0] in ('vnstock', 'vnai', 'requests', 'httpx')];"
        "assert not bad, bad"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_a_scoring_run_opens_no_socket(dbs, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("scoring must work offline")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {d: 100.0 for d in range(1, 8)})
    add_row(dbs)

    assert run_scoring(dbs)["scored"] == 1


# --- 4.2: read-only app.db, idempotent, dry run ---

def test_app_db_is_opened_read_only(dbs):
    conn = sd.open_app_db(dbs["app"])
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO ohlcv VALUES ('X', 'd', 1.0)")
    conn.close()


def test_app_db_is_byte_identical_after_a_scoring_run(dbs):
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {d: 100.0 for d in range(1, 8)})
    add_row(dbs)
    before = sha(dbs["app"])

    run_scoring(dbs)

    assert sha(dbs["app"]) == before


def test_a_second_run_changes_no_row_and_scores_nothing(dbs):
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {d: 100.0 + d for d in range(1, 8)})
    row_id = add_row(dbs)
    run_scoring(dbs)
    first = fetch(dbs, row_id)

    summary = run_scoring(dbs)

    assert summary["scored"] == 0 and fetch(dbs, row_id) == first


def test_dry_run_writes_nothing(dbs):
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {d: 100.0 for d in range(1, 8)})
    row_id = add_row(dbs)
    before = sha(dbs["log"])

    summary = run_scoring(dbs, dry_run=True)

    assert summary["scored"] == 1  # reported as what it would score
    assert sha(dbs["log"]) == before and fetch(dbs, row_id)["outcome_status"] is None


def test_a_scored_row_is_never_rewritten_even_if_ohlcv_later_changes(dbs):
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {d: 100.0 for d in range(1, 8)})
    row_id = add_row(dbs)
    run_scoring(dbs)
    first = fetch(dbs, row_id)
    conn = sqlite3.connect(dbs["app"])
    conn.execute("UPDATE ohlcv SET close = 150.0 WHERE ticker = 'VCB'")
    conn.commit()
    conn.close()

    run_scoring(dbs)

    assert fetch(dbs, row_id) == first


# --- 4.3: outcome definitions ---

def test_a_zero_return_is_a_miss(dbs):
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {d: 100.0 for d in range(1, 8)})
    row_id = add_row(dbs, verdict="BUY_SIGNAL")

    run_scoring(dbs)

    row = fetch(dbs, row_id)
    assert row["r5"] == 0 and row["direction_hit"] == 0


@pytest.mark.parametrize("verdict", ["OBSERVE", "SPLIT", "INSUFFICIENT_DATA"])
def test_non_directional_verdicts_have_no_direction_hit(verdict):
    assert sd.direction_hit(verdict, 0.05) is None and sd.direction_hit(verdict, -0.05) is None


@pytest.mark.parametrize(
    "verdict, r5, expected",
    [
        ("STRONG_BUY_SIGNAL", 0.01, 1), ("BUY_SIGNAL", -0.01, 0),
        ("CAUTION_SIGNAL", -0.01, 1), ("STRONG_CAUTION_SIGNAL", 0.01, 0),
        ("CAUTION_SIGNAL", 0.0, 0),
    ],
)
def test_direction_hit_keys_on_enum_values(verdict, r5, expected):
    assert sd.direction_hit(verdict, r5) == expected


def test_a_display_label_is_not_a_verdict():
    assert sd.direction_hit("Buy signal", 0.05) is None and sd.direction_hit("Caution", -0.05) is None


def test_inside_band_compares_percent_against_percent():
    r5 = math.log(1.03)  # a 3% move
    assert sd.inside_band(r5, 3.1) == 1 and sd.inside_band(r5, 2.9) == 0
    assert sd.inside_band(-r5, 3.1) == 1  # the band is symmetric
    assert sd.inside_band(r5, None) is None


def test_a_logged_close_off_by_a_third_of_a_percent_is_scored_on_current_closes_and_counted(dbs):
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {1: 100.0, 2: 100.0, 3: 100.0, 4: 100.0, 5: 100.0, 6: 103.0, 7: 103.0})
    # logged 100.3 (a later pull revised it to 100.0); band 2.8%: 3.0% is outside, 2.7% inside
    row_id = add_row(dbs, close_at_asof=100.3, range_5s_pct=2.9)

    run_scoring(dbs)
    row = fetch(dbs, row_id)
    log = sd.open_log_db(dbs["log"])
    revised = sd.revision_counts(log)
    log.close()

    assert row["close_asof_at_scoring"] == 100.0 and row["r5"] == pytest.approx(math.log(1.03))
    assert row["inside_band"] == 0  # 2.96% > 2.9%
    assert revised == {"revised": 1, "would_change_inside_band": 1}  # on the logged close it is 2.66%


# ===========================================================================
# Report (task group 5)
# ===========================================================================

import os  # noqa: E402
from datetime import datetime, timezone  # noqa: E402



def scored(dbs, *, r5: float, **fields) -> int:
    """A scored, eligible, healthy row on its own ticker unless `ticker`/`as_of` say otherwise."""
    fields.setdefault("ticker", f"T{add_row.counter}")
    add_row.counter += 1
    fields.setdefault("inside_band", sd.inside_band(r5, fields.get("range_5s_pct", 5.0)))
    fields.setdefault("direction_hit", sd.direction_hit(fields.get("verdict", "BUY_SIGNAL"), r5))
    return add_row(dbs, outcome_status="scored", r5=r5, date_t5=day(6), close_asof_at_scoring=100.0,
                   close_t5=100.0 * math.exp(r5), scored_at="2026-09-10T00:00:00+00:00", **fields)


add_row.counter = 0


def log_rows(dbs):
    log = sd.open_log_db(dbs["log"])
    try:
        return sd.load_log_rows(log)
    finally:
        log.close()


# --- 5.1: the analysed population and the funnel ---

def test_the_analysed_population_excludes_everything_it_should_and_the_funnel_adds_up(dbs):
    add_row(dbs, ticker="A", eligible=0, outcome_status="scored", r5=0.01)  # ineligible
    add_row(dbs, ticker="B", agents_degraded='["news"]', outcome_status="scored", r5=0.01)  # degraded
    add_row(dbs, ticker="C", outcome_status="void_gap")  # void
    add_row(dbs, ticker="D")  # pending
    scored(dbs, ticker="E", r5=0.01, data_age_sessions=20)  # age-excluded
    scored(dbs, ticker="F", r5=0.01, verdict="BUY_SIGNAL")  # analysed: first run of its pair
    scored(dbs, ticker="F", r5=0.01, verdict="CAUTION_SIGNAL")  # a repeat that disagrees
    scored(dbs, ticker="G", r5=0.01)  # analysed
    scored(dbs, ticker="H", r5=0.01, data_age_sessions=None)  # unknown age is excluded

    analysed, funnel = sd.population(log_rows(dbs), max_age=0)

    assert [(r["ticker"], r["verdict"]) for r in analysed] == [("F", "BUY_SIGNAL"), ("G", "BUY_SIGNAL")]
    assert funnel["logged"] == 9
    assert (funnel["ineligible"], funnel["degraded"], funnel["void"], funnel["pending"]) == (1, 1, 1, 1)
    assert (funnel["age_excluded"], funnel["repeats_dropped"], funnel["analysed"]) == (2, 1, 2)
    assert funnel["logged"] == sum(
        funnel[k] for k in ("ineligible", "degraded", "void", "pending", "age_excluded", "repeats_dropped", "analysed")
    )
    assert (funnel["pairs_repeated"], funnel["pairs_disagreed"]) == (1, 1)


def test_the_age_guard_is_a_parameter(dbs):
    scored(dbs, r5=0.01, data_age_sessions=3)
    assert len(sd.population(log_rows(dbs), max_age=0)[0]) == 0
    assert len(sd.population(log_rows(dbs), max_age=3)[0]) == 1


# --- 5.2: coverage, directional hit-rates, per-agent, baselines ---

@pytest.fixture()
def five_rows(dbs):
    """r5 (log) of 2, -6, 4, -1, 3 percent; band 5% from range_k 2; one row per day."""
    spec = [
        (0.02, "BUY_SIGNAL"), (-0.06, "BUY_SIGNAL"), (0.04, "CAUTION_SIGNAL"),
        (-0.01, "STRONG_CAUTION_SIGNAL"), (0.03, "OBSERVE"),
    ]
    for i, (r5, verdict) in enumerate(spec, start=1):
        scored(dbs, r5=r5, verdict=verdict, as_of=day(i), range_5s_pct=5.0, range_k=2.0, range_coverage=0.7)
    analysed, _ = sd.population(log_rows(dbs), max_age=0)
    for r in analysed:
        r["block"], r["market_r5"] = 0, None
    return analysed


def test_coverage_at_the_band_with_k_divided_out_and_the_median_ratio(five_rows):
    stats = sd.coverage_stats(five_rows)

    assert (stats["inside"], stats["n"]) == (4, 5)  # |6| is the one outside 5
    assert stats["inside_without_k"] == 2  # band 2.5: only 2 and 1 are inside
    assert stats["mean_nominal"] == pytest.approx(0.7)
    assert stats["median_ratio"] == pytest.approx(0.6)  # ratios .4 1.2 .8 .2 .6


def test_directional_hit_rate_base_rate_and_edge(five_rows):
    table = sd.directional_stats(five_rows, sd.verdict_lean)

    assert (sum(table["bull"]["hits"]), len(table["bull"]["hits"])) == (1, 2)
    assert (sum(table["bear"]["hits"]), len(table["bear"]["hits"])) == (1, 2)
    assert table["bull"]["base"] == pytest.approx(0.6)  # 3 of 5 rows went up
    assert table["bear"]["base"] == pytest.approx(0.4)  # 2 of 5 went down
    assert "OBSERVE" not in str(table)


def test_the_per_agent_tables_skip_neutral_stances_and_separate_the_rounds(dbs):
    scored(dbs, r5=0.02, r1_news="bull", r2_news="neutral")
    scored(dbs, r5=-0.02, r1_news="bull", r2_news="bear")
    scored(dbs, r5=0.02, r1_news="neutral", r2_news="bull")
    analysed, _ = sd.population(log_rows(dbs), max_age=0)
    for r in analysed:
        r["block"], r["market_r5"] = 0, None

    round1 = sd.directional_stats(analysed, sd.stance_lean("r1_news"))
    round2 = sd.directional_stats(analysed, sd.stance_lean("r2_news"))

    assert round1["bull"]["hits"] == [1, 0] and "bear" not in round1
    assert round2["bull"]["hits"] == [1] and round2["bear"]["hits"] == [1]


def test_verdict_minus_technical_only_on_the_same_rows(dbs):
    # verdict and technical both directional on rows 1-3; row 4 has a neutral technical vote
    scored(dbs, r5=0.02, verdict="BUY_SIGNAL", r1_technical="bull")  # both hit
    scored(dbs, r5=-0.02, verdict="BUY_SIGNAL", r1_technical="bear")  # verdict miss, technical hit
    scored(dbs, r5=0.02, verdict="CAUTION_SIGNAL", r1_technical="bear")  # both miss
    scored(dbs, r5=0.02, verdict="BUY_SIGNAL", r1_technical="neutral")  # not comparable
    analysed, _ = sd.population(log_rows(dbs), max_age=0)

    result = sd.verdict_vs_technical(analysed)

    assert result["n"] == 3
    assert result["verdict"] == pytest.approx(1 / 3) and result["technical"] == pytest.approx(2 / 3)
    assert result["difference"] == pytest.approx(-1 / 3)


def _universe(dbs, tickers, *, ok=True):
    conn = sqlite3.connect(dbs["app"])
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    for t in tickers:
        conn.execute(
            "INSERT INTO ticker_universe (symbol, listing_status, ingestion_state, fails_liquidity_filter, "
            "below_minimum_history, updated_at) VALUES (?, 'listed', ?, 0, 0, 'x')",
            (t, "ok" if ok else "pending"),
        )
    conn.commit()
    conn.close()


def test_the_market_baseline_is_unavailable_below_thirty_tickers_and_correct_above(dbs):
    names = [f"M{i:02d}" for i in range(30)]
    for t in names:
        add_bars(dbs, t, {1: 100.0, 6: 102.0})
    _universe(dbs, names[:29])  # 29 in the universe: not enough
    app = sd.open_app_db(dbs["app"])
    assert sd.market_r5(app, day(1), day(6)) is None
    app.close()

    _universe_rows = sqlite3.connect(dbs["app"])
    _universe_rows.execute(
        "INSERT INTO ticker_universe (symbol, listing_status, ingestion_state, fails_liquidity_filter, "
        "below_minimum_history, updated_at) VALUES (?, 'listed', 'ok', 0, 0, 'x')", (names[29],))
    _universe_rows.commit()
    _universe_rows.close()
    app = sd.open_app_db(dbs["app"])
    assert sd.market_r5(app, day(1), day(6)) == pytest.approx(math.log(1.02))
    app.close()


def test_a_ticker_outside_the_modelling_universe_is_not_in_the_market_mean(dbs):
    names = [f"M{i:02d}" for i in range(30)]
    for t in names:
        add_bars(dbs, t, {1: 100.0, 6: 102.0})
    add_bars(dbs, "ODD", {1: 100.0, 6: 200.0})  # not in the universe
    _universe(dbs, names)
    app = sd.open_app_db(dbs["app"])
    assert sd.market_r5(app, day(1), day(6)) == pytest.approx(math.log(1.02))
    app.close()


def test_the_demeaned_test_scores_the_excess_over_the_market(five_rows):
    for r in five_rows:
        r["market_r5"] = 0.03  # every row's excess is r5 - 3%
    table = sd.directional_stats(five_rows, sd.verdict_lean, demean=True)

    # excess: -1, -9, +1, -4, 0 (percent). bull verdicts: rows 1-2 -> 0 hits; bear: rows 3-4 -> 1 hit
    assert sum(table["bull"]["hits"]) == 0 and sum(table["bear"]["hits"]) == 1
    assert table["bull"]["base"] == pytest.approx(1 / 5)  # only row 3 beat the market


# --- 5.3: the effective sample size ---

def test_wilson_interval_against_a_known_value():
    low, high = sd.wilson(50, 100)
    assert low == pytest.approx(0.4038, abs=1e-3) and high == pytest.approx(0.5962, abs=1e-3)


def test_the_bootstrap_is_withheld_below_eight_blocks():
    assert sd.block_bootstrap([1, 0] * 20, [i // 8 for i in range(40)]) is None  # 5 blocks


def test_the_bootstrap_is_reproducible_and_reports_a_smaller_effective_n_when_clustered():
    # 10 blocks of 20 rows; whole blocks hit or miss together: heavy clustering
    hits = [int(b % 2 == 0) for b in range(10) for _ in range(20)]
    blocks = [b for b in range(10) for _ in range(20)]

    first, second = sd.block_bootstrap(hits, blocks), sd.block_bootstrap(hits, blocks)

    assert first == second
    half_width, effective_n = first
    assert half_width > 0.2 and effective_n < 20  # 200 rows, about 4 independent bets


def test_a_report_with_many_tickers_on_few_dates_prints_the_counts_and_no_false_sample_size(dbs):
    for t in range(25):
        for d in range(1, 9):  # 25 tickers x 8 dates = 200 rows, all inside one block
            scored(dbs, r5=0.01 if (t + d) % 2 else -0.01, ticker=f"T{t:02d}", as_of=day(d),
                   verdict="BUY_SIGNAL")
    calendar_through(dbs, 12)

    text = build(dbs)

    assert "200 rows" in text and "25 tickers" in text and "8 as_of dates" in text and "1 block" in text
    assert "clustered interval not estimable: 1 blocks (need 8)" in text
    assert "effective n: not estimable" in text and "not a sample size" in text


def test_few_blocks_prints_the_wilson_interval_and_the_stated_message(dbs):
    for d in range(1, 4):
        scored(dbs, r5=0.01, as_of=day(d), verdict="BUY_SIGNAL")
    calendar_through(dbs, 12)

    text = build(dbs)

    assert "Wilson" in text and "clustered interval not estimable: 1 blocks (need 8)" in text


def build(dbs, summary=None, reports_dir=None, max_age=0) -> str:
    app, log = sd.open_app_db(dbs["app"]), sd.open_log_db(dbs["log"])
    try:
        return sd.build_report(app, log, summary or {"refresh": []}, max_age, reports_dir)
    finally:
        app.close()
        log.close()


def test_the_report_never_prints_a_rate_without_its_n_and_uses_percentages(dbs):
    for d in range(1, 6):
        scored(dbs, r5=0.02 if d % 2 else -0.02, as_of=day(d), verdict="BUY_SIGNAL",
               r1_technical="bull", r2_technical="bull", r1_news="bear", r2_news="bear")
    calendar_through(dbs, 12)

    text = build(dbs)

    for line in text.splitlines():
        if "%" in line:
            assert "n=" in line or "n =" in line, line
    assert "log return" not in text.lower() and "r5" not in text
    assert "about 384" in text and "chose to analyse" in text


# --- 5.4: cross-checks and no backfill ---

def _touch(path: Path, when: datetime) -> None:
    path.write_text("# report")
    os.utime(path, (when.timestamp(), when.timestamp()))


def test_report_files_newer_than_the_first_run_without_a_row_are_listed_older_ones_ignored(dbs, tmp_path):
    add_row(dbs, ticker="VCB", as_of=day(1), run_at="2026-09-10T00:00:00+00:00")
    reports = tmp_path / "reports"
    reports.mkdir()
    _touch(reports / "2026-09-01_OLD.md", datetime(2026, 9, 5, tzinfo=timezone.utc))  # before the first run
    _touch(reports / "2026-09-02_LOST.md", datetime(2026, 9, 11, tzinfo=timezone.utc))  # no row
    _touch(reports / f"{day(1)}_VCB.md", datetime(2026, 9, 11, tzinfo=timezone.utc))  # has a row
    log = sd.open_log_db(dbs["log"])

    listed = sd.possible_failed_writes(log, reports)
    log.close()

    assert listed == ["2026-09-02_LOST.md"]


def test_reports_never_create_rows(dbs, tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    _touch(reports / "2026-09-02_LOST.md", datetime(2026, 9, 11, tzinfo=timezone.utc))
    calendar_through(dbs, 3)

    build(dbs, reports_dir=reports)

    assert log_rows(dbs) == []


def test_tickers_to_refresh_appear_in_the_report(dbs):
    scored(dbs, r5=0.01)
    calendar_through(dbs, 3)

    assert "VCB, ZZZ" in build(dbs, summary={"refresh": ["VCB", "ZZZ"]})


# --- review fixes ---

def test_a_ticker_with_no_bars_at_all_waits_for_a_refresh_instead_of_voiding(dbs):
    calendar_through(dbs, 6)  # the market has its fifth session; VCB has no bars (app.db rebuilt)
    row_id = add_row(dbs)

    summary = run_scoring(dbs)

    assert fetch(dbs, row_id)["outcome_status"] is None and summary["refresh"] == ["VCB"]


def test_the_update_guard_alone_protects_a_scored_row(dbs):
    calendar_through(dbs, 7)
    add_bars(dbs, "VCB", {d: 100.0 for d in range(1, 8)})
    row_id = add_row(dbs)
    run_scoring(dbs)
    first = fetch(dbs, row_id)

    log = sd.open_log_db(dbs["log"])
    cursor = log.execute(sd.UPDATE_OUTCOME, ("void_gap", "x", None, None, None, None, None, None, row_id))
    log.commit()
    log.close()

    assert cursor.rowcount == 0 and fetch(dbs, row_id) == first


def test_a_withheld_bootstrap_with_enough_blocks_says_why(dbs):
    # 8 blocks, every call a hit: no variance to resample, but not a block-count problem
    for b in range(8):
        scored(dbs, r5=0.01, as_of=day(1 + b), verdict="BUY_SIGNAL")
    calendar_through(dbs, 3)
    rows = log_rows(dbs)
    line = sd.rate_line("hit", [1] * 8, list(range(8)))

    assert "no variance" in line and "blocks (need" not in line and len(rows) == 8
