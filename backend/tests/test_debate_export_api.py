"""Tests for debate export service and debate API endpoint."""

from __future__ import annotations

import re
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
        range_5s_pct=4.14,
        sigma_daily_pct=1.85,
        range_coverage=0.68,
        duration_ms=4200,
    )


def test_export_creates_file(tmp_path, monkeypatch):
    from app.services.debate import export as export_mod
    monkeypatch.setattr(export_mod, "REPORTS_DIR", tmp_path)

    result = _make_debate_result()
    path = export_mod.export_debate_report(result)

    assert path.exists()
    assert path.name == "2026-10-04_VCB.md"


DISCLAIMER_MD = Path(__file__).resolve().parents[2] / "docs" / "DISCLAIMER.md"


def _disclaimer_section(heading: str) -> str:
    """The blockquote under `## <heading>`: `>` lines joined with one space, whitespace collapsed."""
    lines = DISCLAIMER_MD.read_text(encoding="utf-8").splitlines()
    rest = lines[lines.index(f"## {heading}") + 1:]
    quote = []
    for line in (l for l in rest if l.strip()):
        if not line.startswith(">"):
            break
        quote.append(line[1:])
    return re.sub(r"\s+", " ", " ".join(quote)).strip()


def test_export_ends_with_the_full_disclaimer_verbatim(tmp_path, monkeypatch):
    from app.services.debate import export as export_mod
    monkeypatch.setattr(export_mod, "REPORTS_DIR", tmp_path)

    content = export_mod.export_debate_report(_make_debate_result()).read_text()

    last_line = [l for l in content.splitlines() if l.strip()][-1]
    assert last_line == _disclaimer_section("Full disclaimer")
    assert "See docs/DISCLAIMER.md" not in content


def test_the_exporters_copy_equals_the_source_file():
    from app.services.debate.export import DISCLAIMER_FULL

    assert DISCLAIMER_FULL == _disclaimer_section("Full disclaimer")


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
    assert "**Verdict**: Observe" in content


# ===========================================================================
# Debate API endpoint
# ===========================================================================

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


ELIGIBLE = {"eligible": True, "reasons": [], "as_of": "2026-10-04", "age_sessions": 0}


def _must_not_be_called(*args, **kwargs):
    raise AssertionError("this must not be called on this path")


def test_debate_endpoint_404_for_unloaded_ticker(client, monkeypatch):
    from app.api import debate as debate_mod
    monkeypatch.setattr(debate_mod, "get_features_computed", lambda t: 1)
    monkeypatch.setattr(debate_mod, "get_latest_features_row", lambda t: None)
    monkeypatch.setattr(debate_mod, "assess_eligibility", _must_not_be_called)

    resp = client.post("/tickers/ZZZZZ/debate")
    assert resp.status_code == 404
    assert "not been loaded" in resp.json()["detail"]


def test_debate_endpoint_503_for_failed_features(client, monkeypatch):
    from app.api import debate as debate_mod
    monkeypatch.setattr(debate_mod, "get_features_computed", lambda t: 0)
    monkeypatch.setattr(debate_mod, "assess_eligibility", _must_not_be_called)

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
    monkeypatch.setattr(debate_mod, "assess_eligibility", lambda t: ELIGIBLE)

    fake_result = _make_debate_result()

    async def fake_engine_run(self, ticker, eligibility=None, on_stage=None):
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
        range_5s_pct=2.93,
        sigma_daily_pct=1.31,
        range_coverage=0.68,
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


# ===========================================================================
# Eligibility guard, degraded agents and the new response fields
# ===========================================================================

def _loaded(monkeypatch, eligibility):
    from app.api import debate as debate_mod

    monkeypatch.setattr(debate_mod, "get_features_computed", lambda t: 1)
    monkeypatch.setattr(debate_mod, "get_latest_features_row", lambda t: {"date": eligibility["as_of"]})
    monkeypatch.setattr(debate_mod, "assess_eligibility", lambda t: eligibility)
    return debate_mod


def test_an_ineligible_ticker_gets_a_200_abstention_without_llm_fetch_or_file(client, monkeypatch, tmp_path):
    from app.services.debate import export as export_mod
    from app.services.debate import macro as macro_mod
    from app.services.debate import news as news_mod
    from app.services.debate.llm_client import LLMClient

    eligibility = {
        "eligible": False, "reasons": ["delisted", "stale", "hard_quality_flag"],
        "as_of": "2026-09-07", "age_sessions": 21,
    }
    _loaded(monkeypatch, eligibility)
    monkeypatch.setattr(LLMClient, "chat", _must_not_be_called)
    monkeypatch.setattr(news_mod, "fetch_headlines", _must_not_be_called)
    monkeypatch.setattr(macro_mod, "_bounded", _must_not_be_called)
    monkeypatch.setattr(export_mod, "REPORTS_DIR", tmp_path)

    resp = client.post("/tickers/VCB/debate")

    assert resp.status_code == 200
    body = resp.json()
    assert (body["verdict"], body["agreement_level"]) == ("INSUFFICIENT_DATA", "none")
    assert body["eligibility"] == {"eligible": False, "reasons": ["delisted", "stale", "hard_quality_flag"]}
    assert (body["as_of"], body["data_as_of"], body["data_age_sessions"]) == ("2026-09-07", "2026-09-07", 21)
    assert (body["round1"], body["round2"], body["agents_degraded"]) == ({}, {}, [])
    assert body["range_5s_pct"] is None and "volatility_range_pct" not in body
    assert body["synthesis"]["key_tension"] == "" and body["synthesis"]["reasoning"] == ""
    assert list(tmp_path.iterdir()) == []  # a refusal must not overwrite a real report


def test_an_eligible_ticker_returns_the_new_fields_and_the_engine_gets_the_eligibility(client, monkeypatch):
    from app.services.debate.engine import AgentPosition

    _loaded(monkeypatch, ELIGIBLE)
    result = _make_debate_result()
    result.round2["news"] = AgentPosition("news", "neutral", ["placeholder"], degraded_reason="llm_failed")
    result.agents_degraded = ["news"]
    result.data_as_of, result.data_age_sessions = "2026-10-04", 0
    result.eligibility = {"eligible": True, "reasons": []}
    seen = []

    async def fake_engine_run(self, ticker, eligibility=None, on_stage=None):
        seen.append(eligibility)
        return result

    monkeypatch.setattr("app.services.debate.engine.DebateEngine.run", fake_engine_run)
    monkeypatch.setattr("app.services.debate.export.export_debate_report", lambda r: Path("/tmp/x.md"))

    body = client.post("/tickers/VCB/debate").json()

    assert seen == [ELIGIBLE]
    assert body["agents_degraded"] == ["news"]
    assert body["eligibility"] == {"eligible": True, "reasons": []}
    assert (body["data_as_of"], body["data_age_sessions"]) == ("2026-10-04", 0)
    assert body["round2"]["news"]["degraded_reason"] == "llm_failed"
    assert body["round2"]["technical"]["degraded_reason"] is None
    assert body["round1"]["technical"]["degraded_reason"] is None


def test_an_abstention_after_the_agents_ran_is_not_exported(client, monkeypatch):
    from app.services.debate.engine import insufficient_data_result

    _loaded(monkeypatch, ELIGIBLE)
    abstention = insufficient_data_result("VCB", {**ELIGIBLE})
    exported = []

    async def fake_engine_run(self, ticker, eligibility=None, on_stage=None):
        return abstention

    monkeypatch.setattr("app.services.debate.engine.DebateEngine.run", fake_engine_run)
    monkeypatch.setattr("app.services.debate.export.export_debate_report", exported.append)

    assert client.post("/tickers/VCB/debate").json()["verdict"] == "INSUFFICIENT_DATA"
    assert exported == []


# ===========================================================================
# Export: data age, unavailable agents, abstentions
# ===========================================================================

def _export(tmp_path, monkeypatch, result):
    from app.services.debate import export as export_mod

    monkeypatch.setattr(export_mod, "REPORTS_DIR", tmp_path)
    return export_mod.export_debate_report(result)


def _with_news_degraded(reason="llm_failed", news_stance="neutral", tech="bull", macro="bull"):
    """Technical and Macro live, News degraded: a result for two live agents."""
    from app.services.debate.engine import AgentPosition

    result = _make_debate_result(verdict="BUY_SIGNAL")
    for rnd in (result.round1, result.round2):
        rnd["technical"] = AgentPosition("technical", tech, ["tech reasoning"], 1.85)
        rnd["macro"] = AgentPosition("macro", macro, ["macro reasoning"])
        rnd["news"] = AgentPosition("news", news_stance, ["PLACEHOLDER news"], degraded_reason=reason)
    result.agents_degraded = ["news"]
    return result


@pytest.mark.parametrize(
    "age, expected",
    [(2, "**Data as of**: 2026-10-02 (2 sessions old)"), (1, "**Data as of**: 2026-10-02 (1 session old)"),
     (0, "**Data as of**: 2026-10-02 (current)")],
)
def test_summary_states_the_data_date_and_age(tmp_path, monkeypatch, age, expected):
    result = _make_debate_result(date="2026-10-02")
    result.data_as_of, result.data_age_sessions = "2026-10-02", age

    content = _export(tmp_path, monkeypatch, result).read_text()

    assert expected in content.splitlines()


def test_an_unavailable_agent_is_listed_and_agreement_counts_live_agents_only(tmp_path, monkeypatch):
    content = _export(tmp_path, monkeypatch, _with_news_degraded()).read_text()
    lines = content.splitlines()

    assert "**Unavailable agents**: News Context (The language-model analysis failed.)" in lines
    assert "**Agreement**: 2 of 2 live agents (1 unavailable)" in lines
    assert not any("unanimous" in line.lower() for line in lines)


def test_two_live_agents_that_disagree_read_as_a_split_with_the_unavailable_count(tmp_path, monkeypatch):
    result = _with_news_degraded(tech="bull", macro="neutral")
    result.agreement_level = "split"

    lines = _export(tmp_path, monkeypatch, result).read_text().splitlines()

    assert "**Agreement**: Split (2 different positions, 1 unavailable)" in lines


def test_a_degraded_cell_reads_unavailable_and_its_reasoning_is_marked_not_counted(tmp_path, monkeypatch):
    content = _export(tmp_path, monkeypatch, _with_news_degraded("round2_failed")).read_text()

    assert "| News Context | Unavailable | PLACEHOLDER news (not counted in the vote) |" in content
    assert "#### News Context (Unavailable — not counted)" in content
    assert "Round 2 failed; its Round 1 position is shown but not counted." in content
    assert "News Context → Neutral" not in content and "| News Context | → Neutral" not in content


def test_no_unavailable_line_when_every_agent_is_live(tmp_path, monkeypatch):
    content = _export(tmp_path, monkeypatch, _make_debate_result()).read_text()

    assert "Unavailable agents" not in content


def test_a_degraded_report_still_ends_with_the_disclaimer(tmp_path, monkeypatch):
    content = _export(tmp_path, monkeypatch, _with_news_degraded()).read_text()

    assert content.rstrip().endswith(_disclaimer_section("Full disclaimer"))


def test_an_abstention_writes_nothing_and_leaves_an_earlier_report_alone(tmp_path, monkeypatch):
    from app.services.debate.engine import insufficient_data_result

    earlier = _export(tmp_path, monkeypatch, _make_debate_result(date="2026-10-02"))
    before = earlier.read_text()
    refusal = insufficient_data_result(
        "VCB", {"eligible": False, "reasons": ["stale"], "as_of": "2026-10-02", "age_sessions": 21}
    )

    assert _export(tmp_path, monkeypatch, refusal) is None
    assert earlier.read_text() == before
    assert [f.name for f in tmp_path.iterdir()] == ["2026-10-02_VCB.md"]


def test_the_filename_and_title_use_as_of_never_the_system_date(tmp_path, monkeypatch):
    result = _make_debate_result(date="2020-01-03")

    path = _export(tmp_path, monkeypatch, result)

    assert path.name == "2020-01-03_VCB.md"
    assert path.read_text().splitlines()[0] == "# VCB · 2020-01-03"


def test_a_result_without_as_of_is_refused_rather_than_dated_today(tmp_path, monkeypatch):
    result = _make_debate_result()
    result.as_of = None

    with pytest.raises(ValueError, match="as_of"):
        _export(tmp_path, monkeypatch, result)

    assert list(tmp_path.iterdir()) == []


# ===========================================================================
# Verdict labels, language-model note, fixed-text guards (Rules 5 and 6)
# ===========================================================================

EXPECTED_LABELS = {
    "STRONG_BUY_SIGNAL": "Strong bullish lean",
    "BUY_SIGNAL": "Bullish lean",
    "OBSERVE": "Observe",
    "CAUTION_SIGNAL": "Bearish lean",
    "STRONG_CAUTION_SIGNAL": "Strong bearish lean",
    "SPLIT": "Split — no consensus",
    "INSUFFICIENT_DATA": "Insufficient data",
}
LM_NOTE = "Reasoning, key tension and synthesis are written by a language model."
TRANSACTION_VERBS = re.compile(r"\b(buy|sell|hold)\b", re.IGNORECASE)
ENUM_TEXT = re.compile(r"[A-Z]+_SIGNAL\b|INSUFFICIENT_DATA")
CONFIDENCE = re.compile(r"\bconfiden(ce|t)\b", re.IGNORECASE)
REPORTABLE = [v for v in EXPECTED_LABELS if v != "INSUFFICIENT_DATA"]  # an abstention writes no file


def test_every_verdict_value_has_exactly_the_contract_label():
    from typing import get_args

    from app.services.debate.engine import Verdict
    from app.services.debate.export import VERDICT_DESCRIPTIONS

    assert set(get_args(Verdict)) == set(VERDICT_DESCRIPTIONS)
    assert VERDICT_DESCRIPTIONS == EXPECTED_LABELS


@pytest.mark.parametrize("verdict", REPORTABLE)
def test_the_summary_shows_the_display_label_not_the_enum(tmp_path, monkeypatch, verdict):
    content = _export(tmp_path, monkeypatch, _make_debate_result(verdict=verdict)).read_text()

    assert f"**Verdict**: {EXPECTED_LABELS[verdict]}" in content.splitlines()
    assert verdict not in content


def test_the_note_is_the_first_line_under_agent_positions(tmp_path, monkeypatch):
    lines = _export(tmp_path, monkeypatch, _make_debate_result()).read_text().splitlines()

    after = [line for line in lines[lines.index("## Agent Positions") + 1:] if line.strip()]
    assert after[0] == LM_NOTE


@pytest.mark.parametrize("verdict", REPORTABLE)
def test_fixed_report_text_has_no_transaction_verbs_enum_text_or_confidence(tmp_path, monkeypatch, verdict):
    content = _export(tmp_path, monkeypatch, _make_debate_result(verdict=verdict)).read_text()
    body = content.replace(_disclaimer_section("Full disclaimer"), "")

    for guard in (TRANSACTION_VERBS, ENUM_TEXT, CONFIDENCE):
        assert not guard.search(body), guard.pattern


# ===========================================================================
# Typical 5-session move: Summary line and response shape
# ===========================================================================

def _summary_lines(tmp_path, monkeypatch, **range_fields):
    result = _make_debate_result()
    for name, value in range_fields.items():
        setattr(result, name, value)
    content = _export(tmp_path, monkeypatch, result).read_text()
    return content, [line for line in content.splitlines() if line.startswith("**Typical 5-session move**")]


def test_summary_states_the_typical_move_with_its_coverage(tmp_path, monkeypatch):
    content, lines = _summary_lines(tmp_path, monkeypatch, range_5s_pct=5.3, range_coverage=0.68)

    assert lines == [
        "**Typical 5-session move**: ±5.3% (about 2 in 3 recent 5-session moves stayed within this range)"
    ]
    assert "**Volatility range**" not in content


def test_summary_phrases_other_coverages_as_a_percentage(tmp_path, monkeypatch):
    _, lines = _summary_lines(tmp_path, monkeypatch, range_5s_pct=5.3, range_coverage=0.8)

    assert lines == ["**Typical 5-session move**: ±5.3% (about 80% recent 5-session moves stayed within this range)"]


def test_summary_for_an_uncalibrated_stock_claims_no_coverage(tmp_path, monkeypatch):
    _, lines = _summary_lines(tmp_path, monkeypatch, range_5s_pct=5.3, range_coverage=None)

    assert lines == ["**Typical 5-session move**: ±5.3% (coverage not established for this stock)"]
    assert "2 in 3" not in lines[0]  # the Rule 6 disclaimer, which is not this line's to edit, has its own wording


def test_summary_omits_the_line_when_no_band_was_served(tmp_path, monkeypatch):
    content, lines = _summary_lines(
        tmp_path, monkeypatch, range_5s_pct=None, sigma_daily_pct=None, range_coverage=None
    )

    assert lines == []
    assert "Typical 5-session move" not in content and "Volatility range" not in content


def test_summary_never_prints_the_daily_sigma(tmp_path, monkeypatch):
    content, _ = _summary_lines(tmp_path, monkeypatch, range_5s_pct=5.3, sigma_daily_pct=1.77, range_coverage=0.68)

    assert "1.77" not in content


def test_the_debate_json_carries_the_range_fields_and_no_old_name_anywhere(client, monkeypatch):
    import json

    from app.services.debate.engine import AgentPosition

    _loaded(monkeypatch, ELIGIBLE)
    result = _make_debate_result()
    technical = AgentPosition(
        "technical", "bull", ["RSI bullish"], range_5s_pct=4.14, sigma_daily_pct=1.85, range_coverage=0.68
    )
    result.round1["technical"] = result.round2["technical"] = technical
    result.data_as_of, result.data_age_sessions = "2026-10-04", 0

    async def fake_engine_run(self, ticker, eligibility=None, on_stage=None):
        return result

    monkeypatch.setattr("app.services.debate.engine.DebateEngine.run", fake_engine_run)
    monkeypatch.setattr("app.services.debate.export.export_debate_report", lambda r: Path("/tmp/x.md"))

    body = client.post("/tickers/VCB/debate").json()

    expected = {"range_5s_pct": 4.14, "sigma_daily_pct": 1.85, "range_coverage": 0.68}
    for scope in (body, body["round1"]["technical"], body["round2"]["technical"]):
        assert {k: scope[k] for k in expected} == expected
    assert "volatility_range_pct" not in json.dumps(body)


def test_no_band_served_leaves_the_three_fields_null_and_the_debate_complete(client, monkeypatch):
    _loaded(monkeypatch, ELIGIBLE)
    result = _make_debate_result()
    result.range_5s_pct = result.sigma_daily_pct = result.range_coverage = None

    async def fake_engine_run(self, ticker, eligibility=None, on_stage=None):
        return result

    monkeypatch.setattr("app.services.debate.engine.DebateEngine.run", fake_engine_run)
    monkeypatch.setattr("app.services.debate.export.export_debate_report", lambda r: Path("/tmp/x.md"))

    response = client.post("/tickers/VCB/debate")

    assert response.status_code == 200
    body = response.json()
    assert (body["range_5s_pct"], body["sigma_daily_pct"], body["range_coverage"]) == (None, None, None)
    assert body["verdict"] == "BUY_SIGNAL"


# ===========================================================================
# harden-debate-runtime: limits, configuration, progress, report status
# ===========================================================================


def _raising_runner(monkeypatch, error):
    from app.services.debate import runner

    async def run_debate(*args, **kwargs):
        raise error

    monkeypatch.setattr(runner, "run_debate", run_debate)


def test_over_the_cap_the_endpoint_answers_429_with_retry_after_and_the_code(client, monkeypatch):
    from app.services.debate.runner import DebateBusy

    _loaded(monkeypatch, ELIGIBLE)
    _raising_runner(monkeypatch, DebateBusy("Another analysis is already running; try again shortly."))

    resp = client.post("/tickers/VCB/debate")

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "30"
    assert resp.json() == {"detail": "Another analysis is already running; try again shortly.", "code": "debate_busy"}


def test_a_run_past_its_budget_is_a_504_with_the_code(client, monkeypatch):
    from app.services.debate.runner import DebateTimeout

    _loaded(monkeypatch, ELIGIBLE)
    _raising_runner(monkeypatch, DebateTimeout("The analysis did not finish within 180 s."))

    resp = client.post("/tickers/VCB/debate")

    assert resp.status_code == 504
    assert resp.json() == {"detail": "The analysis did not finish within 180 s.", "code": "debate_timeout"}


def test_an_invalid_configuration_is_a_503_that_names_the_variable_and_starts_no_run(client, monkeypatch):
    from app.services.debate import runner

    _loaded(monkeypatch, ELIGIBLE)
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "claude_cli")
    monkeypatch.setenv("DEBATE_LLM_EFFORT", "turbo")
    monkeypatch.setattr(runner, "run_debate", _must_not_be_called)

    resp = client.post("/tickers/VCB/debate")

    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "debate_not_configured"
    assert isinstance(body["detail"], str) and "DEBATE_LLM_EFFORT" in body["detail"]  # a string: the panel shows it


def test_an_unknown_provider_is_a_503_not_a_neutral_200(client, monkeypatch):
    _loaded(monkeypatch, ELIGIBLE)
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "opneai")

    resp = client.post("/tickers/VCB/debate")

    assert resp.status_code == 503 and resp.json()["code"] == "debate_not_configured"


def test_a_missing_credential_is_named_and_its_value_is_not_in_the_response(client, monkeypatch):
    _loaded(monkeypatch, ELIGIBLE)
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-do-not-leak")  # set for the wrong provider
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    resp = client.post("/tickers/VCB/debate")

    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"] and "sk-test-do-not-leak" not in resp.text


def test_the_ticker_checks_still_come_before_the_configuration_check(client, monkeypatch):
    from app.api import debate as debate_mod

    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "opneai")
    monkeypatch.setattr(debate_mod, "get_features_computed", lambda t: 1)
    monkeypatch.setattr(debate_mod, "get_latest_features_row", lambda t: None)
    assert client.post("/tickers/ZZZZZ/debate").status_code == 404

    monkeypatch.setattr(debate_mod, "get_features_computed", lambda t: 0)
    resp = client.post("/tickers/VCB/debate")
    assert resp.status_code == 503 and "code" not in resp.json()  # the feature failure, not the configuration


def test_the_configuration_is_checked_before_eligibility_so_no_row_is_logged_for_a_broken_setup(client, monkeypatch):
    _loaded(monkeypatch, ELIGIBLE)
    monkeypatch.setattr("app.api.debate.assess_eligibility", _must_not_be_called)
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "opneai")

    assert client.post("/tickers/VCB/debate").status_code == 503


@pytest.mark.parametrize("unusable", [None, ""])
def test_an_unavailable_key_tension_is_exported_in_plain_words_not_as_none(tmp_path, monkeypatch, unusable):
    result = _make_debate_result()
    result.synthesis.key_tension = unusable

    content = _export(tmp_path, monkeypatch, result).read_text()

    lines = content.splitlines()
    under_heading = [line for line in lines[lines.index("## Key Tension") + 1:] if line.strip()]
    assert under_heading[0] == "Key tension unavailable: the synthesiser returned no usable text."
    assert "None" not in content


def test_a_usable_key_tension_is_still_exported_as_written(tmp_path, monkeypatch):
    content = _export(tmp_path, monkeypatch, _make_debate_result()).read_text()

    assert "Technical and news are bullish; macro is cautious about index momentum." in content
    assert "Key tension unavailable" not in content


def test_the_response_says_the_report_was_saved_and_names_the_file(client, monkeypatch):
    _loaded(monkeypatch, ELIGIBLE)

    async def fake_engine_run(self, ticker, eligibility=None, on_stage=None):
        return _make_debate_result()

    monkeypatch.setattr("app.services.debate.engine.DebateEngine.run", fake_engine_run)
    monkeypatch.setattr("app.services.debate.export.export_debate_report", lambda r: Path("/tmp/2026-10-04_VCB.md"))

    body = client.post("/tickers/VCB/debate").json()

    assert body["report_saved"] is True and body["report_file"] == "2026-10-04_VCB.md"


def test_a_failed_export_is_still_a_200_and_says_the_report_was_not_saved(client, monkeypatch, caplog):
    _loaded(monkeypatch, ELIGIBLE)

    async def fake_engine_run(self, ticker, eligibility=None, on_stage=None):
        return _make_debate_result()

    def export_fails(result):
        raise OSError("disk full")

    monkeypatch.setattr("app.services.debate.engine.DebateEngine.run", fake_engine_run)
    monkeypatch.setattr("app.services.debate.export.export_debate_report", export_fails)

    resp = client.post("/tickers/VCB/debate")

    assert resp.status_code == 200
    body = resp.json()
    assert body["report_saved"] is False and body["report_file"] is None
    assert body["verdict"] == "BUY_SIGNAL"
    assert "disk full" in caplog.text  # still logged


def test_an_abstention_reports_no_report_saved(client, monkeypatch):
    _loaded(monkeypatch, {"eligible": False, "reasons": ["stale"], "as_of": "2026-09-07", "age_sessions": 21})

    body = client.post("/tickers/VCB/debate").json()

    assert body["report_saved"] is False and body["report_file"] is None


def test_progress_is_idle_for_a_ticker_with_no_run_and_for_an_unknown_one(client):
    for ticker in ("VCB", "ZZZZZ"):
        resp = client.get(f"/tickers/{ticker}/debate/progress")

        assert resp.status_code == 200
        assert resp.json() == {"ticker": ticker, "running": False, "stage": None, "elapsed_ms": None}


@pytest.mark.asyncio
async def test_progress_reports_the_stage_of_a_run_in_flight_then_goes_idle(monkeypatch):
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    _loaded(monkeypatch, ELIGIBLE)
    gate = asyncio.Event()

    async def slow_engine(self, ticker, eligibility=None, on_stage=None):
        on_stage("round1")
        on_stage("round2")
        await gate.wait()
        return _make_debate_result()

    monkeypatch.setattr("app.services.debate.engine.DebateEngine.run", slow_engine)
    monkeypatch.setattr("app.services.debate.export.export_debate_report", lambda r: Path("/tmp/x.md"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        post = asyncio.create_task(ac.post("/tickers/VCB/debate"))
        await asyncio.sleep(0.1)
        running = (await ac.get("/tickers/VCB/debate/progress")).json()
        other = (await ac.get("/tickers/FPT/debate/progress")).json()
        gate.set()
        response = await post
        idle = (await ac.get("/tickers/VCB/debate/progress")).json()

    assert running["running"] is True and running["stage"] == "round2" and running["elapsed_ms"] >= 50
    assert other["running"] is False
    assert response.status_code == 200
    assert idle["running"] is False


def test_known_issue_the_debate_endpoint_runs_for_any_caller_with_no_credentials(client, monkeypatch):
    """Measured, not assumed: docs/KNOWN_ISSUES.md ("`POST /debate` is unauthenticated").

    A request with no Authorization header, no cookie and a foreign Origin starts a run that
    spends the owner's LLM budget. CORS does not prevent it: it only keeps a browser from
    READING the answer, and the run has already happened by then. The protection is the
    loopback bind (and the cap and de-duplication, which guard accidents, not attackers).
    """
    _loaded(monkeypatch, ELIGIBLE)
    runs = []

    async def fake_engine_run(self, ticker, eligibility=None, on_stage=None):
        runs.append(ticker)
        return _make_debate_result()

    monkeypatch.setattr("app.services.debate.engine.DebateEngine.run", fake_engine_run)
    monkeypatch.setattr("app.services.debate.export.export_debate_report", lambda r: Path("/tmp/x.md"))

    resp = client.post("/tickers/VCB/debate", headers={"Origin": "http://evil.example"})

    assert resp.status_code == 200
    assert runs == ["VCB"]
    assert "access-control-allow-origin" not in resp.headers  # a browser on that origin could not read it
