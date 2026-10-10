"""Unit tests for the Technical Agent: a computed stance, the range fields and the values list.

The agent makes no language-model call (`retire-debate-round-two-and-model-prose`)."""

from __future__ import annotations

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

    pos = await tech_mod.TechnicalAgent().run("VCB")

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

    pos = await tech_mod.TechnicalAgent().run("TCB")

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

    pos = await tech_mod.TechnicalAgent().run("VCB", "2026-10-02")

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


_ROW = {"date": "2026-10-04", "rsi": 62.0, "macd_histogram": 0.1, "tenkan_sen": 25.0, "kijun_sen": 22.0}


@pytest.mark.asyncio
async def test_no_model_is_needed_and_the_agent_stays_live(monkeypatch):
    """Traces: "Technical Agent reasoning lists the computed indicator values", scenario "No model is needed"."""
    from app.services.debate import technical as tech_mod
    from app.services.debate.llm_client import LLMClient

    async def llm_down(self, messages):
        raise AssertionError("the Technical agent called a language model")

    monkeypatch.setattr(LLMClient, "chat", llm_down)
    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: _ROW)
    monkeypatch.setattr(tech_mod, "compute_range", lambda t: _range_result())
    agent = tech_mod.TechnicalAgent()

    pos = await agent.run("VCB")

    assert not hasattr(agent, "_llm") and not hasattr(agent, "respond")
    assert pos.stance == "bull" and pos.degraded_reason is None  # the stance is computed
    assert not any("unavailable" in bullet for bullet in pos.reasoning)


# ---------------------------------------------------------------------------
# Reasoning: the computed values, in order, rounded
# ---------------------------------------------------------------------------

async def _run(monkeypatch, served=None, row=None):
    from app.services.debate import technical as tech_mod

    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: row or _ROW)
    monkeypatch.setattr(tech_mod, "compute_range", lambda t: served if served is not None else _range_result())
    return await tech_mod.TechnicalAgent().run("VCB")


@pytest.mark.asyncio
async def test_reasoning_is_the_values_list_in_the_specs_order(monkeypatch):
    pos = await _run(monkeypatch)

    assert pos.reasoning == [
        "RSI: 62.0", "MACD histogram: 0.1", "Ichimoku Tenkan-sen: 25.0", "Ichimoku Kijun-sen: 22.0",
    ]


@pytest.mark.asyncio
async def test_values_are_rounded_to_one_four_two_and_two_decimals_and_keep_a_negative_sign(monkeypatch):
    row = {"date": "2026-10-04", "rsi": 41.37, "macd_histogram": -0.06521, "tenkan_sen": 43.084, "kijun_sen": 43.971}

    pos = await _run(monkeypatch, row=row)

    assert pos.reasoning == [
        "RSI: 41.4", "MACD histogram: -0.0652", "Ichimoku Tenkan-sen: 43.08", "Ichimoku Kijun-sen: 43.97",
    ]


@pytest.mark.asyncio
async def test_only_available_indicators_are_listed(monkeypatch):
    row = {"date": "2026-10-04", "rsi": 62.0, "macd_histogram": None, "tenkan_sen": 25.0, "kijun_sen": 22.0}

    pos = await _run(monkeypatch, row=row)

    assert pos.reasoning == ["RSI: 62.0", "Ichimoku Tenkan-sen: 25.0", "Ichimoku Kijun-sen: 22.0"]
    assert pos.degraded_reason is None


# ---------------------------------------------------------------------------
# The typical 5-session move: on the position, never in the bullets
# ---------------------------------------------------------------------------

def _states_the_band(bullets):
    text = " ".join(bullets).lower()
    return any(phrase in text for phrase in ("typical 5-session", "5-session move", "2 in 3", "coverage", "daily"))


@pytest.mark.asyncio
async def test_calibrated_band_is_on_the_position_and_not_in_any_bullet(monkeypatch):
    pos = await _run(monkeypatch, _range_result())

    assert (pos.range_5s_pct, pos.sigma_daily_pct, pos.range_coverage) == (4.02, 1.5, 0.68)
    assert not _states_the_band(pos.reasoning)
    assert not any(figure in " ".join(pos.reasoning) for figure in ("4.0", "1.50", "1.5%", "68"))


@pytest.mark.asyncio
async def test_uncalibrated_band_carries_null_coverage_and_makes_no_coverage_claim(monkeypatch):
    pos = await _run(monkeypatch, _range_result("uncalibrated"))

    assert pos.range_5s_pct == 4.02 and pos.sigma_daily_pct == 1.5 and pos.range_coverage is None
    assert not _states_the_band(pos.reasoning)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ineligible", "range_out_of_bounds", "model_unavailable"])
async def test_no_band_served_gives_null_fields_and_no_estimate(monkeypatch, status):
    pos = await _run(monkeypatch, _range_result(status))

    assert (pos.range_5s_pct, pos.sigma_daily_pct, pos.range_coverage) == (None, None, None)
    assert not _states_the_band(pos.reasoning)


@pytest.mark.asyncio
async def test_an_out_of_bounds_sigma_is_not_passed_on_as_a_daily_figure(monkeypatch):
    pos = await _run(monkeypatch, _range_result("range_out_of_bounds", sigma_daily_pct=41.7))

    assert pos.sigma_daily_pct is None and "41.7" not in " ".join(pos.reasoning)


@pytest.mark.asyncio
async def test_a_failing_range_service_does_not_stop_the_agent(monkeypatch):
    def broken(ticker):
        raise RuntimeError("database locked")

    from app.services.debate import technical as tech_mod

    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: _ROW)
    monkeypatch.setattr(tech_mod, "compute_range", broken)

    pos = await tech_mod.TechnicalAgent().run("VCB")

    assert pos.stance == "bull" and (pos.range_5s_pct, pos.sigma_daily_pct, pos.range_coverage) == (None, None, None)
    assert pos.reasoning[0] == "RSI: 62.0"  # the values list is still there
