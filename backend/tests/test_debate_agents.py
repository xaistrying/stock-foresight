"""Unit tests for News Agent, Macro Agent, Debate Engine, and Synthesiser."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ===========================================================================
# News Agent
# ===========================================================================

@pytest.mark.asyncio
async def test_news_agent_graceful_on_scrape_failure(monkeypatch):
    """If fetch_headlines raises, agent returns neutral with a 'could not fetch' note."""
    from app.services.debate import news as news_mod

    async def fake_fetch(ticker, sector):
        raise ConnectionError("timeout")

    monkeypatch.setattr(news_mod, "fetch_headlines", fake_fetch)
    monkeypatch.setattr(news_mod, "_get_sector_for_ticker", lambda t: None)

    agent = news_mod.NewsAgent()
    pos = await agent.run("VCB")
    assert pos.stance == "neutral"
    assert "could not fetch" in pos.reasoning[0].lower()


@pytest.mark.asyncio
async def test_news_agent_no_headlines_returns_neutral(monkeypatch):
    from app.services.debate import news as news_mod

    async def fake_fetch(ticker, sector):
        return []

    monkeypatch.setattr(news_mod, "fetch_headlines", fake_fetch)
    monkeypatch.setattr(news_mod, "_get_sector_for_ticker", lambda t: None)

    agent = news_mod.NewsAgent()
    pos = await agent.run("VCB")
    assert pos.stance == "neutral"
    assert "no recent news" in pos.reasoning[0].lower()


@pytest.mark.asyncio
async def test_news_agent_extracts_bearish_signal(monkeypatch):
    from app.services.debate import news as news_mod

    async def fake_fetch(ticker, sector):
        return ["VCB reports Q3 profit warning — earnings down 20%", "Banking sector faces regulatory headwinds"]

    monkeypatch.setattr(news_mod, "fetch_headlines", fake_fetch)
    monkeypatch.setattr(news_mod, "_get_sector_for_ticker", lambda t: "banking")

    async def fake_chat(messages):
        return "bear\n- Profit warning reported for Q3\n- Regulatory pressure on banking sector"

    agent = news_mod.NewsAgent()
    agent._llm.chat = fake_chat

    pos = await agent.run("VCB")
    assert pos.agent_id == "news"
    assert pos.stance == "bear"
    assert len(pos.reasoning) >= 1


# ===========================================================================
# Macro Agent
# ===========================================================================

@pytest.mark.asyncio
async def test_macro_agent_bull_four_bullish_signals(monkeypatch):
    from app.services.debate import macro as macro_mod
    import pandas as pd
    import numpy as np

    # VN-Index trending up
    vnindex_up = pd.Series(np.linspace(1200, 1260, 22))
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: vnindex_up)

    # Ticker outperforming
    ticker_up = pd.Series(np.linspace(50, 54, 22))
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: ticker_up)

    # USD/VND stable / VND strengthening
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: -0.3)

    # Foreign net buyer across the market: (net, gross) in VND, net/gross = +15%
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: (15_000_000_000, 100_000_000_000))

    async def fake_chat(messages):
        return "- VN-Index trending up over 20 sessions\n- Ticker outperforming market\n- VND stable\n- Foreign buying pressure"

    agent = macro_mod.MacroAgent()
    agent._llm.chat = fake_chat

    pos = await agent.run("VCB")
    assert pos.agent_id == "macro"
    assert pos.stance == "bull"


@pytest.mark.asyncio
async def test_macro_agent_vnindex_unavailable_uses_remaining_signals(monkeypatch):
    """When VN-Index is completely unavailable, stance is derived from 3 remaining signals."""
    from app.services.debate import macro as macro_mod
    import pandas as pd
    import numpy as np

    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: None)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series([]))
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: -0.2)   # VND stable → neutral
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: (-5_000_000_000, 40_000_000_000))  # net sell → bear

    async def fake_chat(messages):
        return "- VN-Index data unavailable\n- VND stable\n- Net foreign selling"

    agent = macro_mod.MacroAgent()
    agent._llm.chat = fake_chat

    pos = await agent.run("VCB")
    assert pos.agent_id == "macro"
    # Only 2 votes: 0 (usdvnd stable) + (-1) (foreign sell) = -1 → bear
    assert pos.stance == "bear"


# ===========================================================================
# Synthesiser — verdict mapping
# ===========================================================================

def test_map_verdict_unanimous_bull():
    from app.services.debate.synthesiser import _map_verdict
    verdict, agreement = _map_verdict(["bull", "bull", "bull"])
    assert verdict == "STRONG_BUY_SIGNAL"
    assert agreement == "unanimous"


def test_map_verdict_majority_bull():
    from app.services.debate.synthesiser import _map_verdict
    verdict, agreement = _map_verdict(["bull", "bull", "neutral"])
    assert verdict == "BUY_SIGNAL"
    assert agreement == "majority"


def test_map_verdict_unanimous_bear():
    from app.services.debate.synthesiser import _map_verdict
    verdict, agreement = _map_verdict(["bear", "bear", "bear"])
    assert verdict == "STRONG_CAUTION_SIGNAL"
    assert agreement == "unanimous"


def test_map_verdict_majority_bear():
    from app.services.debate.synthesiser import _map_verdict
    verdict, agreement = _map_verdict(["bear", "bear", "bull"])
    assert verdict == "CAUTION_SIGNAL"
    assert agreement == "majority"


def test_map_verdict_unanimous_neutral():
    from app.services.debate.synthesiser import _map_verdict
    verdict, agreement = _map_verdict(["neutral", "neutral", "neutral"])
    assert verdict == "OBSERVE"
    assert agreement == "unanimous"


def test_map_verdict_two_neutral_one_bull():
    from app.services.debate.synthesiser import _map_verdict
    verdict, agreement = _map_verdict(["neutral", "neutral", "bull"])
    assert verdict == "OBSERVE"
    assert agreement == "majority"


def test_map_verdict_three_way_split():
    from app.services.debate.synthesiser import _map_verdict
    verdict, agreement = _map_verdict(["bull", "neutral", "bear"])
    assert verdict == "SPLIT"
    assert agreement == "split"


@pytest.mark.asyncio
async def test_synthesiser_degrades_instead_of_crashing_when_the_llm_is_down(monkeypatch):
    """Both of the synthesiser's LLM calls have fallbacks; the reasoning
    fallback referenced an undefined name, so any LLM failure there turned the
    whole debate into a 500 instead of a degraded result."""
    from app.services.debate.engine import AgentPosition
    from app.services.debate.synthesiser import Synthesiser

    synth = Synthesiser()

    async def llm_down(messages):
        raise RuntimeError("llm down")

    monkeypatch.setattr(synth._llm, "chat", llm_down)
    round2 = {
        "technical": AgentPosition(agent_id="technical", stance="bull", reasoning=["x"]),
        "news": AgentPosition(agent_id="news", stance="neutral", reasoning=["x"]),
        "macro": AgentPosition(agent_id="macro", stance="bear", reasoning=["x"]),
    }

    result = await synth.run(round2, round2)

    assert result.verdict == "SPLIT"
    assert result.key_tension == "Unable to generate key tension analysis."
    # The fallback names the verdict and every Round 2 stance.
    for expected in ("SPLIT", "bull", "neutral", "bear"):
        assert expected in result.reasoning


# ===========================================================================
# Debate Engine
# ===========================================================================

@pytest.mark.asyncio
async def test_engine_all_agents_succeed(monkeypatch):
    """All three agents succeed → DebateResult with all fields populated."""
    from app.services.debate import engine as eng_mod
    from app.services.debate.engine import AgentPosition, DebateResult

    async def fake_run(ticker):
        return AgentPosition(agent_id="technical", stance="bull", reasoning=["RSI bullish"])

    async def fake_respond(ticker, round1):
        return AgentPosition(agent_id="technical", stance="bull", reasoning=["Maintained"])

    # Patch DebateEngine's agents
    from app.services.debate.engine import DebateEngine
    engine = DebateEngine()

    engine._technical.run = fake_run
    engine._technical.respond = fake_respond
    engine._news.run = lambda t: AgentPosition(agent_id="news", stance="bull", reasoning=["Good news"])
    engine._news.respond = lambda t, r: AgentPosition(agent_id="news", stance="bull", reasoning=["Held"])
    engine._macro.run = lambda t: AgentPosition(agent_id="macro", stance="neutral", reasoning=["Mixed macro"])
    engine._macro.respond = lambda t, r: AgentPosition(agent_id="macro", stance="neutral", reasoning=["Held"])

    async def fake_synth_run(r1, r2):
        from app.services.debate.engine import SynthesisResult
        return SynthesisResult(
            verdict="BUY_SIGNAL",
            agreement_level="majority",
            key_tension="Technical and news bullish; macro neutral.",
            reasoning="Two of three agents signal bullish conditions.",
        )

    engine._synthesiser.run = fake_synth_run

    result = await engine.run("VCB")
    assert isinstance(result, DebateResult)
    assert result.verdict == "BUY_SIGNAL"
    assert result.agreement_level == "majority"
    assert "technical" in result.round1
    assert "news" in result.round2
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_engine_one_agent_fails_debate_proceeds(monkeypatch):
    """One agent raising an exception → neutral fallback, debate still completes."""
    from app.services.debate.engine import AgentPosition, DebateEngine, DebateResult

    engine = DebateEngine()

    async def failing_run(ticker):
        raise RuntimeError("Network error")

    engine._news.run = failing_run
    engine._news.respond = failing_run
    engine._technical.run = lambda t: AgentPosition("technical", "bear", ["RSI low"])
    engine._technical.respond = lambda t, r: AgentPosition("technical", "bear", ["Held"])
    engine._macro.run = lambda t: AgentPosition("macro", "bear", ["Macro weak"])
    engine._macro.respond = lambda t, r: AgentPosition("macro", "bear", ["Held"])

    async def fake_synth(r1, r2):
        from app.services.debate.engine import SynthesisResult
        return SynthesisResult("CAUTION_SIGNAL", "majority", "Tension.", "Bear majority.")

    engine._synthesiser.run = fake_synth

    result = await engine.run("VCB")
    assert isinstance(result, DebateResult)
    # News agent fell back to neutral
    assert result.round1["news"].stance == "neutral"
    assert "Agent unavailable" in result.round1["news"].reasoning[0]
