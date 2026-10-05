"""Unit tests for the Technical Agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


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
    monkeypatch.setattr(tech_mod, "predict_volatility_range", lambda t: 1.85)

    async def fake_chat(messages):
        return "- RSI at 62 is above the 55 bullish threshold\n- MACD histogram positive at 0.1\n- Tenkan above Kijun confirms uptrend"

    agent = tech_mod.TechnicalAgent()
    agent._llm.chat = fake_chat

    pos = await agent.run("VCB")
    assert isinstance(pos, AgentPosition)
    assert pos.agent_id == "technical"
    assert pos.stance == "bull"
    assert pos.volatility_range_pct == 1.85
    assert len(pos.reasoning) >= 1


@pytest.mark.asyncio
async def test_technical_agent_run_null_indicators(monkeypatch):
    from app.services.debate import technical as tech_mod

    fake_row = {"date": "2026-10-04", "rsi": None, "macd_histogram": None, "tenkan_sen": None, "kijun_sen": None}
    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: fake_row)
    monkeypatch.setattr(tech_mod, "predict_volatility_range", lambda t: None)

    agent = tech_mod.TechnicalAgent()
    pos = await agent.run("VCB")

    assert pos.stance == "neutral"
    assert "Indicator data unavailable" in pos.reasoning[0]


@pytest.mark.asyncio
async def test_technical_agent_run_includes_volatility_range(monkeypatch):
    from app.services.debate import technical as tech_mod

    fake_row = {"date": "2026-10-04", "rsi": 55.0, "macd_histogram": 0.02, "tenkan_sen": 20.0, "kijun_sen": 18.0}
    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: fake_row)
    monkeypatch.setattr(tech_mod, "predict_volatility_range", lambda t: 2.3)

    async def fake_chat(messages):
        return "- RSI at 55\n- MACD positive\n- Tenkan above Kijun"

    agent = tech_mod.TechnicalAgent()
    agent._llm.chat = fake_chat

    pos = await agent.run("TCB")
    assert pos.volatility_range_pct == 2.3
