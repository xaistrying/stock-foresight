"""Unit tests for News Agent, Macro Agent, Debate Engine, and Synthesiser."""

from __future__ import annotations

import itertools
import re
from unittest.mock import AsyncMock, patch

import pytest


# ===========================================================================
# News Agent
# ===========================================================================

def _news_agent(monkeypatch, headlines, chat=None):
    from app.services.debate import news as news_mod

    async def fake_fetch(ticker, sector):
        if isinstance(headlines, Exception):
            raise headlines
        return headlines

    monkeypatch.setattr(news_mod, "fetch_headlines", fake_fetch)
    monkeypatch.setattr(news_mod, "_get_sector_for_ticker", lambda t: None)
    agent = news_mod.NewsAgent()
    if chat is not None:
        agent._llm.chat = chat
    return agent


@pytest.mark.asyncio
async def test_news_agent_feed_failure_is_degraded_with_no_input(monkeypatch):
    """If fetch_headlines raises there is nothing to read: no vote, and it says why."""
    agent = _news_agent(monkeypatch, ConnectionError("timeout"))

    pos = await agent.run("VCB")

    assert pos.degraded_reason == "no_input"
    assert "could not fetch" in pos.reasoning[0].lower()


@pytest.mark.asyncio
async def test_news_agent_no_headlines_is_degraded_with_no_input_not_a_neutral_opinion(monkeypatch):
    pos = await _news_agent(monkeypatch, []).run("VCB")

    assert pos.degraded_reason == "no_input"
    assert "no recent news" in pos.reasoning[0].lower()


@pytest.mark.asyncio
async def test_news_agent_llm_failure_is_llm_failed_and_names_the_llm_not_the_feeds(monkeypatch):
    async def llm_down(messages):
        raise RuntimeError("llm down")

    pos = await _news_agent(monkeypatch, ["VCB profit up"], llm_down).run("VCB")

    assert pos.degraded_reason == "llm_failed"
    assert "language-model" in pos.reasoning[0].lower()
    assert "feed" not in pos.reasoning[0].lower()


@pytest.mark.asyncio
async def test_news_agent_reply_without_a_stance_line_is_llm_failed_not_neutral(monkeypatch):
    async def no_stance(messages):
        return "Verdict: bear\n- Profit warning reported"

    pos = await _news_agent(monkeypatch, ["VCB profit warning"], no_stance).run("VCB")

    assert pos.degraded_reason == "llm_failed"


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
    assert pos.degraded_reason is None
    assert len(pos.reasoning) >= 1


# ===========================================================================
# Macro Agent
# ===========================================================================

@pytest.mark.asyncio
async def test_macro_agent_bull_four_bullish_signals(monkeypatch):
    from app.services.debate import macro as macro_mod
    import pandas as pd
    import numpy as np

    dates = pd.date_range(end="2026-10-02", periods=22, freq="B").strftime("%Y-%m-%d")

    # VN-Index trending up
    vnindex_up = pd.Series(np.linspace(1200, 1260, 22), index=dates)
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: vnindex_up)

    # Ticker outperforming
    ticker_up = pd.Series(np.linspace(50, 54, 22), index=dates)
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
    assert result.key_tension is None  # unavailable, not a canned sentence shown as analysis
    # The fallback counts every Round 2 stance and never prints the verdict enum (Rule 6).
    assert result.reasoning == "Vote: 1 bullish, 1 neutral, 1 bearish."


# ===========================================================================
# Synthesiser — votes only the Round 2 stances of live agents
# ===========================================================================

def _round2(technical, news, macro):
    """Each argument is a stance, or (stance, degraded_reason) for a degraded agent."""
    from app.services.debate.engine import AgentPosition

    def position(agent, spec):
        stance, reason = (spec, None) if isinstance(spec, str) else spec
        text = f"PLACEHOLDER {agent}" if reason else f"{agent} reasoning"
        return AgentPosition(agent, stance, [text], degraded_reason=reason)

    return {
        "technical": position("technical", technical),
        "news": position("news", news),
        "macro": position("macro", macro),
    }


async def _synthesise(monkeypatch, round2, *, chat=None):
    from app.services.debate.synthesiser import Synthesiser

    synth = Synthesiser()
    prompts: list[str] = []

    async def capture(messages):
        prompts.append(messages[-1]["content"])
        return "ok"

    monkeypatch.setattr(synth._llm, "chat", chat or capture)
    return await synth.run("VCB", round2, round2), prompts


@pytest.mark.asyncio
async def test_three_live_agents_keep_the_existing_mapping(monkeypatch):
    result, _ = await _synthesise(monkeypatch, _round2("neutral", "neutral", "bull"))

    assert (result.verdict, result.agreement_level) == ("OBSERVE", "majority")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stance, verdict",
    [("bull", "BUY_SIGNAL"), ("bear", "CAUTION_SIGNAL"), ("neutral", "OBSERVE")],
)
async def test_two_live_agents_that_agree_never_reach_a_strong_or_unanimous_verdict(
    monkeypatch, stance, verdict
):
    result, _ = await _synthesise(monkeypatch, _round2(stance, stance, ("neutral", "agent_error")))

    assert (result.verdict, result.agreement_level) == (verdict, "majority")


@pytest.mark.asyncio
@pytest.mark.parametrize("other", ["neutral", "bear"])
async def test_two_live_agents_that_disagree_are_a_split(monkeypatch, other):
    # A neutral placeholder for the degraded agent would have made bull+neutral "OBSERVE".
    result, _ = await _synthesise(monkeypatch, _round2("bull", other, ("neutral", "no_input")))

    assert (result.verdict, result.agreement_level) == ("SPLIT", "split")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "round2",
    [
        _round2("bull", ("neutral", "no_input"), ("neutral", "round2_failed")),
        _round2(("neutral", "agent_error"), ("neutral", "llm_failed"), ("neutral", "no_input")),
    ],
)
async def test_fewer_than_two_live_agents_abstain_without_any_llm_call(monkeypatch, round2):
    async def fail(messages):
        raise AssertionError("the synthesiser called the LLM while abstaining")

    result, _ = await _synthesise(monkeypatch, round2, chat=fail)

    assert (result.verdict, result.agreement_level) == ("INSUFFICIENT_DATA", "none")
    assert result.key_tension == "" and result.reasoning == ""


@pytest.mark.asyncio
async def test_a_degraded_agent_is_named_unavailable_and_its_placeholder_is_not_shown(monkeypatch):
    _, prompts = await _synthesise(monkeypatch, _round2("bull", ("neutral", "llm_failed"), "bull"))

    assert len(prompts) == 2
    # The agent's own line says unavailable (the static preamble alone also does):
    assert "News Context agent (Round 2): unavailable" in prompts[0]
    assert "News Context: unavailable" in prompts[1]
    for prompt in prompts:
        assert "PLACEHOLDER news" not in prompt
        # The vote counts live agents only: the placeholder stance is not counted as neutral.
        assert "2 bullish, 0 neutral, 0 bearish" in prompt


@pytest.mark.asyncio
async def test_a_failing_synthesis_prose_keeps_the_verdict(monkeypatch):
    async def llm_down(messages):
        raise RuntimeError("llm down")

    result, _ = await _synthesise(
        monkeypatch, _round2("bull", ("neutral", "llm_failed"), "bull"), chat=llm_down
    )

    assert (result.verdict, result.agreement_level) == ("BUY_SIGNAL", "majority")
    # The fallback counts live stances only (a degraded agent's placeholder is not a vote).
    assert result.reasoning == "Vote: 2 bullish, 0 neutral, 0 bearish."


# ===========================================================================
# Debate Engine
# ===========================================================================

ELIGIBLE = {"eligible": True, "reasons": [], "as_of": "2026-10-02", "age_sessions": 2}


def _position(agent, stance, text="reasoning", reason=None):
    from app.services.debate.engine import AgentPosition

    return AgentPosition(agent, stance, [text], degraded_reason=reason)


def _stub(outcome, calls):
    """An agent method that returns `outcome`, or raises it when it is an exception."""

    async def method(ticker, *args):
        calls.append(args)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return method


def _engine(round1, round2):
    """A DebateEngine whose agents are stubs and whose synthesiser LLM is counted.

    Returns (engine, calls, synthesiser_prompts); `calls[agent][method]` lists the
    extra arguments each stub received.
    """
    from app.services.debate.engine import AGENT_ORDER, DebateEngine

    engine = DebateEngine()
    calls = {agent_id: {"run": [], "respond": []} for agent_id in AGENT_ORDER}
    for agent_id in AGENT_ORDER:
        agent = getattr(engine, f"_{agent_id}")
        agent.run = _stub(round1[agent_id], calls[agent_id]["run"])
        agent.respond = _stub(
            round2.get(agent_id, AssertionError("Round 2 was not expected")),
            calls[agent_id]["respond"],
        )

    prompts: list[str] = []

    async def chat(messages):
        prompts.append(messages[-1]["content"])
        return "synthesis prose"

    engine._synthesiser._llm.chat = chat
    return engine, calls, prompts


@pytest.mark.asyncio
async def test_engine_all_agents_live_uses_the_eligibility_date_and_age():
    r1 = {"technical": _position("technical", "bull"), "news": _position("news", "bull"),
          "macro": _position("macro", "neutral")}
    r2 = {a: _position(a, p.stance, "held") for a, p in r1.items()}
    engine, calls, prompts = _engine(r1, r2)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    assert (result.verdict, result.agreement_level) == ("BUY_SIGNAL", "majority")
    assert (result.as_of, result.data_as_of, result.data_age_sessions) == ("2026-10-02", "2026-10-02", 2)
    assert result.agents_degraded == []
    assert result.eligibility == {"eligible": True, "reasons": []}
    assert result.round2["news"].reasoning == ["held"]
    assert result.duration_ms >= 0
    assert calls["technical"]["run"] == [("2026-10-02",)]  # Technical reads the row of as_of
    assert calls["news"]["run"] == [()]
    assert len(prompts) == 2


@pytest.mark.asyncio
async def test_engine_copies_the_range_fields_from_round1_to_the_result():
    from app.services.debate.engine import AgentPosition

    technical = AgentPosition(
        "technical", "bull", ["RSI high"], range_5s_pct=4.02, sigma_daily_pct=1.5, range_coverage=0.68
    )
    r1 = {"technical": technical, "news": _position("news", "bull"), "macro": _position("macro", "neutral")}
    r2 = {a: _position(a, p.stance, "held") for a, p in r1.items()}
    engine, _, _ = _engine(r1, r2)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    assert (result.range_5s_pct, result.sigma_daily_pct, result.range_coverage) == (4.02, 1.5, 0.68)
    assert not hasattr(result, "volatility_range_pct")


@pytest.mark.asyncio
async def test_a_round1_exception_degrades_the_agent_and_two_live_agents_vote():
    from app.services.debate.engine import AGENT_UNAVAILABLE_REASONING

    r1 = {"technical": _position("technical", "bear"), "news": RuntimeError("Network error"),
          "macro": _position("macro", "bear")}
    r2 = {"technical": _position("technical", "bear", "held"), "macro": _position("macro", "bear", "held")}
    engine, calls, _ = _engine(r1, r2)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    news = result.round1["news"]
    assert (news.stance, news.degraded_reason) == ("neutral", "agent_error")
    assert news.reasoning == AGENT_UNAVAILABLE_REASONING
    assert result.round2["news"] == news and calls["news"]["respond"] == []  # not asked again
    # The others are not shown the degraded agent's placeholder as a position.
    assert set(calls["technical"]["respond"][0][0]) == {"technical", "macro"}
    assert result.agents_degraded == ["news"]
    assert (result.verdict, result.agreement_level) == ("CAUTION_SIGNAL", "majority")


@pytest.mark.asyncio
async def test_two_degraded_agents_after_round1_skip_round2_and_synthesis():
    r1 = {"technical": _position("technical", "bull"), "news": RuntimeError("down"),
          "macro": _position("macro", "neutral", reason="no_input")}
    engine, calls, prompts = _engine(r1, {})

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    assert all(not c["respond"] for c in calls.values())
    assert prompts == []
    assert (result.verdict, result.agreement_level) == ("INSUFFICIENT_DATA", "none")
    assert result.agents_degraded == ["news", "macro"]
    assert (result.range_5s_pct, result.sigma_daily_pct, result.range_coverage) == (None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["raises", "blank", "no_stance"])
async def test_a_round2_failure_keeps_the_round1_position_but_not_the_vote(failure):
    from app.services.debate.engine import ROUND2_UNAVAILABLE_NOTE, AgentPosition
    from app.services.debate.technical import StanceNotRecognised

    outcome = {
        "raises": RuntimeError("llm timeout"),
        "blank": ValueError("empty LLM response"),
        "no_stance": StanceNotRecognised("no stance line"),
    }[failure]
    r1 = {"technical": AgentPosition("technical", "bull", ["RSI high"], range_5s_pct=1.2),
          "news": _position("news", "bull"), "macro": _position("macro", "neutral")}
    r2 = {"technical": outcome, "news": _position("news", "bull", "held"),
          "macro": _position("macro", "neutral", "held")}
    engine, _, _ = _engine(r1, r2)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    technical = result.round2["technical"]
    assert (technical.stance, technical.degraded_reason) == ("bull", "round2_failed")
    assert technical.reasoning == ["RSI high", ROUND2_UNAVAILABLE_NOTE]
    assert result.agents_degraded == ["technical"]
    # Technical's kept "bull" does not vote: News bull vs Macro neutral is a split.
    assert (result.verdict, result.agreement_level) == ("SPLIT", "split")


@pytest.mark.asyncio
async def test_an_llm_outage_ends_in_insufficient_data():
    r1 = {"technical": _position("technical", "bull"),
          "news": _position("news", "neutral", "language-model analysis failed", reason="llm_failed"),
          "macro": _position("macro", "bull")}
    r2 = {"technical": RuntimeError("llm down"), "macro": RuntimeError("llm down")}
    engine, _, prompts = _engine(r1, r2)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    assert result.verdict == "INSUFFICIENT_DATA"
    assert result.agents_degraded == ["technical", "news", "macro"]
    assert prompts == []


@pytest.mark.asyncio
async def test_as_of_is_the_eligibility_date_even_when_technical_raises():
    r1 = {"technical": RuntimeError("db locked"), "news": _position("news", "bull"),
          "macro": _position("macro", "bull")}
    r2 = {"news": _position("news", "bull"), "macro": _position("macro", "bull")}
    engine, _, _ = _engine(r1, r2)
    eligibility = {**ELIGIBLE, "as_of": "2020-01-03", "age_sessions": 7}  # never the system date

    result = await engine.run("VCB", eligibility=eligibility)

    assert (result.as_of, result.data_as_of, result.data_age_sessions) == ("2020-01-03", "2020-01-03", 7)


@pytest.mark.asyncio
async def test_run_with_an_ineligible_ticker_abstains_without_running_any_agent():
    eligibility = {"eligible": False, "reasons": ["stale", "near_gap"], "as_of": "2026-09-07", "age_sessions": 21}
    from app.services.debate.engine import AGENT_ORDER

    failing = {a: AssertionError("no agent may run") for a in AGENT_ORDER}
    engine, calls, prompts = _engine(failing, failing)

    result = await engine.run("VCB", eligibility=eligibility)

    assert (result.verdict, result.agreement_level) == ("INSUFFICIENT_DATA", "none")
    assert result.eligibility == {"eligible": False, "reasons": ["stale", "near_gap"]}
    assert (result.round1, result.round2, result.agents_degraded) == ({}, {}, [])
    assert all(not c["run"] and not c["respond"] for c in calls.values()) and prompts == []


@pytest.mark.asyncio
async def test_run_without_eligibility_asks_assess_eligibility(monkeypatch):
    monkeypatch.setattr("app.services.data_eligibility.assess_eligibility", lambda ticker: ELIGIBLE)
    r1 = {a: _position(a, "bull") for a in ("technical", "news", "macro")}
    engine, _, _ = _engine(r1, r1)

    result = await engine.run("VCB")

    assert result.as_of == "2026-10-02"


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


def test_parse_stance_unrecognised_raises_instead_of_keeping_a_stance():
    """A reply with no stance line is a failed call, never a kept or a neutral stance."""
    from app.services.debate.engine import AgentPosition
    from app.services.debate.technical import StanceNotRecognised, _parse_stance_and_bullets

    r1 = AgentPosition(agent_id="technical", stance="bull", reasoning=["r1"])

    with pytest.raises(StanceNotRecognised):
        _parse_stance_and_bullets("I think things look fine.\n- point", r1)
    with pytest.raises(StanceNotRecognised):
        _parse_stance_and_bullets("no stance here\n- point", None)


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

    out = await agent._generate_reasoning("VCB", "2026-10-05", "bear", {"macd_histogram": -0.15}, None)

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
    from app.services.debate.technical import StanceNotRecognised, _parse_stance_and_bullets

    r1 = AgentPosition(agent_id="technical", stance="bull", reasoning=["r1"])

    for reply in ("Bear market weighs on the index.\n- a", "- Bear case: weak RSI", "bullion prices are up"):
        with pytest.raises(StanceNotRecognised):
            _parse_stance_and_bullets(reply, r1)


def test_parse_blank_response_raises_so_the_caller_falls_back():
    from app.services.debate.technical import _parse_stance_and_bullets

    with pytest.raises(ValueError):
        _parse_stance_and_bullets("  \n ", None)


def test_extract_bullets_ignores_markdown_rules():
    from app.services.debate.technical import _extract_bullets

    assert _extract_bullets("- - -\n* * *\n- real") == ["real"]


# ===========================================================================
# Synthesiser prompts and fallback describe the vote neutrally (Rule 6)
# ===========================================================================

STANCES = ("bull", "neutral", "bear")
ENUM_TEXT = re.compile(r"[A-Z]+_SIGNAL\b|INSUFFICIENT_DATA|\bSPLIT\b|\bOBSERVE\b")
TRANSACTION_VERBS = re.compile(r"\b(buy|sell|hold)\b", re.IGNORECASE)


@pytest.mark.asyncio
@pytest.mark.parametrize("stances", list(itertools.product(STANCES, repeat=3)))
async def test_prompts_carry_no_enum_text_or_transaction_verbs(monkeypatch, stances):
    _, prompts = await _synthesise(monkeypatch, _round2(*stances))

    assert len(prompts) == 2
    for prompt in prompts:
        assert not ENUM_TEXT.search(prompt)
        assert not TRANSACTION_VERBS.search(prompt)


@pytest.mark.asyncio
async def test_prompts_state_the_vote_as_counts_and_agreement(monkeypatch):
    _, prompts = await _synthesise(monkeypatch, _round2("bull", "bull", "neutral"))

    assert "2 bullish, 1 neutral, 0 bearish (majority)" in prompts[0]
    assert "2 bullish, 1 neutral, 0 bearish" in prompts[1]


@pytest.mark.asyncio
async def test_synthesis_fallback_shows_the_vote_not_the_enum(monkeypatch):
    async def llm_down(messages):
        raise RuntimeError("llm down")

    result, _ = await _synthesise(monkeypatch, _round2("bull", "bull", "neutral"), chat=llm_down)

    assert result.reasoning == "Vote: 2 bullish, 1 neutral, 0 bearish."
    assert not ENUM_TEXT.search(result.reasoning)


# ===========================================================================
# harden-debate-runtime: engine seam, unusable synthesis text, concurrency, loop
# ===========================================================================

ADVICE_BULLET = "Investors should consider buying on weakness"
USABLE = "The technical picture and the news disagree on direction, and the macro read is thin."
VOTE_LINE = "Vote: 2 bullish, 1 neutral, 0 bearish."


@pytest.mark.asyncio
async def test_a_withheld_round1_bullet_is_a_placeholder_in_round2_and_the_synthesis_and_the_stance_stays():
    from app.services.debate.prompt_safety import WITHHELD

    r1 = {"technical": _position("technical", "bull", ADVICE_BULLET), "news": _position("news", "bull"),
          "macro": _position("macro", "neutral")}
    r2 = {"technical": _position("technical", "bull", ADVICE_BULLET), "news": _position("news", "bull", "held"),
          "macro": _position("macro", "neutral", "held")}
    engine, calls, prompts = _engine(r1, r2)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    seen_by_news = calls["news"]["respond"][0][0]["technical"]
    assert seen_by_news.reasoning == [WITHHELD] and seen_by_news.stance == "bull"
    assert result.round1["technical"].reasoning == [WITHHELD]
    assert result.round2["technical"].reasoning == [WITHHELD] and result.round2["technical"].stance == "bull"
    assert result.agents_degraded == []  # withholding is not a degradation
    assert (result.verdict, result.agreement_level) == ("BUY_SIGNAL", "majority")  # and does not move a vote
    assert prompts and all(ADVICE_BULLET not in p and WITHHELD in p for p in prompts)


@pytest.mark.asyncio
async def test_descriptive_bullets_pass_the_engine_seam_untouched():
    r1 = {a: _position(a, "bull", "Foreign investors net sold 245B VND") for a in ("technical", "news", "macro")}
    engine, _, _ = _engine(r1, r1)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    assert all(p.reasoning == ["Foreign investors net sold 245B VND"] for p in result.round1.values())


UNUSABLE = [
    "", "   \n", "Too short.", "I'm sorry, I can't help with that.", "I can't assist with this request at all.",
    "I cannot provide an analysis of this stock for you.", "I am unable to write this analysis today, sorry.",
    "As an AI language model, I do not have a view on this.",
    "I’m sorry, but I can’t help with that request.",  # curly apostrophes, as models write them
]


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", UNUSABLE)
async def test_an_unusable_key_tension_reply_is_unavailable_and_the_summary_falls_back(monkeypatch, reply):
    async def chat(messages):
        return reply

    result, _ = await _synthesise(monkeypatch, _round2("bull", "bull", "neutral"), chat=chat)

    assert result.key_tension is None
    assert result.reasoning == VOTE_LINE  # the deterministic line, on the same test


@pytest.mark.asyncio
async def test_a_usable_reply_is_kept_trimmed(monkeypatch):
    async def chat(messages):
        return f"  {USABLE}\n"

    result, _ = await _synthesise(monkeypatch, _round2("bull", "bull", "neutral"), chat=chat)

    assert result.key_tension == USABLE and result.reasoning == USABLE


@pytest.mark.asyncio
async def test_a_refusal_phrase_later_in_a_long_text_does_not_make_it_unusable(monkeypatch):
    text = "The agents disagree about direction. Some analysts say they cannot rule out a pullback."

    async def chat(messages):
        return text

    result, _ = await _synthesise(monkeypatch, _round2("bull", "bull", "neutral"), chat=chat)

    assert result.key_tension == text


@pytest.mark.asyncio
async def test_recommendation_wording_in_the_synthesis_text_is_withheld(monkeypatch):
    from app.services.debate.prompt_safety import WITHHELD

    async def chat(messages):
        return "The agents are split on direction. Investors should buy this stock now for a quick gain."

    result, _ = await _synthesise(monkeypatch, _round2("bull", "bull", "neutral"), chat=chat)

    assert result.key_tension == f"The agents are split on direction. {WITHHELD}"
    assert "should buy" not in result.reasoning


@pytest.mark.asyncio
async def test_the_two_synthesiser_calls_overlap_in_time(monkeypatch):
    import asyncio
    import time

    async def chat(messages):
        await asyncio.sleep(0.3)
        return USABLE

    started = time.monotonic()
    result, _ = await _synthesise(monkeypatch, _round2("bull", "bull", "neutral"), chat=chat)

    assert time.monotonic() - started < 0.5  # one call's time, not two
    assert result.key_tension == USABLE and result.reasoning == USABLE


@pytest.mark.asyncio
async def test_one_failing_synthesiser_call_leaves_the_other_intact(monkeypatch):
    async def chat(messages):
        if "KEY TENSION" in messages[-1]["content"]:
            raise RuntimeError("llm down")
        return USABLE

    result, _ = await _synthesise(monkeypatch, _round2("bull", "bull", "neutral"), chat=chat)

    assert result.key_tension is None and result.reasoning == USABLE

    async def other_way(messages):
        if "KEY TENSION" in messages[-1]["content"]:
            return USABLE
        raise RuntimeError("llm down")

    result, _ = await _synthesise(monkeypatch, _round2("bull", "bull", "neutral"), chat=other_way)

    assert result.key_tension == USABLE and result.reasoning == VOTE_LINE


@pytest.mark.asyncio
async def test_blocking_reads_in_the_agents_do_not_stall_the_event_loop(monkeypatch):
    """Each agent's SQLite read blocks 0.3 s in a stub; a 10 ms ticker must never see a gap near that."""
    import asyncio
    import time

    import numpy as np
    import pandas as pd

    from app.services.debate import macro as macro_mod
    from app.services.debate import news as news_mod
    from app.services.debate import technical as technical_mod

    block = 0.3

    def blocking(value):
        def read(*args, **kwargs):
            time.sleep(block)
            return value

        return read

    dates = [f"D{i:02d}" for i in range(27)]
    vnindex = pd.Series(np.linspace(100, 110, 27), index=dates)

    async def bounded(fetch, *args):
        return {"_get_vnindex_closes": vnindex, "_get_usd_vnd_change": 0.1, "_get_market_foreign_flow": (1e9, 1e10)}[
            fetch.__name__
        ]

    async def headlines(ticker, sector):
        return ["[ticker] 2026-10-06 VCB headline"]

    row = {"date": "2026-10-07", "rsi": 60.0, "macd_histogram": 0.05, "tenkan_sen": 20.0, "kijun_sen": 18.0}
    monkeypatch.setattr(technical_mod, "_get_features_row", blocking(row))
    monkeypatch.setattr(technical_mod, "get_latest_features_row", blocking(row))
    monkeypatch.setattr(technical_mod, "compute_range", blocking(None))
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", blocking(pd.Series(np.linspace(50, 55, 22), index=dates[2:24])))
    monkeypatch.setattr(macro_mod, "_bounded", bounded)
    monkeypatch.setattr(news_mod, "_get_sector_for_ticker", blocking("banking"))
    monkeypatch.setattr(news_mod, "fetch_headlines", headlines)

    async def chat(messages):
        return "bull\n- a usable reasoning bullet for the test"

    agents = (technical_mod.TechnicalAgent(), news_mod.NewsAgent(), macro_mod.MacroAgent())
    for agent in agents:
        monkeypatch.setattr(agent._llm, "chat", chat)

    worst = 0.0

    async def probe():
        nonlocal worst
        while True:
            before = time.monotonic()
            await asyncio.sleep(0.01)
            worst = max(worst, time.monotonic() - before - 0.01)

    watcher = asyncio.create_task(probe())
    await asyncio.gather(agents[0].run("VCB", "2026-10-07"), agents[1].run("VCB"), agents[2].run("VCB"))
    watcher.cancel()

    assert worst < 0.1, f"the event loop was stalled for {worst:.2f} s"
