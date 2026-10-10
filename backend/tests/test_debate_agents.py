"""Unit tests for the News Agent, the Macro Agent, the vote and the Debate Engine.

One round, one model call (News): see `retire-debate-round-two-and-model-prose`."""

from __future__ import annotations

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

def _macro_data(monkeypatch, *, vnindex, usdvnd, flow, ticker_closes, settling=False):
    from app.services.debate import macro as macro_mod

    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: vnindex)
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: ticker_closes)
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: usdvnd)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: flow)
    monkeypatch.setattr(macro_mod, "_foreign_flow_is_settling", lambda now=None: settling)
    return macro_mod.MacroAgent()


@pytest.mark.asyncio
async def test_macro_agent_bull_four_bullish_signals(monkeypatch):
    import pandas as pd
    import numpy as np

    dates = pd.date_range(end="2026-10-02", periods=22, freq="B").strftime("%Y-%m-%d")
    # VN-Index up, ticker outperforming, VND stable, foreign net buying (+15% of turnover, final: it votes)
    agent = _macro_data(
        monkeypatch,
        vnindex=pd.Series(np.linspace(1200, 1260, 22), index=dates),
        usdvnd=-0.3,
        flow=(15_000_000_000, 100_000_000_000),
        ticker_closes=pd.Series(np.linspace(50, 54, 22), index=dates),
    )

    pos = await agent.run("VCB")
    assert pos.agent_id == "macro"
    assert pos.stance == "bull"


@pytest.mark.asyncio
async def test_macro_agent_vnindex_unavailable_uses_remaining_signals(monkeypatch):
    """When VN-Index is completely unavailable, stance is derived from 3 remaining signals."""
    import pandas as pd

    agent = _macro_data(
        monkeypatch,
        vnindex=None,
        usdvnd=-0.2,  # VND stable → neutral
        flow=(-5_000_000_000, 40_000_000_000),  # net sell → bear
        ticker_closes=pd.Series([], dtype="float64"),
    )

    pos = await agent.run("VCB")
    assert pos.agent_id == "macro"
    # Only 2 votes: 0 (usdvnd stable) + (-1) (foreign sell) = -1 → bear
    assert pos.stance == "bear"

# ===========================================================================
# The vote — verdict mapping over the stances of live agents
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


def _round1(technical, news, macro):
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


def _vote_of(round1):
    from app.services.debate.synthesiser import vote

    return vote(round1)


def test_the_vote_needs_no_language_model(monkeypatch):
    """Traces: "The vote is deterministic, makes no language-model call and returns no prose".
    Every model call would raise, and the vote is still the mapping."""
    from app.services.debate.llm_client import LLMClient

    async def llm_down(self, messages):
        raise AssertionError("the vote called a language model")

    monkeypatch.setattr(LLMClient, "chat", llm_down)

    assert _vote_of(_round1("bull", "neutral", "bear")) == ("SPLIT", "split")
    assert _vote_of(_round1("bull", "bull", "bull")) == ("STRONG_BUY_SIGNAL", "unanimous")


def test_the_synthesiser_module_has_no_language_model_and_no_prose():
    from app.services.debate import synthesiser

    assert not hasattr(synthesiser, "Synthesiser")
    assert not hasattr(synthesiser, "LLMClient")
    assert not hasattr(synthesiser, "_TENSION_PROMPT") and not hasattr(synthesiser, "_SYNTHESIS_SUMMARY_PROMPT")


def test_three_live_agents_keep_the_existing_mapping():
    assert _vote_of(_round1("neutral", "neutral", "bull")) == ("OBSERVE", "majority")


@pytest.mark.parametrize(
    "stance, verdict",
    [("bull", "BUY_SIGNAL"), ("bear", "CAUTION_SIGNAL"), ("neutral", "OBSERVE")],
)
def test_two_live_agents_that_agree_never_reach_a_strong_or_unanimous_verdict(stance, verdict):
    assert _vote_of(_round1(stance, stance, ("neutral", "agent_error"))) == (verdict, "majority")


@pytest.mark.parametrize("other", ["neutral", "bear"])
def test_two_live_agents_that_disagree_are_a_split(other):
    # A neutral placeholder for the degraded agent would have made bull+neutral "OBSERVE".
    assert _vote_of(_round1("bull", other, ("neutral", "no_input"))) == ("SPLIT", "split")


@pytest.mark.parametrize(
    "round1",
    [
        _round1("bull", ("neutral", "no_input"), ("neutral", "agent_error")),
        _round1(("neutral", "agent_error"), ("neutral", "llm_failed"), ("neutral", "no_input")),
    ],
)
def test_fewer_than_two_live_agents_abstain_without_any_llm_call(monkeypatch, round1):
    from app.services.debate.llm_client import LLMClient

    async def fail(self, messages):
        raise AssertionError("the vote called the LLM while abstaining")

    monkeypatch.setattr(LLMClient, "chat", fail)

    assert _vote_of(round1) == ("INSUFFICIENT_DATA", "none")



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


def _engine(round1):
    """A DebateEngine whose agents are stubs; `calls[agent]` lists the extra arguments each `run` got."""
    from app.services.debate.engine import AGENT_ORDER, DebateEngine

    engine = DebateEngine()
    calls = {agent_id: [] for agent_id in AGENT_ORDER}
    for agent_id in AGENT_ORDER:
        getattr(engine, f"_{agent_id}").run = _stub(round1[agent_id], calls[agent_id])
    return engine, calls


@pytest.mark.asyncio
async def test_engine_all_agents_live_uses_the_eligibility_date_and_age():
    r1 = {"technical": _position("technical", "bull"), "news": _position("news", "bull"),
          "macro": _position("macro", "neutral")}
    engine, calls = _engine(r1)
    stages: list[str] = []

    result = await engine.run("VCB", eligibility=ELIGIBLE, on_stage=stages.append)

    assert (result.verdict, result.agreement_level) == ("BUY_SIGNAL", "majority")
    assert (result.as_of, result.data_as_of, result.data_age_sessions) == ("2026-10-02", "2026-10-02", 2)
    assert result.agents_degraded == []
    assert result.eligibility == {"eligible": True, "reasons": []}
    assert result.duration_ms >= 0
    assert calls["technical"] == [("2026-10-02",)]  # Technical reads the row of as_of
    assert calls["news"] == [()]
    assert stages == ["round1"]  # the run's only stage


@pytest.mark.asyncio
async def test_the_result_has_no_second_round_and_no_synthesis():
    r1 = {a: _position(a, "bull") for a in ("technical", "news", "macro")}
    engine, _ = _engine(r1)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    assert set(result.round1) == {"technical", "news", "macro"}
    assert not hasattr(result, "round2") and not hasattr(result, "synthesis")


@pytest.mark.asyncio
async def test_engine_copies_the_range_fields_from_round1_to_the_result():
    from app.services.debate.engine import AgentPosition

    technical = AgentPosition(
        "technical", "bull", ["RSI high"], range_5s_pct=4.02, sigma_daily_pct=1.5, range_coverage=0.68
    )
    r1 = {"technical": technical, "news": _position("news", "bull"), "macro": _position("macro", "neutral")}
    engine, _ = _engine(r1)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    assert (result.range_5s_pct, result.sigma_daily_pct, result.range_coverage) == (4.02, 1.5, 0.68)
    assert not hasattr(result, "volatility_range_pct")


@pytest.mark.asyncio
async def test_a_round1_exception_degrades_the_agent_and_two_live_agents_vote():
    from app.services.debate.engine import AGENT_UNAVAILABLE_REASONING

    r1 = {"technical": _position("technical", "bear"), "news": RuntimeError("Network error"),
          "macro": _position("macro", "bear")}
    engine, _ = _engine(r1)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    news = result.round1["news"]
    assert (news.stance, news.degraded_reason) == ("neutral", "agent_error")
    assert news.reasoning == AGENT_UNAVAILABLE_REASONING
    assert result.agents_degraded == ["news"]
    assert (result.verdict, result.agreement_level) == ("CAUTION_SIGNAL", "majority")


@pytest.mark.asyncio
async def test_agents_degraded_is_read_from_round1_and_the_reason_is_never_round2_failed():
    r1 = {"technical": _position("technical", "bull"),
          "news": _position("news", "neutral", "language-model analysis failed", reason="llm_failed"),
          "macro": _position("macro", "neutral", "nothing to count", reason="no_input")}
    engine, _ = _engine(r1)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    assert result.agents_degraded == ["news", "macro"]
    reasons = {p.degraded_reason for p in result.round1.values()}
    assert reasons == {None, "llm_failed", "no_input"} and "round2_failed" not in reasons


@pytest.mark.asyncio
async def test_two_degraded_agents_give_insufficient_data_and_no_further_call():
    r1 = {"technical": _position("technical", "bull"), "news": RuntimeError("down"),
          "macro": _position("macro", "neutral", reason="no_input")}
    engine, calls = _engine(r1)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    assert all(len(c) == 1 for c in calls.values())  # each agent ran once; nothing ran after
    assert (result.verdict, result.agreement_level) == ("INSUFFICIENT_DATA", "none")
    assert result.agents_degraded == ["news", "macro"]
    assert (result.range_5s_pct, result.sigma_daily_pct, result.range_coverage) == (None, None, None)


def _real_agent_data(monkeypatch):
    """Data for the real Technical and Macro agents and a News feed, so a failing model can be
    observed on all three (a stub `run` would prove nothing about who calls a model)."""
    import numpy as np
    import pandas as pd

    from app.services.debate import macro as macro_mod
    from app.services.debate import news as news_mod
    from app.services.debate import technical as technical_mod

    dates = pd.date_range(end="2026-10-02", periods=22, freq="B").strftime("%Y-%m-%d")
    row = {"date": "2026-10-02", "rsi": 61.0, "macd_histogram": 0.05, "tenkan_sen": 20.0, "kijun_sen": 18.0}

    async def headlines(ticker, sector):
        return ["[ticker] 2026-10-01 VCB headline"]

    monkeypatch.setattr(technical_mod, "_get_features_row", lambda t, a: row)
    monkeypatch.setattr(technical_mod, "compute_range", lambda t: None)
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: pd.Series(np.linspace(1200, 1260, 22), index=dates))
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: pd.Series(np.linspace(50, 54, 22), index=dates))
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: -0.3)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: (15e9, 100e9))
    monkeypatch.setattr(macro_mod, "_foreign_flow_is_settling", lambda now=None: False)
    monkeypatch.setattr(news_mod, "fetch_headlines", headlines)
    monkeypatch.setattr(news_mod, "_get_sector_for_ticker", lambda t: None)


@pytest.mark.asyncio
async def test_an_llm_outage_degrades_only_news_and_the_two_live_agents_still_vote(monkeypatch):
    """Traces: "Degraded agents are defined by an untrustworthy stance, not by failed prose".
    Technical and Macro never call a model, so an outage costs News's stance and nothing else."""
    from app.services.debate.engine import DebateEngine
    from app.services.debate.llm_client import LLMClient

    async def llm_down(self, messages):
        raise RuntimeError("llm down")

    monkeypatch.setattr(LLMClient, "chat", llm_down)
    _real_agent_data(monkeypatch)

    result = await DebateEngine().run("VCB", eligibility=ELIGIBLE)

    assert result.agents_degraded == ["news"]
    assert result.round1["news"].degraded_reason == "llm_failed"
    assert result.round1["technical"].degraded_reason is None and result.round1["macro"].degraded_reason is None
    assert (result.round1["technical"].stance, result.round1["macro"].stance) == ("bull", "bull")
    assert (result.verdict, result.agreement_level) == ("BUY_SIGNAL", "majority")  # not INSUFFICIENT_DATA


@pytest.mark.asyncio
async def test_as_of_is_the_eligibility_date_even_when_technical_raises():
    r1 = {"technical": RuntimeError("db locked"), "news": _position("news", "bull"),
          "macro": _position("macro", "bull")}
    engine, _ = _engine(r1)
    eligibility = {**ELIGIBLE, "as_of": "2020-01-03", "age_sessions": 7}  # never the system date

    result = await engine.run("VCB", eligibility=eligibility)

    assert (result.as_of, result.data_as_of, result.data_age_sessions) == ("2020-01-03", "2020-01-03", 7)


@pytest.mark.asyncio
async def test_run_with_an_ineligible_ticker_abstains_without_running_any_agent():
    eligibility = {"eligible": False, "reasons": ["stale", "near_gap"], "as_of": "2026-09-07", "age_sessions": 21}
    from app.services.debate.engine import AGENT_ORDER

    failing = {a: AssertionError("no agent may run") for a in AGENT_ORDER}
    engine, calls = _engine(failing)

    result = await engine.run("VCB", eligibility=eligibility)

    assert (result.verdict, result.agreement_level) == ("INSUFFICIENT_DATA", "none")
    assert result.eligibility == {"eligible": False, "reasons": ["stale", "near_gap"]}
    assert (result.round1, result.agents_degraded) == ({}, [])
    assert all(not c for c in calls.values())


@pytest.mark.asyncio
async def test_run_without_eligibility_asks_assess_eligibility(monkeypatch):
    monkeypatch.setattr("app.services.data_eligibility.assess_eligibility", lambda ticker: ELIGIBLE)
    r1 = {a: _position(a, "bull") for a in ("technical", "news", "macro")}
    engine, _ = _engine(r1)

    result = await engine.run("VCB")

    assert result.as_of == "2026-10-02"


# ===========================================================================
# Response parsing (the News reply)
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


@pytest.mark.parametrize("response", [
    "Bear — shifting because macro is weak\n- a",
    "bear (shifted from bull)\n- a",
    "Stance (Round 2): bear\n- a",
    "My stance: bear\n- a",
    "Here is my update:\nbear\n- a",
    "```\nbear\n```\n- a",
    "## Final Stance\nbear\n- a",
])
def test_parse_stance_honours_an_annotated_stance_line(response):
    from app.services.debate.technical import _parse_stance_and_bullets

    stance, bullets = _parse_stance_and_bullets(response, None)

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
# harden-debate-runtime: the engine seam and the event loop
# ===========================================================================

ADVICE_BULLET = "Investors should consider buying on weakness"


@pytest.mark.asyncio
async def test_a_withheld_bullet_is_a_placeholder_in_the_response_and_the_stance_stays():
    from app.api.debate import _serialise_result
    from app.services.debate.prompt_safety import WITHHELD

    r1 = {"technical": _position("technical", "bull", ADVICE_BULLET), "news": _position("news", "bull"),
          "macro": _position("macro", "neutral")}
    engine, _ = _engine(r1)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    assert result.round1["technical"].reasoning == [WITHHELD] and result.round1["technical"].stance == "bull"
    assert _serialise_result(result)["round1"]["technical"]["reasoning"] == [WITHHELD]  # the response says so
    assert result.agents_degraded == []  # withholding is not a degradation
    assert (result.verdict, result.agreement_level) == ("BUY_SIGNAL", "majority")  # and does not move a vote


@pytest.mark.asyncio
async def test_descriptive_bullets_pass_the_engine_seam_untouched():
    r1 = {a: _position(a, "bull", "Foreign investors net sold 245B VND") for a in ("technical", "news", "macro")}
    engine, _ = _engine(r1)

    result = await engine.run("VCB", eligibility=ELIGIBLE)

    assert all(p.reasoning == ["Foreign investors net sold 245B VND"] for p in result.round1.values())


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
    monkeypatch.setattr(agents[1]._llm, "chat", chat)  # only News calls a model

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
