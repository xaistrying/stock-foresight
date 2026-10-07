"""The calibrated 5-session range for one ticker, and why it is or is not served.

Eligibility (delisted, stale, gaps, quality flags) is `assess_eligibility`'s business, not this
module's. The one exception is a reason the range does not care about: it reads only closes, so a
null indicator column says nothing about rv5/rv20/rv60 (design.md Decision 8).

Status, first match wins: ineligible (shared service) > model_unavailable > ineligible
(insufficient_history) > range_out_of_bounds > uncalibrated > ok. A ticker with no OHLCV rows raises
TickerNotLoaded before eligibility is consulted.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from app.ml.volatility import (
    MIN_CLOSES,
    band_from_sigma,
    load_model,
    range_hit_rate,
    read_recent_closes,
    sigma_daily_pct_from_closes,
    sigma_out_of_bounds,
)
from app.services.data_eligibility import assess_eligibility

logger = logging.getLogger(__name__)

# The range needs closes only; extend this set if the near_gap guard turns out to withhold too
# many bands (design.md Decision 8, Open Question 1).
RANGE_IGNORED_ELIGIBILITY_REASONS = frozenset({"indicators_missing"})
DISPLAY_DECIMALS = 2  # the API keeps two decimals; the display rounds further


def coverage_phrase(range_coverage: float) -> str:
    """"about 2 in 3" for the 0.68 nominal level, else "about N%" with N to the nearest 5.

    Derived from the artifact's coverage so a retrain at another level cannot leave a wrong
    sentence behind (design.md Decision 12).
    """
    if round(range_coverage, 2) == 0.68:
        return "about 2 in 3"
    return f"about {math.floor(range_coverage * 100 / 5 + 0.5) * 5}%"


class TickerNotLoaded(LookupError):
    """The ticker has no OHLCV rows."""


@dataclass(frozen=True)
class RangeResult:
    ticker: str
    as_of: str
    status: str  # ok | uncalibrated | ineligible | range_out_of_bounds | model_unavailable
    reasons: tuple[str, ...]  # non-empty only when status is ineligible
    sigma_daily_pct: float | None  # daily, never labelled "5 sessions"
    range_5s_pct: float | None  # half-width of the typical 5-session move
    range_k: float | None
    range_coverage: float | None  # None when not measured for this ticker
    range_hit_rate: dict | None  # {rate, n}


def _result(ticker: str, as_of: str, status: str, reasons=(), **fields) -> RangeResult:
    values = dict.fromkeys(
        ("sigma_daily_pct", "range_5s_pct", "range_k", "range_coverage", "range_hit_rate")
    )
    return RangeResult(ticker, as_of, status, tuple(reasons), **{**values, **fields})


def compute_range(ticker: str) -> RangeResult:
    dates, closes = read_recent_closes(ticker)  # the only per-ticker read: at most HISTORY_ROWS closes
    if not len(closes):
        raise TickerNotLoaded(ticker)
    as_of = dates[-1]

    blocking = [r for r in assess_eligibility(ticker)["reasons"] if r not in RANGE_IGNORED_ELIGIBILITY_REASONS]
    if blocking:
        return _result(ticker, as_of, "ineligible", blocking)

    model = load_model()
    if model is None:
        return _result(ticker, as_of, "model_unavailable")

    if len(closes) < MIN_CLOSES:
        logger.error(
            "%s is eligible with %d closes, below the %d the range needs: the eligibility "
            "threshold is too low", ticker, len(closes), MIN_CLOSES,
        )
        return _result(ticker, as_of, "ineligible", ["insufficient_history"])

    sigma = sigma_daily_pct_from_closes(closes, model)
    if sigma is None or sigma_out_of_bounds(sigma):
        shown = round(sigma, DISPLAY_DECIMALS) if sigma is not None and math.isfinite(sigma) else None
        return _result(ticker, as_of, "range_out_of_bounds", sigma_daily_pct=shown)

    calibrated = ticker in model.universe
    return _result(
        ticker, as_of, "ok" if calibrated else "uncalibrated",
        sigma_daily_pct=round(sigma, DISPLAY_DECIMALS),
        range_5s_pct=round(band_from_sigma(sigma, model), DISPLAY_DECIMALS),
        range_k=model.range_k,
        range_coverage=model.range_coverage if calibrated else None,
        range_hit_rate=range_hit_rate(closes, model),
    )
