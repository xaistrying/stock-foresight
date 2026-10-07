"""Round 1 `evidence` of the three agents (`debate-outcome-log`, task group 2).

The outcome log stores what the agents actually used; it never re-fetches.
"""

from __future__ import annotations

import hashlib

import pandas as pd
import pytest

from app.services.debate import macro as macro_mod
from app.services.debate import news as news_mod
from app.services.debate import technical as tech_mod
from app.services.debate.engine import AgentPosition
from app.services.range import RangeResult


def test_agent_position_still_constructs_positionally_without_evidence():
    pos = AgentPosition("technical", "bull", ["x"], 4.1, 1.8, 0.68, None)
    assert pos.evidence is None


# --- technical ---

@pytest.mark.asyncio
async def test_technical_evidence_holds_the_voted_values_near_gap_and_range_k(monkeypatch):
    row = {"date": "2026-10-04", "near_gap": 0, "rsi": 62.0, "macd_histogram": 0.1,
           "tenkan_sen": 25.0, "kijun_sen": 22.0}
    band = RangeResult("VCB", "2026-10-04", "ok", (), 1.5, 4.02, 1.2, 0.68, None)
    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: row)
    monkeypatch.setattr(tech_mod, "compute_range", lambda t: band)
    agent = tech_mod.TechnicalAgent()

    async def chat(messages):
        return "- RSI 62"

    agent._llm.chat = chat
    pos = await agent.run("VCB")

    assert pos.evidence == {
        "rsi": 62.0, "macd_histogram": 0.1, "tenkan_sen": 25.0, "kijun_sen": 22.0,
        "near_gap": 0, "range_k": 1.2,
    }


@pytest.mark.asyncio
async def test_technical_evidence_range_k_is_null_when_no_band_is_served(monkeypatch):
    row = {"date": "2026-10-04", "near_gap": 1, "rsi": 62.0, "macd_histogram": 0.1,
           "tenkan_sen": 25.0, "kijun_sen": 22.0}
    monkeypatch.setattr(tech_mod, "get_latest_features_row", lambda t: row)
    monkeypatch.setattr(tech_mod, "compute_range",
                        lambda t: RangeResult("VCB", "x", "model_unavailable", (), None, None, None, None, None))
    agent = tech_mod.TechnicalAgent()

    async def chat(messages):
        return "- RSI 62"

    agent._llm.chat = chat
    pos = await agent.run("VCB")

    assert pos.evidence["range_k"] is None and pos.evidence["near_gap"] == 1


def test_the_by_date_features_query_returns_near_gap(tmp_path, monkeypatch):
    import sqlite3

    from app.db.schema import CREATE_FEATURES_TABLE

    path = tmp_path / "app.db"
    conn = sqlite3.connect(path)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.execute(
        "INSERT INTO features (ticker, date, rsi, macd_histogram, tenkan_sen, kijun_sen, near_gap, computed_at)"
        " VALUES ('VCB', '2026-10-02', 61, 0.1, 20, 19, 1, 'x')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(tech_mod, "get_connection", lambda: sqlite3.connect(path))

    assert tech_mod._get_features_row("VCB", "2026-10-02")["near_gap"] == 1


# --- news ---

LINES = [
    "[ticker] 2026-10-05 VCB posts record profit — snippet",
    "[sector] 2026-10-04 Banks lift lending targets",
    "[market] 2026-10-03 VN-Index closes higher",
]


def _expected_id(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()[:12]


@pytest.mark.asyncio
async def test_news_evidence_has_one_tag_date_id_per_headline_given_to_the_llm(monkeypatch):
    async def fetch(ticker, sector):
        return LINES

    monkeypatch.setattr(news_mod, "fetch_headlines", fetch)
    monkeypatch.setattr(news_mod, "_get_sector_for_ticker", lambda t: "banking")
    agent = news_mod.NewsAgent()

    async def chat(messages):
        return "bull\n- Record profit"

    agent._llm.chat = chat
    pos = await agent.run("VCB")

    ids = pos.evidence["headline_ids"]
    assert [(h["tag"], h["date"]) for h in ids] == [
        ("ticker", "2026-10-05"), ("sector", "2026-10-04"), ("market", "2026-10-03")]
    assert [h["id"] for h in ids] == [_expected_id(line) for line in LINES]
    assert all(len(h["id"]) == 12 for h in ids)


def test_headline_ids_are_stable_and_carry_no_text():
    first = news_mod.headline_evidence(LINES)
    assert first == news_mod.headline_evidence(list(LINES))
    assert "profit" not in str(first)


@pytest.mark.asyncio
async def test_only_the_headlines_the_prompt_receives_are_recorded(monkeypatch):
    many = [f"[market] 2026-10-0{1 + i % 5} headline {i}" for i in range(news_mod.MAX_HEADLINES + 5)]

    async def fetch(ticker, sector):
        return many

    monkeypatch.setattr(news_mod, "fetch_headlines", fetch)
    monkeypatch.setattr(news_mod, "_get_sector_for_ticker", lambda t: None)
    agent = news_mod.NewsAgent()
    prompts = []

    async def chat(messages):
        prompts.append(messages[-1]["content"])
        return "neutral\n- backdrop only"

    agent._llm.chat = chat
    pos = await agent.run("VCB")

    assert len(pos.evidence["headline_ids"]) == news_mod.MAX_HEADLINES
    assert prompts[0].count("\n- [market] ") == news_mod.MAX_HEADLINES


# --- macro ---

def _dated(values):
    return pd.Series(values, index=[f"2026-09-{d:02d}" for d in range(1, len(values) + 1)], dtype="float64")


def _macro_agent(monkeypatch, *, usdvnd, flow, settling):
    monkeypatch.setattr(macro_mod, "_get_vnindex_closes", lambda n: _dated([100.0 + i for i in range(n)]))
    monkeypatch.setattr(macro_mod, "_load_ohlcv_closes", lambda t, n: _dated([100.0 + 3 * i for i in range(n)]))
    monkeypatch.setattr(macro_mod, "_get_usd_vnd_change", lambda n: usdvnd)
    monkeypatch.setattr(macro_mod, "_get_market_foreign_flow", lambda: flow)
    monkeypatch.setattr(macro_mod, "_foreign_flow_is_settling", lambda: settling)
    agent = macro_mod.MacroAgent()

    async def chat(messages):
        return "- stub"

    agent._llm.chat = chat
    return agent


@pytest.mark.asyncio
async def test_macro_evidence_holds_numbers_not_formatted_strings(monkeypatch):
    agent = _macro_agent(monkeypatch, usdvnd=0.2, flow=(-365e9, 1488e9), settling=False)
    pos = await agent.run("SAB")

    e = pos.evidence
    assert e["vnindex_slope"] == 1
    assert isinstance(e["rel_vs_vnindex_pct"], float)
    assert e["usdvnd_change_pct"] == pytest.approx(0.2)
    assert (e["foreign_net_vnd"], e["foreign_gross_vnd"]) == (-365e9, 1488e9)
    assert e["foreign_vote_counted"] is True
    assert not any(isinstance(v, str) for v in e.values())


@pytest.mark.asyncio
async def test_macro_evidence_nulls_the_unavailable_signals(monkeypatch):
    agent = _macro_agent(monkeypatch, usdvnd=None, flow=None, settling=False)
    e = (await agent.run("SAB")).evidence

    assert e["usdvnd_change_pct"] is None
    assert e["foreign_net_vnd"] is None and e["foreign_gross_vnd"] is None
    assert e["foreign_vote_counted"] is False


@pytest.mark.asyncio
async def test_a_settling_board_is_recorded_but_not_counted(monkeypatch):
    agent = _macro_agent(monkeypatch, usdvnd=0.0, flow=(-365e9, 1488e9), settling=True)
    e = (await agent.run("SAB")).evidence

    assert e["foreign_net_vnd"] == -365e9 and e["foreign_vote_counted"] is False
