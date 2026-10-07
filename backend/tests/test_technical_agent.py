"""Unit tests for the Technical Agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.range import RangeResult


def _range_result(status="ok", **overrides) -> RangeResult:
    """What the range service returns; `ok` carries a 4.02% band from a 1.50% daily sigma."""
    served = status in ("ok", "uncalibrated")
    fields = {
        "ticker": "VCB", "as_of": "2026-10-04", "status": status, "reasons": (),
        "sigma_daily_pct": 1.5 if served else None,
        "range_5s_pct": 4.02 if served else None,
        "range_k": 1.2 if served else None,
        "range_coverage": 0.68 if status == "ok" else None,
        "range_hit_rate": {"rate": 0.7, "n": 50} if served else None,
    }
    return RangeResult(**{**fields, **overrides})


# ---------------------------------------------------------------------------
# _compute_stance_from_indicators
# ---------------------------------------------------------------------------

def test_stance_bull_all_indicators():
    from app.services.debate.technical import _compute_stance_from_indicators
    row = {"rsi": 60.0, "macd_histogram": 0.05, "tenkan_sen": 20.0, "kijun_sen": 18.0}
    stance, available, values = _compute_stance_from_indicators(row)
    assert stance == "bull"
    assert set(available) == {"RSI", "MACD", "Ichimoku"}


def test_stance_bear_all_indicators():
    from app.services.debate.technical import _compute_stance_from_indicators
    row = {"rsi": 40.0, "macd_histogram": -0.05, "tenkan_sen": 15.0, "kijun_sen": 20.0}
    stance, available, _ = _compute_stance_from_indicators(row)
    assert stance == "bear"


def test_stance_neutral_mixed():
    from app.services.debate.technical import _compute_stance_from_indicators
    # RSI bullish, MACD bearish, Ichimoku neutral → 1 bull, 1 bear, 0 neutral votes → tie → neutral
    row = {"rsi": 60.0, "macd_histogram": -0.05, "tenkan_sen": 20.0, "kijun_sen": 20.0}
    stance, _, _ = _compute_stance_from_indicators(row)
    assert stance == "neutral"


def test_stance_null_indicators_returns_empty():
    from app.services.debate.technical import _compute_stance_from_indicators
    row = {"rsi": None, "macd_histogram": None, "tenkan_sen": None, "kijun_sen": None}
    stance, available, values = _compute_stance_from_indicators(row)
    assert stance == "neutral"
    assert available == []
    assert values == {}


def test_stance_partial_indicators():
    from app.services.debate.technical import _compute_stance_from_indicators
    # Only RSI available and bullish
    row = {"rsi": 70.0, "macd_histogram": None, "tenkan_sen": None, "kijun_sen": None}
    stance, available, _ = _compute_stance_from_indicators(row)
    assert stance == "bull"
    assert available == ["RSI"]


# ---------------------------------------------------------------------------
# TechnicalAgent.run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_technical_agent_run_bull(monkeypatch):
    from app.services.debate import technical as tech_mod
    from app.services.debate.engine import AgentPosition

    fake_row = {
        "date": "2026-10-04",
        "rsi": 62.0,
        "macd_histogram": 0.1,
        "tenkan_sen": 25.0,
        "kijun_sen": 22.0,
    }
    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: fake_row)
    monkeypatch.setattr(tech_mod, "compute_range", lambda t: _range_result())

    async def fake_chat(messages):
        return "- RSI at 62 is above the 55 bullish threshold\n- MACD histogram positive at 0.1\n- Tenkan above Kijun confirms uptrend"

    agent = tech_mod.TechnicalAgent()
    agent._llm.chat = fake_chat

    pos = await agent.run("VCB")
    assert isinstance(pos, AgentPosition)
    assert pos.agent_id == "technical"
    assert pos.stance == "bull"
    assert (pos.range_5s_pct, pos.sigma_daily_pct, pos.range_coverage) == (4.02, 1.5, 0.68)
    assert len(pos.reasoning) >= 1


@pytest.mark.asyncio
async def test_technical_agent_run_null_indicators(monkeypatch):
    from app.services.debate import technical as tech_mod

    fake_row = {"date": "2026-10-04", "rsi": None, "macd_histogram": None, "tenkan_sen": None, "kijun_sen": None}
    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: fake_row)
    monkeypatch.setattr(tech_mod, "compute_range", lambda t: _range_result("model_unavailable"))

    agent = tech_mod.TechnicalAgent()
    pos = await agent.run("VCB")

    assert pos.stance == "neutral"
    assert "Indicator data unavailable" in pos.reasoning[0]
    assert pos.degraded_reason == "no_input"  # nothing to form a stance from: no vote


@pytest.mark.asyncio
async def test_technical_agent_run_includes_volatility_range(monkeypatch):
    from app.services.debate import technical as tech_mod

    fake_row = {"date": "2026-10-04", "rsi": 55.0, "macd_histogram": 0.02, "tenkan_sen": 20.0, "kijun_sen": 18.0}
    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: fake_row)
    monkeypatch.setattr(tech_mod, "compute_range", lambda t: _range_result(range_5s_pct=5.1, sigma_daily_pct=1.9))

    async def fake_chat(messages):
        return "- RSI at 55\n- MACD positive\n- Tenkan above Kijun"

    agent = tech_mod.TechnicalAgent()
    agent._llm.chat = fake_chat

    pos = await agent.run("TCB")
    assert (pos.range_5s_pct, pos.sigma_daily_pct, pos.range_coverage) == (5.1, 1.9, 0.68)


@pytest.mark.asyncio
async def test_technical_agent_reads_the_features_row_of_as_of_not_the_latest(monkeypatch):
    from app.services.debate import technical as tech_mod

    asked = []

    def by_date(ticker, as_of):
        asked.append((ticker, as_of))
        return {"date": as_of, "rsi": 62.0, "macd_histogram": 0.1, "tenkan_sen": 25.0, "kijun_sen": 22.0}

    def latest(ticker):
        raise AssertionError("the latest row must not be read when as_of is given")

    monkeypatch.setattr(tech_mod, "_get_features_row", by_date)
    monkeypatch.setattr(tech_mod, "get_latest_features_row", latest)
    monkeypatch.setattr(tech_mod, "compute_range", lambda t: _range_result())
    agent = tech_mod.TechnicalAgent()

    async def fake_chat(messages):
        return "- RSI 62"

    agent._llm.chat = fake_chat

    pos = await agent.run("VCB", "2026-10-02")

    assert asked == [("VCB", "2026-10-02")]
    assert pos.stance == "bull" and pos.degraded_reason is None


def test_features_row_by_date_returns_that_days_values(tmp_path, monkeypatch):
    import sqlite3

    from app.db.schema import CREATE_FEATURES_TABLE
    from app.services.debate import technical as tech_mod

    path = tmp_path / "app.db"
    conn = sqlite3.connect(path)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.executemany(
        "INSERT INTO features (ticker, date, rsi, macd_histogram, tenkan_sen, kijun_sen, near_gap, computed_at)"
        " VALUES ('VCB', ?, ?, 0.1, 20, 19, 0, 'x')",
        [("2026-10-02", 61.0), ("2026-10-05", 30.0)],  # a refresh stored a newer row
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(tech_mod, "get_connection", lambda: sqlite3.connect(path))

    assert tech_mod._get_features_row("VCB", "2026-10-02")["rsi"] == 61.0
    assert tech_mod._get_features_row("VCB", "2026-10-03") is None


@pytest.mark.asyncio
async def test_a_failing_llm_leaves_the_technical_agent_live_with_the_computed_values(monkeypatch):
    from app.services.debate import technical as tech_mod

    row = {"date": "2026-10-04", "rsi": 62.0, "macd_histogram": 0.1, "tenkan_sen": 25.0, "kijun_sen": 22.0}
    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: row)
    monkeypatch.setattr(tech_mod, "compute_range", lambda t: _range_result())
    agent = tech_mod.TechnicalAgent()

    async def llm_down(messages):
        raise RuntimeError("llm down")

    agent._llm.chat = llm_down

    pos = await agent.run("VCB")

    assert pos.stance == "bull" and pos.degraded_reason is None  # the stance is computed, not LLM-made
    assert pos.reasoning == [
        "RSI: 62.0", "MACD histogram: 0.1", "Ichimoku Tenkan-sen: 25.0", "Ichimoku Kijun-sen: 22.0",
    ]
    assert not any("unavailable" in bullet for bullet in pos.reasoning)


# ---------------------------------------------------------------------------
# The typical 5-session move in the prompt and on the position
# ---------------------------------------------------------------------------

_ROW = {"date": "2026-10-04", "rsi": 62.0, "macd_histogram": 0.1, "tenkan_sen": 25.0, "kijun_sen": 22.0}


async def _run_and_capture_prompt(monkeypatch, served):
    from app.services.debate import technical as tech_mod

    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: _ROW)
    monkeypatch.setattr(tech_mod, "compute_range", lambda t: served)
    prompts: list[str] = []

    async def fake_chat(messages):
        prompts.append(messages[-1]["content"])
        return "- RSI at 62 is above the 55 bullish threshold"

    agent = tech_mod.TechnicalAgent()
    agent._llm.chat = fake_chat
    position = await agent.run("VCB")
    return prompts[0], position


@pytest.mark.asyncio
async def test_calibrated_band_is_stated_with_its_coverage_and_the_daily_sigma(monkeypatch):
    prompt, pos = await _run_and_capture_prompt(monkeypatch, _range_result())

    assert "Typical 5-session move: ±4.0%" in prompt
    assert "about 2 in 3 of past 5-session moves stayed within this band" in prompt
    assert "daily volatility forecast 1.50%" in prompt
    assert "not a direction" in prompt and "not a ceiling" in prompt and "not a prediction" in prompt
    assert (pos.range_5s_pct, pos.sigma_daily_pct, pos.range_coverage) == (4.02, 1.5, 0.68)


@pytest.mark.asyncio
async def test_the_prompt_never_calls_the_band_expected(monkeypatch):
    for served in (_range_result(), _range_result("uncalibrated"), _range_result("range_out_of_bounds")):
        prompt, _ = await _run_and_capture_prompt(monkeypatch, served)
        assert "expected" not in prompt.lower()


@pytest.mark.asyncio
async def test_uncalibrated_band_makes_no_coverage_claim(monkeypatch):
    prompt, pos = await _run_and_capture_prompt(monkeypatch, _range_result("uncalibrated"))

    assert "Typical 5-session move: ±4.0%" in prompt
    assert "coverage not established for this stock" in prompt
    assert "2 in 3" not in prompt
    assert pos.range_5s_pct == 4.02 and pos.range_coverage is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ineligible", "range_out_of_bounds", "model_unavailable"])
async def test_no_band_served_gives_unavailable_and_null_fields(monkeypatch, status):
    prompt, pos = await _run_and_capture_prompt(monkeypatch, _range_result(status))

    assert "Typical 5-session move: unavailable" in prompt
    assert "do not estimate" in prompt.lower()
    assert (pos.range_5s_pct, pos.sigma_daily_pct, pos.range_coverage) == (None, None, None)


@pytest.mark.asyncio
async def test_an_out_of_bounds_sigma_is_not_passed_on_as_a_daily_figure(monkeypatch):
    served = _range_result("range_out_of_bounds", sigma_daily_pct=41.7)

    prompt, pos = await _run_and_capture_prompt(monkeypatch, served)

    assert "41.7" not in prompt and pos.sigma_daily_pct is None


@pytest.mark.asyncio
async def test_a_failing_range_service_does_not_stop_the_agent(monkeypatch):
    def broken(ticker):
        raise RuntimeError("database locked")

    from app.services.debate import technical as tech_mod

    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: _ROW)
    monkeypatch.setattr(tech_mod, "compute_range", broken)
    agent = tech_mod.TechnicalAgent()

    async def fake_chat(messages):
        return "- RSI at 62"

    agent._llm.chat = fake_chat

    pos = await agent.run("VCB")

    assert pos.stance == "bull" and pos.range_5s_pct is None


@pytest.mark.asyncio
async def test_round_two_keeps_the_round_one_range_fields(monkeypatch):
    from app.services.debate import technical as tech_mod
    from app.services.debate.engine import AgentPosition

    agent = tech_mod.TechnicalAgent()

    async def fake_chat(messages):
        return "bull\n- RSI still above 55"

    agent._llm.chat = fake_chat
    r1 = AgentPosition("technical", "bull", ["RSI high"], range_5s_pct=4.02, sigma_daily_pct=1.5, range_coverage=0.68)

    pos = await agent.respond("VCB", {"technical": r1})

    assert (pos.range_5s_pct, pos.sigma_daily_pct, pos.range_coverage) == (4.02, 1.5, 0.68)
