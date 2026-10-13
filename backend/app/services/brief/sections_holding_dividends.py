"""Dividend lines that need the investor's own entries: the lists since the purchase date, the "update your
entries" line and the notes under each level. None of them runs in a redacted copy.

Pure functions from a `Holding`, `MarketFacts` and the level's entry date to tuples of lines. No share
count, cost, amount on a share count or total is computed, and the investor's own text is never used.
"""

from __future__ import annotations

from datetime import date

from app.services.brief import dividend_lines_holding as dh
from app.services.brief.facts import MarketFacts
from app.services.brief.holdings import Holding, Level
from app.services.brief.sections_market_dividends import window_events

Lines = tuple[str, ...]


def since_purchase_lines(holding: Holding, facts: MarketFacts) -> Lines:
    if facts.feed is None or facts.last_bar is None:
        return ()
    return dh.since_purchase_lines(facts.feed, holding.purchase_date, date.fromisoformat(facts.last_bar))


def update_entries_lines(facts: MarketFacts) -> Lines:
    return dh.update_entries_lines(window_events(facts))


def level_note_lines(level: Level, facts: MarketFacts) -> Lines:
    if facts.last_bar is None:
        return ()
    return dh.level_note_lines(facts.feed, facts.ex_status, level.entered, date.fromisoformat(facts.last_bar))
