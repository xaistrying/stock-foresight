"""Refresh the held tickers from the vendor, one call each, and report what happened per ticker.

A failed or skipped refresh never stops the brief: the holding is computed from stored prices and
the outcome is shown beside it. vnai's rate limiter ends a call with `SystemExit`, which
`bulk_ingestion` already knows how to recognise; its decision function and its pacing constant are
imported, not copied, so the two cannot drift.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.services import ticker_ingestion
from app.services.bulk_ingestion import DEFAULT_SYMBOLS_PER_MINUTE, _is_rate_limit_exit

logger = logging.getLogger(__name__)

OK, FAILED, NOT_ATTEMPTED = "ok", "failed", "not_attempted"
RATE_LIMIT_DETAIL = "vendor rate limit"
NOT_ATTEMPTED_DETAIL = "vendor limit reached earlier in this run"
SECONDS_BETWEEN_CALLS = 60 / DEFAULT_SYMBOLS_PER_MINUTE


@dataclass(frozen=True)
class RefreshOutcome:
    ticker: str
    state: str  # ok | failed | not_attempted
    detail: str  # a status, an exception class name, or a reason; never vendor text


def refresh_tickers(
    tickers: tuple[str, ...],
    *,
    loader: Callable[..., dict] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[RefreshOutcome, ...]:
    """Call `loader` once per ticker, spaced at bulk_ingestion's rate; one outcome per ticker."""
    loader = loader or ticker_ingestion.load_ticker  # looked up now so a test can replace it
    outcomes: list[RefreshOutcome] = []
    limited = False
    for position, ticker in enumerate(tickers):
        if limited:
            outcomes.append(RefreshOutcome(ticker, NOT_ATTEMPTED, NOT_ATTEMPTED_DETAIL))
            continue
        if position:
            sleep(SECONDS_BETWEEN_CALLS)
        outcome = _refresh_one(ticker, loader)
        limited = outcome.detail == RATE_LIMIT_DETAIL
        outcomes.append(outcome)
    return tuple(outcomes)


def _refresh_one(ticker: str, loader: Callable[..., dict]) -> RefreshOutcome:
    try:
        status = loader(ticker).get("status")
    except SystemExit as exit_request:
        if not _is_rate_limit_exit(exit_request):
            raise  # a genuine exit stays honoured
        return RefreshOutcome(ticker, FAILED, RATE_LIMIT_DETAIL)
    except Exception as error:  # noqa: BLE001 - one ticker's failure must not stop the others
        logger.warning("refresh of %s failed: %s", ticker, type(error).__name__)
        return RefreshOutcome(ticker, FAILED, type(error).__name__)
    if status == "ok":
        return RefreshOutcome(ticker, OK, "ok")
    return RefreshOutcome(ticker, FAILED, str(status))
