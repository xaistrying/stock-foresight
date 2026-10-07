"""Debate API endpoints.

POST /tickers/{ticker}/debate
  Runs the multi-agent debate for a loaded ticker and returns a DebateResult as JSON.
  The run itself is the runner's (`app.services.debate.runner`): requests for a ticker
  already running join that run, at most DEBATE_MAX_CONCURRENT_RUNS run at once, and a
  run has a time budget. The runner also writes reports/YYYY-MM-DD_<TICKER>.md; an
  export failure is logged, not surfaced, and the response says whether it was saved
  (`report_saved`, `report_file`).
  Every run, abstentions included, is recorded in the outcome log
  (`backend/data/debate_log.db`): for a run, from the runner's post-run hook, so once
  per run however many requests joined it; for an ineligible ticker, here. The row id
  is `debate_log_id`. A failed write is logged at ERROR and gives `debate_log_id: null`;
  it never fails the response.

An ineligible ticker (delisted, stale, short history, gaps, hard quality flag,
missing indicators) is HTTP 200 with verdict INSUFFICIENT_DATA: no agent runs, no
LLM call, no report file. So is a run in which fewer than two agents are live.

GET /tickers/{ticker}/debate/progress
  `{ticker, running, stage, elapsed_ms}` for the panel. Never starts a run.

Errors (`detail` is always a string; the extra `code` is the machine-readable part):
  404 — ticker not loaded (no feature row)
  503 — feature computation failed for this ticker
  503 `debate_not_configured` — the LLM configuration is invalid or incomplete
  429 `debate_busy` (with Retry-After) — the concurrent-run cap is reached
  504 `debate_timeout` — the run did not finish within its budget
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.services.data_eligibility import assess_eligibility
from app.services.debate import runner
from app.services.debate.engine import DebateResult, insufficient_data_result
from app.services.feature_rows import get_features_computed, get_latest_features_row
from app.services.debate.llm_client import DebateConfigError, check_debate_config
from app.services.debate.outcome_log import log_debate_run

router = APIRouter()
logger = logging.getLogger(__name__)


def _serialise_result(result: DebateResult, report_file: str | None = None) -> dict:
    """Convert DebateResult dataclass to a JSON-serialisable dict.

    `debate_log_id` is not here: the post-run hook adds it (and the abstention path below).
    """
    def pos_to_dict(pos):
        return {
            "agent_id": pos.agent_id,
            "stance": pos.stance,
            "reasoning": pos.reasoning,
            "range_5s_pct": pos.range_5s_pct,
            "sigma_daily_pct": pos.sigma_daily_pct,
            "range_coverage": pos.range_coverage,
            "degraded_reason": pos.degraded_reason,
        }

    return {
        "ticker": result.ticker,
        "as_of": result.as_of,
        "data_as_of": result.data_as_of,
        "data_age_sessions": result.data_age_sessions,
        "verdict": result.verdict,
        "agreement_level": result.agreement_level,
        "eligibility": result.eligibility,
        "agents_degraded": result.agents_degraded,
        "round1": {k: pos_to_dict(v) for k, v in result.round1.items()},
        "round2": {k: pos_to_dict(v) for k, v in result.round2.items()},
        "synthesis": {
            "verdict": result.synthesis.verdict,
            "agreement_level": result.synthesis.agreement_level,
            "key_tension": result.synthesis.key_tension,
            "reasoning": result.synthesis.reasoning,
        },
        "range_5s_pct": result.range_5s_pct,
        "sigma_daily_pct": result.sigma_daily_pct,
        "range_coverage": result.range_coverage,
        "duration_ms": result.duration_ms,
        "report_saved": report_file is not None,
        "report_file": report_file,
    }


def _log_run(result: DebateResult) -> dict:
    """Record the run; never raises, never silent (a null id is the visible signal).

    Blocking SQLite: the runner calls a sync hook in a worker thread.
    """
    try:
        return {"debate_log_id": log_debate_run(result)}
    except Exception:
        logger.error(
            "Debate log write failed for %s as_of=%s", result.ticker, result.data_as_of, exc_info=True
        )
        return {"debate_log_id": None}


def record_run(context: runner.RunContext) -> dict:
    """Post-run hook: one outcome-log row per run, whatever number of requests joined it."""
    return _log_run(context.result)


runner.register_post_run_hook(record_run)


def _problem(status: int, detail: str, code: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail, "code": code}, headers=headers)


@router.post("/tickers/{ticker}/debate")
async def run_debate(ticker: str):
    """Run the multi-agent debate for a ticker and return the DebateResult."""
    # Blocking SQLite: off the event loop.
    if await asyncio.to_thread(get_features_computed, ticker) == 0:
        raise HTTPException(
            status_code=503,
            detail="Feature computation failed for this ticker",
        )

    if await asyncio.to_thread(get_latest_features_row, ticker) is None:
        raise HTTPException(
            status_code=404,
            detail="Ticker has not been loaded",
        )

    # A broken setup is an error, not a run: unchecked, every agent would fail and the
    # answer would be HTTP 200 with neutral agents.
    try:
        check_debate_config()
    except DebateConfigError as exc:
        return _problem(503, str(exc), "debate_not_configured")

    # Before any agent or LLM call: a verdict from stale or partial data is worse
    # than none. The answer is "not enough data", not an error, so it is a 200.
    eligibility = await asyncio.to_thread(assess_eligibility, ticker)  # blocking sqlite, ~0.08 s
    if not eligibility["eligible"]:
        abstention = insufficient_data_result(ticker, eligibility)
        logged = await asyncio.to_thread(_log_run, abstention)
        return JSONResponse(content={**_serialise_result(abstention), **logged})

    try:
        payload = await runner.run_debate(ticker, eligibility, _serialise_result)
    except runner.DebateBusy as exc:
        return _problem(429, str(exc), "debate_busy", {"Retry-After": str(exc.retry_after)})
    except runner.DebateTimeout as exc:
        return _problem(504, str(exc), "debate_timeout")
    except DebateConfigError as exc:  # raised inside the run: the preflight above should have caught it
        return _problem(503, str(exc), "debate_not_configured")
    return JSONResponse(content=payload)


@router.get("/tickers/{ticker}/debate/progress")
async def debate_progress(ticker: str):
    """The stage of the run in flight for `ticker`, or `running: false`. Never 404."""
    return runner.progress(ticker)
