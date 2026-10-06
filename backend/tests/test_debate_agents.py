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
    monkeypatch.setattr(macro_mod, "_foreign_flow_is_settling", lambda now=None: False)  # flow is final: it votes

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
    monkeypatch.setattr(macro_mod, "_foreign_flow_is_settling", lambda now=None: False)  # flow is final: it votes

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

    result = await synth.run("VCB", round2, round2)

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
    async def news_run(t):
        return AgentPosition(agent_id="news", stance="bull", reasoning=["Good news"])

    async def news_respond(t, r):
        return AgentPosition(agent_id="news", stance="bull", reasoning=["Held"])

    async def macro_run(t):
        return AgentPosition(agent_id="macro", stance="neutral", reasoning=["Mixed macro"])

    async def macro_respond(t, r):
        return AgentPosition(agent_id="macro", stance="neutral", reasoning=["Held"])

    engine._news.run, engine._news.respond = news_run, news_respond
    engine._macro.run, engine._macro.respond = macro_run, macro_respond

    async def fake_synth_run(ticker, r1, r2):
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
    # Every agent really ran both rounds (a fake that raised would show as neutral/"unavailable").
    assert result.round1["news"].reasoning == ["Good news"]
    assert result.round2["news"].reasoning == ["Held"]
    assert result.round2["macro"].reasoning == ["Held"]


@pytest.mark.asyncio
async def test_engine_one_agent_fails_debate_proceeds(monkeypatch):
    """One agent raising an exception → neutral fallback, debate still completes."""
    from app.services.debate.engine import AgentPosition, DebateEngine, DebateResult

    engine = DebateEngine()

    async def failing_run(ticker):
        raise RuntimeError("Network error")

    engine._news.run = failing_run
    engine._news.respond = failing_run
    async def tech_run(t):
        return AgentPosition("technical", "bear", ["RSI low"])

    async def tech_respond(t, r):
        return AgentPosition("technical", "bear", ["Held"])

    async def macro_run(t):
        return AgentPosition("macro", "bear", ["Macro weak"])

    async def macro_respond(t, r):
        return AgentPosition("macro", "bear", ["Held"])

    engine._technical.run, engine._technical.respond = tech_run, tech_respond
    engine._macro.run, engine._macro.respond = macro_run, macro_respond

    async def fake_synth(ticker, r1, r2):
        from app.services.debate.engine import SynthesisResult
        return SynthesisResult("CAUTION_SIGNAL", "majority", "Tension.", "Bear majority.")

    engine._synthesiser.run = fake_synth

    result = await engine.run("VCB")
    assert isinstance(result, DebateResult)
    # News agent fell back to neutral
    assert result.round1["news"].stance == "neutral"
    assert "Agent unavailable" in result.round1["news"].reasoning[0]
    assert result.round2["news"].stance == "neutral"
    assert result.round2["technical"].reasoning == ["Held"]
    assert result.round2["macro"].stance == "bear"


# ===========================================================================
# Response parsing, synthesis context, Round 2 fallback
# ===========================================================================

@pytest.mark.parametrize("first_line", [
    "bull", "Bull.", "**bull**", "Stance: bull", "**Final stance:** bull", "_bull_", "Bullish",
])
def test_parse_stance_accepts_common_llm_formats(first_line):
    from app.services.debate.technical import _parse_stance_and_bullets

    stance, bullets = _parse_stance_and_bullets(f"{first_line}\n- RSI is 60", None)

    assert stance == "bull"
    assert bullets == ["RSI is 60"]


def test_parse_stance_unrecognised_keeps_round1_stance_not_neutral():
    from app.services.debate.engine import AgentPosition
    from app.services.debate.technical import _parse_stance_and_bullets

    r1 = AgentPosition(agent_id="technical", stance="bull", reasoning=["r1"])

    stance, _ = _parse_stance_and_bullets("I think things look fine.\n- point", r1)

    assert stance == "bull"
    assert _parse_stance_and_bullets("no stance here\n- point", None)[0] == "neutral"


def test_parse_bullets_keeps_negative_sign_and_other_markers():
    from app.services.debate.technical import _parse_stance_and_bullets

    _, bullets = _parse_stance_and_bullets("bear\n- -2.5% vs VN-Index\n* star bullet\n• dot bullet", None)

    assert bullets == ["-2.5% vs VN-Index", "star bullet", "dot bullet"]


@pytest.mark.asyncio
async def test_technical_reasoning_keeps_negative_sign(monkeypatch):
    from app.services.debate.technical import TechnicalAgent

    agent = TechnicalAgent()

    async def fake_chat(messages):
        return "- -0.15 MACD histogram"

    monkeypatch.setattr(agent._llm, "chat", fake_chat)

    out = await agent._generate_reasoning("VCB", "2026-10-05", "bear", {"macd_histogram": -0.15}, 1.0)

    assert out == ["-0.15 MACD histogram"]


@pytest.mark.asyncio
async def test_macro_reasoning_keeps_negative_sign(monkeypatch):
    from app.services.debate.macro import MacroAgent

    agent = MacroAgent()

    async def fake_chat(messages):
        return "- -0.8% relative to VN-Index"

    monkeypatch.setattr(agent._llm, "chat", fake_chat)

    out = await agent._generate_reasoning("VCB", "bear", {})

    assert out == ["-0.8% relative to VN-Index"]


@pytest.mark.asyncio
async def test_synthesiser_prompts_carry_ticker_and_every_bullet(monkeypatch):
    from app.services.debate.engine import AgentPosition
    from app.services.debate.synthesiser import Synthesiser

    synth = Synthesiser()
    prompts: list[str] = []

    async def capture(messages):
        prompts.append(messages[-1]["content"])
        return "ok"

    monkeypatch.setattr(synth._llm, "chat", capture)
    bullets = [f"bullet {i}" for i in range(5)]
    round2 = {
        a: AgentPosition(agent_id=a, stance="bear", reasoning=bullets)
        for a in ("technical", "news", "macro")
    }

    await synth.run("VPB", round2, round2)

    assert len(prompts) == 2
    for prompt in prompts:
        assert "VPB" in prompt and "unknown" not in prompt
        assert "bullet 4" in prompt  # the 5th bullet used to be dropped


@pytest.mark.asyncio
async def test_engine_round2_failure_keeps_round1_stance():
    from app.services.debate.engine import AgentPosition, DebateEngine, SynthesisResult

    engine = DebateEngine()

    async def r1_bull(ticker):
        return AgentPosition("technical", "bull", ["RSI high"], volatility_range_pct=1.2)

    async def r2_boom(ticker, round1):
        raise RuntimeError("llm timeout")

    async def neutral(ticker, *a):
        return AgentPosition("x", "neutral", ["n"])

    engine._technical.run = r1_bull
    engine._technical.respond = r2_boom
    engine._news.run = engine._news.respond = neutral
    engine._macro.run = engine._macro.respond = neutral

    async def synth(ticker, r1, r2):
        return SynthesisResult("OBSERVE", "majority", "t", "r")

    engine._synthesiser.run = synth

    result = await engine.run("VCB")

    assert result.round2["technical"].stance == "bull"
    assert result.round2["technical"].reasoning[0] == "RSI high"
    assert "Round 2 unavailable" in result.round2["technical"].reasoning[-1]


@pytest.mark.parametrize("response", [
    "Bear — shifting because macro is weak\n- a",
    "bear (shifted from bull)\n- a",
    "Stance (Round 2): bear\n- a",
    "My stance: bear\n- a",
    "Here is my update:\nbear\n- a",
    "```\nbear\n```\n- a",
    "## Final Stance\nbear\n- a",
])
def test_parse_stance_honours_a_deliberate_shift_when_annotated(response):
    from app.services.debate.engine import AgentPosition
    from app.services.debate.technical import _parse_stance_and_bullets

    r1 = AgentPosition(agent_id="technical", stance="bull", reasoning=["r1"])

    stance, bullets = _parse_stance_and_bullets(response, r1)

    assert stance == "bear"
    assert bullets == ["a"]


def test_parse_stance_does_not_read_a_sentence_or_bullet_as_the_stance():
    from app.services.debate.engine import AgentPosition
    from app.services.debate.technical import _parse_stance_and_bullets

    r1 = AgentPosition(agent_id="technical", stance="bull", reasoning=["r1"])

    assert _parse_stance_and_bullets("Bear market weighs on the index.\n- a", r1)[0] == "bull"
    assert _parse_stance_and_bullets("- Bear case: weak RSI", r1)[0] == "bull"
    assert _parse_stance_and_bullets("bullion prices are up", None)[0] == "neutral"


def test_parse_blank_response_raises_so_the_caller_falls_back():
    from app.services.debate.technical import _parse_stance_and_bullets

    with pytest.raises(ValueError):
        _parse_stance_and_bullets("  \n ", None)


def test_extract_bullets_ignores_markdown_rules():
    from app.services.debate.technical import _extract_bullets

    assert _extract_bullets("- - -\n* * *\n- real") == ["real"]
