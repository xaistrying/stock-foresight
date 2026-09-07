"""Tests for the batch ingestion layer (hose-universe-ingestion, group 6).

The point of most of these is what a 634-symbol run must survive: a rate
limit mid-run, a symbol that raises, an interrupt — none of which may cost
the run the symbols it already finished.
"""

import json
import sqlite3

import pytest

import app.services.bulk_ingestion as bulk_ingestion
import app.services.ticker_universe as ticker_universe
from app.db.schema import CREATE_TICKER_UNIVERSE_TABLE
from app.services.bulk_ingestion import (
    ingest_symbol,
    run_batch,
    summarise,
    symbols_to_ingest,
    write_run_summary,
)
from app.services.ticker_universe import (
    INGESTION_STATE_FAILED,
    INGESTION_STATE_OK,
    INGESTION_STATE_PENDING,
    last_session_spread,
)


def _universe_row(conn, symbol, *, status="listed", state=INGESTION_STATE_PENDING,
                  last_session=None):
    conn.execute(
        "INSERT INTO ticker_universe (symbol, exchange, listing_status, "
        "ingestion_state, last_observed_session, updated_at) "
        "VALUES (?, 'HSX', ?, ?, ?, '2026-08-28T00:00:00')",
        (symbol, status, state, last_session),
    )


@pytest.fixture
def universe_db(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    conn.commit()
    conn.close()
    connect = lambda: sqlite3.connect(db_path)  # noqa: E731
    monkeypatch.setattr(bulk_ingestion, "get_connection", connect)
    monkeypatch.setattr(ticker_universe, "get_connection", connect)
    return db_path


def _ok_result(rows=100, **overrides):
    result = {
        "rows_loaded": rows,
        "available_since": "2018-01-02",
        "possibly_truncated_by_tier": False,
        "features_computed": True,
        "status": "ok",
        "hard_flag_count": 0,
        "soft_flag_count": 0,
        "stale_close_fraction": 0.01,
        "fails_liquidity_filter": False,
    }
    result.update(overrides)
    return result


def _failed_result(status):
    return {
        "rows_loaded": 0,
        "available_since": None,
        "possibly_truncated_by_tier": None,
        "features_computed": None,
        "status": status,
    }


# --- symbol selection and resumability (tasks 6.3, 6.9) ---


def test_selection_skips_already_ingested_symbols_by_default(universe_db):
    """Resumability comes from the universe row's own state, so an
    interrupted run needs no checkpoint file (task 6.3)."""
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "AAA", state=INGESTION_STATE_OK)
    _universe_row(conn, "BBB", state=INGESTION_STATE_PENDING)
    _universe_row(conn, "CCC", state=INGESTION_STATE_FAILED)
    conn.commit()
    conn.close()

    assert symbols_to_ingest() == ["BBB", "CCC"]


def test_selection_can_include_already_ingested_symbols(universe_db):
    """Task 6.9: the first full run must refresh the 15 already-ingested
    tickers rather than leaving their last sessions weeks behind the rest."""
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "AAA", state=INGESTION_STATE_OK)
    _universe_row(conn, "BBB", state=INGESTION_STATE_PENDING)
    conn.commit()
    conn.close()

    assert symbols_to_ingest(include_ingested=True) == ["AAA", "BBB"]


def test_selection_filters_by_listing_status_and_limit(universe_db):
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "AAA")
    _universe_row(conn, "BBB")
    _universe_row(conn, "ZZZ", status="delisted")
    conn.commit()
    conn.close()

    assert symbols_to_ingest(listing_status="delisted") == ["ZZZ"]
    # Deterministic order, so a dry run over a subset is reproducible.
    assert symbols_to_ingest(limit=1) == ["AAA"]


# --- per-symbol behaviour (tasks 6.2, 6.4) ---


def test_rate_limit_waits_and_retries_the_same_symbol(universe_db, monkeypatch):
    """`load_ticker` swallows RateLimitError and reports it as a status, so
    retrying is the only way the symbol is not silently lost (task 6.2)."""
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "AAA")
    conn.commit()
    conn.close()

    attempts = []
    results = [_failed_result("rate_limited"), _ok_result()]

    def fake_load(symbol, timings=None):
        attempts.append(symbol)
        return results[len(attempts) - 1]

    slept = []
    monkeypatch.setattr(bulk_ingestion, "load_ticker", fake_load)

    outcome = ingest_symbol("AAA", rate_limit_wait=7.0, sleep=slept.append)

    assert attempts == ["AAA", "AAA"]
    assert slept == [7.0]
    assert outcome["status"] == "ok"
    assert outcome["rate_limit_waits"] == 1


def test_rate_limit_gives_up_after_the_wait_cap(universe_db, monkeypatch):
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "AAA")
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        bulk_ingestion, "load_ticker",
        lambda symbol, timings=None: _failed_result("rate_limited"),
    )

    outcome = ingest_symbol(
        "AAA", rate_limit_wait=1.0, max_rate_limit_waits=2, sleep=lambda _: None
    )

    assert outcome["status"] == "rate_limited"
    assert outcome["rate_limit_waits"] == 2
    # The status itself is the recorded state, so a resumed run can tell a
    # throttled symbol (retry) from a `no_data` one (do not bother) — which a
    # single `failed` state cannot express (docs/DATA_DICTIONARY.md).
    conn = sqlite3.connect(universe_db)
    try:
        state, error = conn.execute(
            "SELECT ingestion_state, ingestion_last_error FROM ticker_universe "
            "WHERE symbol = 'AAA'"
        ).fetchone()
    finally:
        conn.close()
    assert state == "rate_limited"
    assert error == "rate_limited"
    assert symbols_to_ingest() == ["AAA"], "a throttled symbol must be retried"


def test_a_permanent_failure_is_not_retried_by_default(universe_db, monkeypatch):
    """A rate-limited call spent rediscovering a known `no_data` symbol is a
    call not spent on one that might succeed — and 229 of the 634 are
    delisted names where `no_data` is plausible (task 6.3)."""
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "GONE")
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        bulk_ingestion, "load_ticker",
        lambda symbol, timings=None: _failed_result("no_data"),
    )

    ingest_symbol("GONE")

    assert symbols_to_ingest() == []
    assert symbols_to_ingest(retry_permanent_failures=True) == ["GONE"]


def test_a_rate_limit_exit_is_waited_out_not_fatal(universe_db, monkeypatch):
    """vnai's limiter calls `sys.exit` from a context manager
    (`vnai/beam/quota.py:313`), so the rate limit arrives as `SystemExit` —
    a BaseException that `except Exception` does not catch. The first full
    run died at symbol 12 of 634 this way."""
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "AAA")
    conn.commit()
    conn.close()

    attempts = []

    def fake_load(symbol, timings=None):
        attempts.append(symbol)
        if len(attempts) == 1:
            raise SystemExit(
                "Rate limit exceeded. Bạn đã đạt giới hạn. Process terminated."
            )
        return _ok_result()

    slept = []
    monkeypatch.setattr(bulk_ingestion, "load_ticker", fake_load)

    outcome = ingest_symbol("AAA", rate_limit_wait=9.0, sleep=slept.append)

    assert attempts == ["AAA", "AAA"]
    assert slept == [9.0]
    assert outcome["status"] == "ok"
    assert outcome["rate_limit_waits"] == 1


def test_a_genuine_system_exit_is_not_swallowed(universe_db, monkeypatch):
    """Catching every `SystemExit` would make the batch unkillable."""
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "AAA")
    conn.commit()
    conn.close()

    def fake_load(symbol, timings=None):
        raise SystemExit("interpreter is going down")

    monkeypatch.setattr(bulk_ingestion, "load_ticker", fake_load)

    with pytest.raises(SystemExit):
        ingest_symbol("AAA", sleep=lambda _: None)


def test_a_rate_limit_exit_stops_retrying_at_the_cap(universe_db, monkeypatch):
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "AAA")
    conn.commit()
    conn.close()

    def always_limited(symbol, timings=None):
        raise SystemExit("Rate limit exceeded. Process terminated.")

    monkeypatch.setattr(bulk_ingestion, "load_ticker", always_limited)

    outcome = ingest_symbol(
        "AAA", rate_limit_wait=1.0, max_rate_limit_waits=2, sleep=lambda _: None
    )

    assert outcome["status"] == "rate_limited"
    assert outcome["rate_limit_waits"] == 2
    # Recorded so a resume retries it — the symbol was never actually read.
    assert symbols_to_ingest() == ["AAA"]


def test_an_exception_is_recorded_against_the_symbol_and_swallowed(
    universe_db, monkeypatch
):
    """Task 6.4: one malformed response must not end a 634-symbol run."""
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "AAA")
    conn.commit()
    conn.close()

    def explode(symbol, timings=None):
        raise ValueError("something unexpected from vnstock")

    monkeypatch.setattr(bulk_ingestion, "load_ticker", explode)

    outcome = ingest_symbol("AAA")

    assert outcome["status"] == "error"
    assert "something unexpected" in outcome["error"]

    conn = sqlite3.connect(universe_db)
    try:
        state, error = conn.execute(
            "SELECT ingestion_state, ingestion_last_error FROM ticker_universe "
            "WHERE symbol = 'AAA'"
        ).fetchone()
    finally:
        conn.close()
    assert state == INGESTION_STATE_FAILED
    assert "ValueError" in error


def test_a_successful_load_is_not_re_recorded_by_the_batch(universe_db, monkeypatch):
    """`load_ticker` already writes the ok state with the observed range; the
    batch must not overwrite it with nulls."""
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "AAA")
    conn.execute(
        "UPDATE ticker_universe SET ingestion_state = ?, "
        "first_observed_session = '2018-01-02', observed_session_count = 100 "
        "WHERE symbol = 'AAA'",
        (INGESTION_STATE_OK,),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        bulk_ingestion, "load_ticker", lambda symbol, timings=None: _ok_result()
    )

    ingest_symbol("AAA")

    conn = sqlite3.connect(universe_db)
    try:
        state, first, count = conn.execute(
            "SELECT ingestion_state, first_observed_session, "
            "observed_session_count FROM ticker_universe WHERE symbol = 'AAA'"
        ).fetchone()
    finally:
        conn.close()
    assert (state, first, count) == (INGESTION_STATE_OK, "2018-01-02", 100)


# --- run loop (tasks 6.4, 6.5) ---


def test_run_continues_past_a_failing_symbol(universe_db, monkeypatch):
    conn = sqlite3.connect(universe_db)
    for symbol in ("AAA", "BBB", "CCC"):
        _universe_row(conn, symbol)
    conn.commit()
    conn.close()

    def load(symbol, timings=None):
        if symbol == "BBB":
            raise RuntimeError("boom")
        return _ok_result()

    monkeypatch.setattr(bulk_ingestion, "load_ticker", load)

    summary, outcomes = run_batch(["AAA", "BBB", "CCC"], sleep=lambda _: None)

    assert [o["symbol"] for o in outcomes] == ["AAA", "BBB", "CCC"]
    assert summary["succeeded"] == 2
    assert summary["fetch_failures"]["by_status"]["error"] == ["BBB"]


def test_run_loads_each_selected_symbol_exactly_once(universe_db, monkeypatch):
    """Task 6.5: a run touches only what it fetched — there is no
    whole-universe pass hiding in the loop."""
    conn = sqlite3.connect(universe_db)
    for symbol in ("AAA", "BBB"):
        _universe_row(conn, symbol)
    conn.commit()
    conn.close()

    loaded = []
    monkeypatch.setattr(
        bulk_ingestion, "load_ticker",
        lambda symbol, timings=None: (loaded.append(symbol), _ok_result())[1],
    )

    run_batch(["AAA", "BBB"], sleep=lambda _: None)

    assert loaded == ["AAA", "BBB"]


def test_an_interrupt_keeps_the_symbols_already_completed(universe_db, monkeypatch):
    conn = sqlite3.connect(universe_db)
    for symbol in ("AAA", "BBB", "CCC"):
        _universe_row(conn, symbol)
    conn.commit()
    conn.close()

    def load(symbol, timings=None):
        if symbol == "BBB":
            raise KeyboardInterrupt
        return _ok_result()

    monkeypatch.setattr(bulk_ingestion, "load_ticker", load)

    summary, outcomes = run_batch(["AAA", "BBB", "CCC"], sleep=lambda _: None)

    assert summary["interrupted"] is True
    assert summary["selected"] == 3
    assert [o["symbol"] for o in outcomes] == ["AAA"]


# --- summary (task 6.6) ---


def test_summary_separates_fetch_failures_from_filter_exclusions():
    """The `bulk-ticker-ingestion` requirement: a symbol that never returned
    data is an operational problem; one excluded by the liquidity filter is
    the filter working."""
    outcomes = [
        {"symbol": "AAA", "status": "ok", "rows_loaded": 2000,
         "features_computed": True, "hard_flag_count": 1, "soft_flag_count": 3,
         "stale_close_fraction": 0.02, "fails_liquidity_filter": False,
         "rate_limit_waits": 0, "elapsed_seconds": 4.0,
         "fetch_seconds": 1.0, "features_seconds": 3.0},
        {"symbol": "ILL", "status": "ok", "rows_loaded": 1500,
         "features_computed": True, "hard_flag_count": 0, "soft_flag_count": 0,
         "stale_close_fraction": 0.4, "fails_liquidity_filter": True,
         "rate_limit_waits": 0, "elapsed_seconds": 2.0,
         "fetch_seconds": 1.0, "features_seconds": 1.0},
        {"symbol": "GONE", "status": "no_data", "rows_loaded": 0,
         "rate_limit_waits": 0, "elapsed_seconds": 0.5, "error": "no_data"},
    ]

    summary = summarise(outcomes, universe_size=600)

    assert summary["succeeded"] == 2
    assert summary["fetch_failures"] == {
        "total": 1, "by_status": {"no_data": ["GONE"]}
    }
    assert summary["liquidity_exclusions"] == ["ILL"]
    assert summary["quality_gate"]["hard_flags"] == 1
    assert summary["quality_gate"]["symbols_with_hard_flags"] == ["AAA"]
    # No minimum-history exclusion count — task 7.1 picks that threshold from
    # this distribution, so inventing one here would prejudge it.
    assert "minimum_history_exclusions" not in summary
    assert summary["session_count_distribution"]["min"] == 1500
    assert summary["timing"]["extrapolated_processing_seconds"] == pytest.approx(
        (6.5 / 3) * 600
    )
    # The throttle, not the processing time, is what bounds a real run — a dry
    # run short enough to stay inside the rate limit never pays for it, so
    # scaling wall time alone would promise a 20-minute run that takes an
    # hour (measured 2026-09-07: 20 req/min, ~2 req/symbol).
    assert summary["timing"]["extrapolated_throttled_seconds"] == pytest.approx(3600.0)
    assert summary["timing"]["extrapolated_full_run_seconds"] == pytest.approx(3600.0)
    assert summary["timing"]["extrapolated_from"]["bound_by"] == "rate_limit"


def test_summary_flags_a_symbol_whose_features_failed():
    outcomes = [
        {"symbol": "AAA", "status": "ok", "rows_loaded": 10,
         "features_computed": False, "hard_flag_count": 0, "soft_flag_count": 0,
         "stale_close_fraction": 0.0, "fails_liquidity_filter": False,
         "rate_limit_waits": 0, "elapsed_seconds": 1.0,
         "fetch_seconds": 0.5, "features_seconds": 0.5},
    ]

    assert summarise(outcomes)["feature_failures"] == ["AAA"]


def test_the_journal_records_each_symbol_as_it_finishes(universe_db, monkeypatch, tmp_path):
    """A run killed outright — timeout, SIGTERM — never reaches
    `write_run_summary`, so the journal is the only thing that survives it,
    and the timing measurements cannot be reproduced by rerunning."""
    conn = sqlite3.connect(universe_db)
    for symbol in ("AAA", "BBB"):
        _universe_row(conn, symbol)
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        bulk_ingestion, "load_ticker", lambda symbol, timings=None: _ok_result()
    )
    journal = tmp_path / "runs" / "journal.jsonl"

    run_batch(["AAA", "BBB"], sleep=lambda _: None, journal_path=journal)

    lines = [json.loads(line) for line in journal.read_text().splitlines()]
    assert [entry["symbol"] for entry in lines] == ["AAA", "BBB"]


def test_run_summary_is_written_durably(tmp_path):
    """`bulk-ticker-ingestion`: the summary must outlive the process."""
    summary = {"attempted": 1, "succeeded": 1}
    outcomes = [{"symbol": "AAA", "status": "ok"}]

    path = write_run_summary(summary, outcomes, directory=tmp_path / "runs")

    assert path.exists()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["summary"]["succeeded"] == 1
    assert written["outcomes"][0]["symbol"] == "AAA"


# --- last-session spread (task 6.10) ---


def test_last_session_spread_reports_the_ragged_edge(universe_db):
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "FRESH1", state=INGESTION_STATE_OK, last_session="2026-09-04")
    _universe_row(conn, "FRESH2", state=INGESTION_STATE_OK, last_session="2026-09-04")
    _universe_row(conn, "STALE", state=INGESTION_STATE_OK, last_session="2026-08-12")
    conn.commit()
    conn.close()

    spread = last_session_spread()

    assert spread["symbols"] == 3
    assert spread["latest_session"] == "2026-09-04"
    assert spread["earliest_session"] == "2026-08-12"
    assert spread["spread_days"] == 23
    assert spread["symbols_at_latest"] == 2
    assert spread["symbols_behind_latest"] == 1


def test_last_session_spread_excludes_delisted_and_unloaded_symbols(universe_db):
    """A delisted symbol's last session is years old correctly, so including
    them would swamp the measurement with expected staleness."""
    conn = sqlite3.connect(universe_db)
    _universe_row(conn, "LIVE", state=INGESTION_STATE_OK, last_session="2026-09-04")
    _universe_row(conn, "DEAD", status="delisted", state=INGESTION_STATE_OK,
                  last_session="2022-07-28")
    _universe_row(conn, "NEVER", state=INGESTION_STATE_PENDING)
    conn.commit()
    conn.close()

    spread = last_session_spread()

    assert spread["symbols"] == 1
    assert spread["spread_days"] == 0
