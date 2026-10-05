"""Debate API endpoint.

POST /tickers/{ticker}/debate
  Runs the multi-agent debate for a loaded ticker.
  Returns a DebateResult as JSON.
  Also writes reports/YYYY-MM-DD_<TICKER>.md (export failure is logged, not surfaced).

Errors:
  404 — ticker not loaded (no feature row)
  503 — feature computation failed for this ticker
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.predictions import get_features_computed, get_latest_features_row
from app.services.debate.engine import DebateEngine

router = APIRouter()
logger = logging.getLogger(__name__)


def _serialise_result(result) -> dict:
    """Convert DebateResult dataclass to a JSON-serialisable dict."""
    def pos_to_dict(pos):
        return {
            "agent_id": pos.agent_id,
            "stance": pos.stance,
            "reasoning": pos.reasoning,
            "volatility_range_pct": pos.volatility_range_pct,
        }

    return {
        "ticker": result.ticker,
        "as_of": result.as_of,
        "verdict": result.verdict,
        "agreement_level": result.agreement_level,
        "round1": {k: pos_to_dict(v) for k, v in result.round1.items()},
        "round2": {k: pos_to_dict(v) for k, v in result.round2.items()},
        "synthesis": {
            "verdict": result.synthesis.verdict,
            "agreement_level": result.synthesis.agreement_level,
            "key_tension": result.synthesis.key_tension,
            "reasoning": result.synthesis.reasoning,
        },
        "volatility_range_pct": result.volatility_range_pct,
        "duration_ms": result.duration_ms,
    }


@router.post("/tickers/{ticker}/debate")
async def run_debate(ticker: str):
    """Run the multi-agent debate for a ticker and return the DebateResult."""
    features_state = get_features_computed(ticker)
    if features_state == 0:
        raise HTTPException(
            status_code=503,
            detail="Feature computation failed for this ticker",
        )

    row = get_latest_features_row(ticker)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Ticker has not been loaded",
        )

    engine = DebateEngine()
    result = await engine.run(ticker)

    # Export to .md — failure is logged, never blocks the response
    try:
        from app.services.debate.export import export_debate_report
        export_debate_report(result)
    except Exception as exc:
        logger.warning("Debate report export failed for %s: %s", ticker, exc)

    return JSONResponse(content=_serialise_result(result))
