"""Tests for debate export service and debate API endpoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ===========================================================================
# Export service
# ===========================================================================

def _make_debate_result(ticker="VCB", verdict="BUY_SIGNAL", date="2026-10-04"):
    from app.services.debate.engine import (
        AgentPosition, DebateResult, SynthesisResult
    )
    r1 = {
        "technical": AgentPosition("technical", "bull", ["RSI bullish", "MACD positive"], 1.85),
        "news": AgentPosition("news", "bull", ["Positive Q3 results reported"]),
        "macro": AgentPosition("macro", "neutral", ["VN-Index flat"]),
    }
    r2 = {
        "technical": AgentPosition("technical", "bull", ["Maintained: RSI still above 55"], 1.85),
        "news": AgentPosition("news", "bull", ["Maintained: earnings confirmation"]),
        "macro": AgentPosition("macro", "neutral", ["Held: macro mixed"]),
    }
    synth = SynthesisResult(
        verdict=verdict,
        agreement_level="majority",
        key_tension="Technical and news are bullish; macro is cautious about index momentum.",
        reasoning="Two of three agents signal bullish conditions for VCB.",
    )
    return DebateResult(
        ticker=ticker,
        as_of=date,
        verdict=verdict,
        agreement_level="majority",
        round1=r1,
        round2=r2,
        synthesis=synth,
        volatility_range_pct=1.85,
        duration_ms=4200,
    )


def test_export_creates_file(tmp_path, monkeypatch):
    from app.services.debate import export as export_mod
    monkeypatch.setattr(export_mod, "REPORTS_DIR", tmp_path)

    result = _make_debate_result()
    path = export_mod.export_debate_report(result)

    assert path.exists()
    assert path.name == "2026-10-04_VCB.md"


def test_export_disclaimer_present(tmp_path, monkeypatch):
    from app.services.debate import export as export_mod
    monkeypatch.setattr(export_mod, "REPORTS_DIR", tmp_path)

    result = _make_debate_result()
    path = export_mod.export_debate_report(result)
    content = path.read_text()
    assert "not investment advice" in content.lower()


def test_export_agent_labels_correct(tmp_path, monkeypatch):
    """TechnicalAgent → 'Technical Signal', NewsAgent → 'News Context', Macro → 'Macro'."""
    from app.services.debate import export as export_mod
    monkeypatch.setattr(export_mod, "REPORTS_DIR", tmp_path)

    result = _make_debate_result()
    path = export_mod.export_debate_report(result)
    content = path.read_text()

    assert "Technical Signal" in content
    assert "News Context" in content
    assert "Macro" in content
    assert "Market Sentiment" not in content


def test_export_overwrite_on_rerun(tmp_path, monkeypatch):
    """Re-running export for same ticker+date overwrites the file."""
    from app.services.debate import export as export_mod
    monkeypatch.setattr(export_mod, "REPORTS_DIR", tmp_path)

    result = _make_debate_result()
    export_mod.export_debate_report(result)

    # Second export with different verdict
    result2 = _make_debate_result(verdict="OBSERVE")
    path2 = export_mod.export_debate_report(result2)
    content = path2.read_text()
    assert "Observe" in content


# ===========================================================================
# Debate API endpoint
# ===========================================================================

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_debate_endpoint_404_for_unloaded_ticker(client, monkeypatch):
    from app.api import debate as debate_mod
    monkeypatch.setattr(debate_mod, "get_features_computed", lambda t: 1)
    monkeypatch.setattr(debate_mod, "get_latest_features_row", lambda t: None)

    resp = client.post("/tickers/ZZZZZ/debate")
    assert resp.status_code == 404
    assert "not been loaded" in resp.json()["detail"]


def test_debate_endpoint_503_for_failed_features(client, monkeypatch):
    from app.api import debate as debate_mod
    monkeypatch.setattr(debate_mod, "get_features_computed", lambda t: 0)

    resp = client.post("/tickers/VCB/debate")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_debate_endpoint_200_with_valid_shape(monkeypatch):
    """200 response includes all required DebateResult fields (LLM calls mocked)."""
    from app.api import debate as debate_mod
    from app.services.debate.engine import AgentPosition, DebateResult, SynthesisResult

    monkeypatch.setattr(debate_mod, "get_features_computed", lambda t: 1)
    monkeypatch.setattr(debate_mod, "get_latest_features_row", lambda t: {
        "date": "2026-10-04", "near_gap": 0,
        "rsi": 60.0, "macd_histogram": 0.05,
        "tenkan_sen": 20.0, "kijun_sen": 18.0,
    })

    fake_result = _make_debate_result()

    async def fake_engine_run(self, ticker):
        return fake_result

    monkeypatch.setattr(
        "app.services.debate.engine.DebateEngine.run",
        fake_engine_run,
    )
    # Patch inside the debate module's imported export function
    import app.services.debate.export as export_mod_real
    monkeypatch.setattr(export_mod_real, "export_debate_report", lambda r: Path("/tmp/test.md"))

    from app.main import app
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/tickers/VCB/debate")

    assert resp.status_code == 200
    data = resp.json()
    for key in ("verdict", "agreement_level", "round1", "round2", "synthesis"):
        assert key in data, f"Missing key: {key}"


def _result_with(agreement_level, stances):
    """A DebateResult whose Round 2 stances are `stances` (technical, news, macro)."""
    from app.services.debate.engine import AgentPosition, DebateResult, SynthesisResult

    r2 = {
        agent: AgentPosition(agent, stance, [f"{agent} reasoning"])
        for agent, stance in zip(("technical", "news", "macro"), stances)
    }
    return DebateResult(
        ticker="VPB",
        as_of="2026-10-05",
        verdict="SPLIT" if agreement_level == "split" else "OBSERVE",
        agreement_level=agreement_level,
        round1=r2,
        round2=r2,
        synthesis=SynthesisResult("SPLIT", agreement_level, "a tension", "a summary"),
        volatility_range_pct=1.31,
        duration_ms=1000,
    )


def _agreement_line(tmp_path, monkeypatch, result):
    from app.services.debate import export as export_mod

    monkeypatch.setattr(export_mod, "REPORTS_DIR", tmp_path)
    content = export_mod.export_debate_report(result).read_text()
    return next(line for line in content.splitlines() if line.startswith("**Agreement**"))


def test_split_agreement_names_the_three_positions_not_zero_agreeing_agents(tmp_path, monkeypatch):
    # "Split (0 of 3 agents)" read as if nobody agreed with the verdict; the panel
    # already says "Split — 3 different positions".
    line = _agreement_line(tmp_path, monkeypatch, _result_with("split", ("bull", "neutral", "bear")))

    assert line == "**Agreement**: Split (3 different positions)"


@pytest.mark.parametrize(
    "level, stances, expected",
    [
        ("majority", ("bear", "neutral", "bear"), "**Agreement**: Majority (2 of 3 agents)"),
        ("unanimous", ("neutral", "neutral", "neutral"), "**Agreement**: Unanimous (3 of 3 agents)"),
    ],
)
def test_other_agreement_levels_still_count_the_agreeing_agents(tmp_path, monkeypatch, level, stances, expected):
    assert _agreement_line(tmp_path, monkeypatch, _result_with(level, stances)) == expected
