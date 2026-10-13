"""Whether stored history is already adjusted for an ex-date, read from the stored bars only.

The vendor rewrites history some time after an ex-date. Only an upper bound of that lag is known (at
most 3 sessions on one observed case) and there is no lower bound, so nothing in the brief assumes
history is adjusted: for each cash dividend or count-changing issue it compares the stored ex-day open
with the previous stored close and classifies the result. No vendor call is made; the inputs are the
stored bars, the event and the loaded model.

    expected gap if history is NOT adjusted:  cash  -D / P   (D in the stored price unit, P the previous close)
                                              issue -r / (1 + r)
    observed gap:                             open / P - 1

The check is a heuristic: a large market move on the ex-day can mimic or hide the gap, it cannot see an
event whose bar is not stored, and it says nothing when the expected gap is within an ordinary day's move.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

from app.ml.volatility import HarModel, sigma_daily_pct_from_closes
from app.services.brief.corporate_actions import COUNT_CHANGING_CLASSES, PRICE_UNIT

if TYPE_CHECKING:
    from app.services.brief.feed_source import Event

# A gap smaller than this many daily sigmas of the ticker cannot be told from an ordinary day (Rule 3:
# relative to the ticker's own volatility, not a fixed percent).
UNCLEAR_GAP_SIGMAS = 2.0
_TOLERANCE = 1e-12  # so that exactly half the expected gap is decided by the rule, not by float noise


class AdjustmentStatus(Enum):
    ADJUSTED = "ADJUSTED"
    NOT_YET_ADJUSTED = "NOT_YET_ADJUSTED"
    UNCLEAR = "UNCLEAR"


def adjustment_status(
    event: Event, dates: Sequence[str], opens: Sequence[float], closes: Sequence[float], model: HarModel,
) -> AdjustmentStatus:
    """The status of the history stored for `event`; UNCLEAR whenever the bars or the sigma cannot decide."""
    if event.exright_date is None or event.exright_date.isoformat() not in dates:
        return AdjustmentStatus.UNCLEAR
    index = list(dates).index(event.exright_date.isoformat())
    if index < 1:
        return AdjustmentStatus.UNCLEAR
    previous, opening = float(closes[index - 1]), float(opens[index])
    expected = _expected_gap(event, previous)
    if expected is None or not all(math.isfinite(v) and v > 0 for v in (previous, opening)):
        return AdjustmentStatus.UNCLEAR
    sigma = sigma_daily_pct_from_closes(np.asarray(closes[:index], dtype=float), model)
    if sigma is None or abs(expected) * 100 <= UNCLEAR_GAP_SIGMAS * sigma:
        return AdjustmentStatus.UNCLEAR
    observed = opening / previous - 1
    return AdjustmentStatus.NOT_YET_ADJUSTED if observed <= expected / 2 + _TOLERANCE else AdjustmentStatus.ADJUSTED


def status_of(event: Event, ex_status: Sequence[tuple[Event, AdjustmentStatus]]) -> AdjustmentStatus:
    """The status computed for `event`, UNCLEAR when none was computed (for example no stored bar)."""
    return next((status for known, status in ex_status if known == event), AdjustmentStatus.UNCLEAR)


def _expected_gap(event: Event, previous_close: float) -> float | None:
    """The negative gap an unadjusted history would show on the ex-day, or None for an event not classified."""
    if event.event_code == "DIV" and event.value_per_share and event.value_per_share > 0 and previous_close > 0:
        return -(event.value_per_share / PRICE_UNIT) / previous_close
    name = event.issue_class.name if event.issue_class is not None else None
    if name in COUNT_CHANGING_CLASSES and event.exercise_ratio and event.exercise_ratio > 0:
        return -event.exercise_ratio / (1 + event.exercise_ratio)
    return None
