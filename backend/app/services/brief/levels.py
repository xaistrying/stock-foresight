"""The investor's levels checked against the last stored close, and the re-adjusted-close detector.

The tool's only judgement is reached or not reached and the distance; there is no threshold of its
own (Rule 3) and no word about what to do (Rule 6). Strict comparison: a close equal to the level is
not reached.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.services.brief.holdings import Level
from app.services.brief.issued_log import IssuedEntry

READJUSTED_TOLERANCE = 0.005  # half the displayed price unit: quantisation, not a move threshold


@dataclass(frozen=True)
class LevelCheck:
    level: Level
    reached: bool | None  # None when there is no stored close
    distance_pct: float | None  # |close - price| / close * 100


@dataclass(frozen=True)
class Readjusted:
    date: str
    stored: float  # the close stored for that date now
    issued: float  # the close the earlier brief printed


def check_level(level: Level, close: float | None) -> LevelCheck:
    if close is None:
        return LevelCheck(level, None, None)
    reached = close < level.price if level.comparator == "below" else close > level.price
    return LevelCheck(level, reached, abs(close - level.price) / close * 100)


def check_levels(levels: tuple[Level, ...], close: float | None) -> tuple[LevelCheck, ...]:
    return tuple(check_level(level, close) for level in levels)


def detect_readjusted(entries: tuple[IssuedEntry, ...], dates: Sequence[str], closes: Sequence[float]) -> Readjusted | None:
    """Compare the latest earlier logged close with the stored close for the same date.

    "Earlier" means issued for a bar strictly before the last bar, plus a provisional entry for the last
    bar itself (a provisional close revised after the market closed is the right warning). A final entry
    for the last bar is never compared: a re-run on the same bar must read what an earlier run read.
    Sees only an adjustment that has already reached the stored prices.
    """
    if not len(dates):
        return None
    last = dates[-1]
    candidates = [
        e for e in entries
        if e.as_of and e.close is not None and (e.as_of < last or (e.as_of == last and e.provisional))
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda entry: (entry.as_of, not entry.provisional))  # the post-close entry wins a date
    if latest.as_of not in dates:
        return None
    stored = float(closes[list(dates).index(latest.as_of)])
    if abs(stored - latest.close) <= READJUSTED_TOLERANCE:
        return None
    return Readjusted(latest.as_of, stored, latest.close)
