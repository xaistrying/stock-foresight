"""THE WEEK JUST ENDED: the move over the last 5 stored sessions and the range that was issued for it.

The week is `dates[-5] .. dates[-1]`; the range that covered it was issued on the bar before it,
`dates[-6]`. The verdict is computed on stored closes in log-return space (the measure the band is
fitted to), so a constant rescale of the closes cannot change it. The log return is used only for
that comparison and is never shown (Rule 2).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.ml.volatility import HORIZON_SESSIONS
from app.services.brief.issued_log import IssuedEntry

SESSIONS = HORIZON_SESSIONS  # Rule 1: one source for the horizon


@dataclass(frozen=True)
class WeekFacts:
    first_date: str  # dates[-5]
    last_date: str  # dates[-1]
    base_date: str  # dates[-6], the bar the previous range was issued on
    base_close: float
    last_close: float
    move_pct: float  # simple percent, close ratio - 1
    kind: str  # first | no_match | no_band | band
    latest_on_file: str | None = None  # kind == no_match
    prior_status: str | None = None  # kind == no_band
    band_pct: float | None = None  # kind == band
    band_lo: float | None = None
    band_hi: float | None = None
    inside: bool | None = None
    prior_provisional: bool = False


def week_facts(dates: Sequence[str], closes: Sequence[float], entries: tuple[IssuedEntry, ...]) -> WeekFacts | None:
    """The week over the last 5 stored sessions, or None with fewer than 6 closes.

    Only entries issued for a bar strictly before the last bar count, so a re-run on the same bar reads
    what an earlier week said, never its own entry.
    """
    if len(closes) < SESSIONS + 1:
        return None
    base_date, base_close, last_close = dates[-SESSIONS - 1], float(closes[-SESSIONS - 1]), float(closes[-1])
    common = dict(
        first_date=dates[-SESSIONS], last_date=dates[-1], base_date=base_date, base_close=base_close,
        last_close=last_close, move_pct=(last_close / base_close - 1) * 100,
    )
    dated = [entry for entry in entries if entry.as_of and entry.as_of < dates[-1]]
    if not dated:
        return WeekFacts(kind="first", **common)
    matches = [entry for entry in dated if entry.as_of == base_date]
    if not matches:
        return WeekFacts(kind="no_match", latest_on_file=max(entry.as_of for entry in dated), **common)
    # prefer an entry with a band, then a post-close one; ties go to the later line (entries arrive oldest first)
    issued = sorted(matches, key=lambda e: (e.band_pct is not None, not e.provisional))[-1]
    if issued.band_pct is None:
        return WeekFacts(kind="no_band", prior_status=issued.status, prior_provisional=issued.provisional, **common)
    inside = abs(math.log(last_close / base_close)) * 100 <= issued.band_pct
    return WeekFacts(
        kind="band", band_pct=issued.band_pct, band_lo=issued.band_lo, band_hi=issued.band_hi, inside=inside,
        prior_provisional=issued.provisional, **common,
    )
