"""Tests for the debate outcome log writer (`debate-outcome-log` change, task groups 1-2)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timedelta

import pytest

from app.db import debate_log as debate_log_mod
from app.services.debate import outcome_log
from app.services.debate.engine import (
    AgentPosition,
    DebateResult,
    SynthesisResult,
    insufficient_data_result,
)

REASONING_SENTENCE = "Zebra-quartz reasoning sentence that must never be stored"
HEADLINE_TITLE = "Distinctive-headline-title-xyzzy"


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    """A temporary log file and a temporary app.db holding one ohlcv close."""
    log_path = tmp_path / "debate_log.db"
    app_path = tmp_path / "app.db"
    model_path = tmp_path / "model.json"
    monkeypatch.setattr(debate_log_mod, "DEBATE_LOG_DB_PATH", log_path)
    monkeypatch.setattr(outcome_log, "get_connection", lambda: sqlite3.connect(app_path))
    monkeypatch.setattr(outcome_log, "MODEL_PATH", model_path)
    monkeypatch.setattr(outcome_log, "_code_rev", lambda: "abc1234")
    for name in ("DEBATE_LLM_PROVIDER", "DEBATE_LLM_MODEL", "DEBATE_LLM_EFFORT"):
        monkeypatch.delenv(name, raising=False)
    conn = sqlite3.connect(app_path)
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, close REAL)")
    conn.execute("INSERT INTO ohlcv VALUES ('VCB', '2026-10-06', 42.55)")
    conn.commit()
    conn.close()
    return {"log": log_path, "app": app_path, "model": model_path}


def _result(ticker="VCB", as_of="2026-10-06", verdict="BUY_SIGNAL", **overrides) -> DebateResult:
    technical_evidence = {"rsi": 61.0, "near_gap": 0, "range_k": 1.3}
    news_evidence = {"headline_ids": [{"tag": "ticker", "date": "2026-10-05", "id": "0123456789ab"}]}
    macro_evidence = {"rel_vs_vnindex_pct": 1.23, "foreign_vote_counted": True}
    round1 = {
        "technical": AgentPosition("technical", "bull", [REASONING_SENTENCE], 4.1, 1.8, 0.68,
                                   evidence=technical_evidence),
        "news": AgentPosition("news", "bull", [HEADLINE_TITLE], evidence=news_evidence),
        "macro": AgentPosition("macro", "neutral", ["flat"], evidence=macro_evidence),
    }
    round2 = {
        "technical": AgentPosition("technical", "bull", ["kept"]),
        "news": AgentPosition("news", "bear", ["shifted"]),
        "macro": AgentPosition("macro", "neutral", ["held"]),
    }
    fields = dict(
        ticker=ticker, as_of=as_of, verdict=verdict, agreement_level="majority",
        round1=round1, round2=round2,
        synthesis=SynthesisResult(verdict, "majority", REASONING_SENTENCE, REASONING_SENTENCE),
        duration_ms=10, range_5s_pct=4.1, sigma_daily_pct=1.8, range_coverage=0.68,
        data_as_of=as_of, data_age_sessions=0, agents_degraded=[],
        eligibility={"eligible": True, "reasons": []},
    )
    fields.update(overrides)
    return DebateResult(**fields)


def _rows(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM debate_log ORDER BY id")]
    finally:
        conn.close()


OUTCOME_COLUMNS = (
    "outcome_status", "scored_at", "date_t5", "close_asof_at_scoring",
    "close_t5", "r5", "inside_band", "direction_hit",
)


# --- 1.1: the file ---

def test_first_write_creates_the_file_and_its_table(paths):
    assert not paths["log"].exists()
    row_id = outcome_log.log_debate_run(_result())
    assert paths["log"].exists()
    assert row_id == 1 and len(_rows(paths["log"])) == 1


def test_initialising_a_populated_log_keeps_its_rows(paths):
    outcome_log.log_debate_run(_result())
    conn = debate_log_mod.get_debate_log_connection()
    debate_log_mod.init_debate_log_db(conn)
    conn.close()
    assert len(_rows(paths["log"])) == 1


def test_init_db_neither_creates_nor_touches_debate_log(tmp_path, monkeypatch):
    from app.db import connection

    monkeypatch.setattr(connection, "DB_PATH", tmp_path / "fresh_app.db")
    monkeypatch.setattr(debate_log_mod, "DEBATE_LOG_DB_PATH", tmp_path / "debate_log.db")
    connection.init_db()
    names = {r[0] for r in sqlite3.connect(tmp_path / "fresh_app.db").execute(
        "SELECT name FROM sqlite_master")}
    assert "debate_log" not in names
    assert not (tmp_path / "debate_log.db").exists()


def test_rebuilding_app_db_leaves_the_log_intact(paths):
    outcome_log.log_debate_run(_result())
    paths["app"].unlink()
    assert len(_rows(paths["log"])) == 1


# --- 1.2: one row per run ---

def test_a_result_yields_one_fully_filled_row_with_null_outcomes(paths):
    outcome_log.log_debate_run(_result())
    (row,) = _rows(paths["log"])
    assert row["ticker"] == "VCB" and row["as_of"] == "2026-10-06"
    assert (row["eligible"], row["data_age_sessions"], row["agents_degraded"]) == (1, 0, "[]")
    assert json.loads(row["eligibility_reasons"]) == []
    assert (row["sigma_daily_pct"], row["range_5s_pct"], row["range_k"], row["range_coverage"]) == (
        1.8, 4.1, 1.3, 0.68)
    assert [row[c] for c in ("r1_technical", "r1_news", "r1_macro")] == ["bull", "bull", "neutral"]
    assert [row[c] for c in ("r2_technical", "r2_news", "r2_macro")] == ["bull", "bear", "neutral"]
    assert (row["verdict"], row["agreement_level"]) == ("BUY_SIGNAL", "majority")
    assert all(row[c] is not None for c in (
        "run_at", "close_at_asof", "llm_provider", "llm_model", "code_rev", "evidence"))
    assert all(row[c] is None for c in OUTCOME_COLUMNS)


def test_two_runs_of_the_same_ticker_and_as_of_give_two_rows(paths):
    first = outcome_log.log_debate_run(_result())
    second = outcome_log.log_debate_run(_result())
    rows = _rows(paths["log"])
    assert (first, second) == (1, 2) and len(rows) == 2


def test_an_abstention_logs_null_stances_and_eligible_zero(paths):
    eligibility = {"eligible": False, "reasons": ["stale_data"], "as_of": "2026-10-06", "age_sessions": 20}
    outcome_log.log_debate_run(insufficient_data_result("VCB", eligibility))
    (row,) = _rows(paths["log"])
    assert row["eligible"] == 0 and json.loads(row["eligibility_reasons"]) == ["stale_data"]
    assert row["verdict"] == "INSUFFICIENT_DATA"
    assert all(row[c] is None for c in (
        "r1_technical", "r1_news", "r1_macro", "r2_technical", "r2_news", "r2_macro"))


def test_a_degraded_agent_has_no_logged_stance(paths):
    result = _result()
    result.round1["news"] = AgentPosition("news", "neutral", ["x"], degraded_reason="llm_failed")
    result.round2["news"] = result.round1["news"]
    outcome_log.log_debate_run(result)
    (row,) = _rows(paths["log"])
    assert row["r1_news"] is None and row["r2_news"] is None and row["r1_macro"] == "neutral"


def test_a_failed_round_two_keeps_round_one_but_not_the_voting_stance(paths):
    result = _result()
    result.round2["news"] = AgentPosition("news", "bull", ["x"], degraded_reason="round2_failed")
    outcome_log.log_debate_run(result)
    (row,) = _rows(paths["log"])
    assert row["r1_news"] == "bull" and row["r2_news"] is None


def test_as_of_is_data_as_of_and_never_today(paths, monkeypatch):
    class FakeDate:
        @staticmethod
        def today():
            return datetime(2030, 1, 1).date()

    monkeypatch.setattr(outcome_log, "date", FakeDate, raising=False)
    outcome_log.log_debate_run(_result(as_of="2026-09-01", data_as_of="2026-10-06"))
    assert _rows(paths["log"])[0]["as_of"] == "2026-10-06"


def test_a_missing_data_as_of_raises_and_writes_nothing(paths):
    with pytest.raises(ValueError, match="data_as_of"):
        outcome_log.log_debate_run(_result(data_as_of=None))
    assert not paths["log"].exists()


def test_run_at_is_timezone_aware_utc(paths):
    outcome_log.log_debate_run(_result())
    run_at = datetime.fromisoformat(_rows(paths["log"])[0]["run_at"])
    assert run_at.utcoffset() == timedelta(0)


# --- 1.3: provenance and what is not stored ---

def test_close_is_captured_at_write_time_and_survives_a_revision(paths):
    outcome_log.log_debate_run(_result())
    conn = sqlite3.connect(paths["app"])
    conn.execute("UPDATE ohlcv SET close = 42.50")
    conn.commit()
    conn.close()
    assert _rows(paths["log"])[0]["close_at_asof"] == 42.55


def test_a_missing_bar_logs_a_null_close(paths):
    outcome_log.log_debate_run(_result(as_of="2026-10-05", data_as_of="2026-10-05"))
    assert _rows(paths["log"])[0]["close_at_asof"] is None


def test_model_hash_is_the_files_sha256_and_null_when_absent(paths):
    outcome_log.log_debate_run(_result())
    paths["model"].write_bytes(b"model-v1")
    outcome_log.log_debate_run(_result())
    paths["model"].write_bytes(b"model-v2")
    outcome_log.log_debate_run(_result())
    first, second, third = (r["model_sha256"] for r in _rows(paths["log"]))
    assert first is None
    assert second == hashlib.sha256(b"model-v1").hexdigest()
    assert third == hashlib.sha256(b"model-v2").hexdigest() != second


def test_llm_columns_come_from_the_environment(paths, monkeypatch):
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "claude_cli")
    monkeypatch.setenv("DEBATE_LLM_MODEL", "haiku")
    monkeypatch.setenv("DEBATE_LLM_EFFORT", "high")
    outcome_log.log_debate_run(_result())
    row = _rows(paths["log"])[0]
    assert (row["llm_provider"], row["llm_model"], row["llm_effort"]) == ("claude_cli", "haiku", "high")


def test_no_reasoning_title_or_other_environment_value_is_stored(paths, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value-never-stored")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gateway.invalid")
    outcome_log.log_debate_run(_result())
    stored = json.dumps(_rows(paths["log"])[0])
    for text in (REASONING_SENTENCE, HEADLINE_TITLE, "sk-secret-value-never-stored", "gateway.invalid"):
        assert text not in stored


def test_evidence_is_assembled_from_round_one_with_empty_for_a_missing_agent(paths):
    result = _result()
    result.round1["macro"] = AgentPosition("macro", "neutral", ["x"])  # no evidence
    outcome_log.log_debate_run(result)
    evidence = json.loads(_rows(paths["log"])[0]["evidence"])
    assert evidence["technical"]["rsi"] == 61.0
    assert evidence["news"]["headline_ids"][0]["id"] == "0123456789ab"
    assert evidence["macro"] == {}


def test_a_failed_write_leaves_no_partial_row_and_raises(paths, monkeypatch):
    monkeypatch.setattr(outcome_log, "INSERT_DEBATE_LOG", "INSERT INTO nope VALUES (1)")
    with pytest.raises(sqlite3.OperationalError):
        outcome_log.log_debate_run(_result())


def test_a_failed_git_lookup_is_not_cached_for_the_whole_process(monkeypatch):
    outcome_log._resolve_code_rev.cache_clear()
    calls = []

    def flaky(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired("git", 2)
        return subprocess.CompletedProcess(args, 0, stdout="abc1234\n" if "rev-parse" in args[0] else "", stderr="")

    monkeypatch.setattr(outcome_log.subprocess, "run", flaky)
    try:
        assert outcome_log._code_rev() is None  # git timed out: NULL, not a crash
        assert outcome_log._code_rev() == "abc1234"  # the next row recovers
    finally:
        outcome_log._resolve_code_rev.cache_clear()
