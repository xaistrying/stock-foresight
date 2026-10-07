"""The debate endpoint and the outcome log (`debate-outcome-log`, task group 3)."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import debate as debate_mod
from app.db import debate_log as debate_log_mod
from app.services.debate import outcome_log
from app.services.debate.engine import AgentPosition, DebateResult, SynthesisResult

# Captured at import, before the autouse fixture redirects the path for each test.
REAL_LOG_PATH = debate_log_mod.DEBATE_LOG_DB_PATH


def _fingerprint(path: Path):
    return (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None


REAL_LOG_BEFORE = _fingerprint(REAL_LOG_PATH)

ELIGIBLE = {"eligible": True, "reasons": [], "as_of": "2026-10-06", "age_sessions": 0}


def _result() -> DebateResult:
    round1 = {
        "technical": AgentPosition("technical", "bull", ["RSI"], 4.1, 1.8, 0.68, evidence={"range_k": 1.3}),
        "news": AgentPosition("news", "bull", ["n"]),
        "macro": AgentPosition("macro", "neutral", ["m"]),
    }
    return DebateResult(
        ticker="VCB", as_of="2026-10-06", verdict="BUY_SIGNAL", agreement_level="majority",
        round1=round1, round2=dict(round1),
        synthesis=SynthesisResult("BUY_SIGNAL", "majority", "tension", "reason"),
        duration_ms=5, range_5s_pct=4.1, sigma_daily_pct=1.8, range_coverage=0.68,
        data_as_of="2026-10-06", data_age_sessions=0,
    )


@pytest.fixture()
def patched(monkeypatch):
    """The endpoint with a loaded, eligible ticker, a stub engine and a stub export."""
    monkeypatch.setattr(debate_mod, "get_features_computed", lambda t: 1)
    monkeypatch.setattr(debate_mod, "get_latest_features_row", lambda t: {"date": "2026-10-06"})
    monkeypatch.setattr(debate_mod, "assess_eligibility", lambda t: ELIGIBLE)
    monkeypatch.setattr(outcome_log, "_close_at", lambda t, d: 42.55)
    monkeypatch.setattr(outcome_log, "_code_rev", lambda: "abc1234")

    async def run(self, ticker, eligibility=None, on_stage=None):
        return _result()

    monkeypatch.setattr("app.services.debate.engine.DebateEngine.run", run)
    monkeypatch.setattr("app.services.debate.export.export_debate_report", lambda r: Path("/tmp/x.md"))


@pytest.fixture()
def client(patched):
    from app.main import app

    with TestClient(app) as c:
        yield c


def _rows():
    conn = sqlite3.connect(debate_log_mod.DEBATE_LOG_DB_PATH)
    try:
        return conn.execute("SELECT id, ticker, as_of FROM debate_log ORDER BY id").fetchall()
    finally:
        conn.close()


def test_success_returns_200_and_the_id_of_the_new_row(client):
    resp = client.post("/tickers/VCB/debate")

    assert resp.status_code == 200
    assert resp.json()["debate_log_id"] == 1
    assert _rows() == [(1, "VCB", "2026-10-06")]


def test_a_raising_writer_still_returns_the_full_result_and_logs_an_error(client, monkeypatch, caplog):
    def boom(result):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(debate_mod, "log_debate_run", boom)
    with caplog.at_level(logging.ERROR, logger=debate_mod.logger.name):
        resp = client.post("/tickers/VCB/debate")

    body = resp.json()
    assert resp.status_code == 200 and body["debate_log_id"] is None
    assert body["verdict"] == "BUY_SIGNAL" and set(body["round1"]) == {"technical", "news", "macro"}
    (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert record.exc_info is not None
    assert "VCB" in record.getMessage() and "2026-10-06" in record.getMessage()


def test_a_raising_export_still_lets_the_row_be_written(client, monkeypatch):
    def export_fails(result):
        raise OSError("disk full")

    monkeypatch.setattr("app.services.debate.export.export_debate_report", export_fails)
    resp = client.post("/tickers/VCB/debate")

    assert resp.status_code == 200 and resp.json()["debate_log_id"] == 1


def test_an_abstention_is_logged_too(client, monkeypatch):
    ineligible = {"eligible": False, "reasons": ["stale_data"], "as_of": "2026-10-06", "age_sessions": 20}
    monkeypatch.setattr(debate_mod, "assess_eligibility", lambda t: ineligible)
    resp = client.post("/tickers/VCB/debate")

    assert resp.json()["verdict"] == "INSUFFICIENT_DATA" and resp.json()["debate_log_id"] == 1


@pytest.mark.asyncio
async def test_three_requests_joined_to_one_run_write_one_row_and_share_the_id(patched, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    runs = []

    async def slow_run(self, ticker, eligibility=None, on_stage=None):
        runs.append(ticker)
        await asyncio.sleep(0.1)  # long enough for all three requests to arrive
        return _result()

    monkeypatch.setattr("app.services.debate.engine.DebateEngine.run", slow_run)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        responses = await asyncio.gather(*(ac.post("/tickers/VCB/debate") for _ in range(3)))

    assert runs == ["VCB"]  # one run
    assert [r.status_code for r in responses] == [200, 200, 200]
    assert [r.json()["debate_log_id"] for r in responses] == [1, 1, 1]  # one row, one shared id
    assert _rows() == [(1, "VCB", "2026-10-06")]


def test_the_endpoint_tests_do_not_create_or_change_the_real_log(client):
    client.post("/tickers/VCB/debate")

    assert debate_log_mod.DEBATE_LOG_DB_PATH != REAL_LOG_PATH
    assert _fingerprint(REAL_LOG_PATH) == REAL_LOG_BEFORE
