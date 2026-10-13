"""Sections that need the investor's own data: the position block, the shares sentence, YOUR LEVELS,
HOLDINGS LISTED. Pure functions returning a tuple of lines; none of them runs in the redacted copy.
"""

from __future__ import annotations

from collections.abc import Callable

from app.services.brief import wording
from app.services.brief.facts import MarketFacts
from app.services.brief.holdings import Holding, Level
from app.services.brief.levels import LevelCheck

Lines = tuple[str, ...]
_THOUSAND = 1000  # prices are in thousand VND, amounts are shown in millions
# The one place the investor's own text is printed: a level line starts with the text and then this label. The final text
# scan exempts the investor's words by this position, never by substring, so a short text cannot hide a tool word.
LEVEL_LABEL = " (you wrote this on "


def ticker_header(holding: Holding) -> Lines:
    bought = holding.purchase_date.isoformat() if holding.purchase_date else "not entered"
    return (
        f"--- {holding.ticker} · {holding.shares:,} shares · cost {wording.fmt_price(holding.cost)} · bought {bought} ---",
    )


def position_lines(holding: Holding, facts: MarketFacts) -> Lines:
    as_entered = wording.AS_ENTERED_LINE
    if holding.shares_as_of:
        as_entered += f" Shares as of {holding.shares_as_of.isoformat()}."
    if facts.close is None:
        return ("Value and gain/loss not shown: no stored close.", as_entered)
    value = holding.shares * facts.close / _THOUSAND
    gain = holding.shares * (facts.close - holding.cost) / _THOUSAND
    gain_pct = (facts.close / holding.cost - 1) * 100
    return (
        f"Value {wording.fmt_millions(value)}; gain/loss on price against your cost "
        f"{wording.fmt_signed_millions(gain)} ({wording.fmt_signed_pct(gain_pct)}).",
        as_entered,
    )


def range_amount_lines(holding: Holding, facts: MarketFacts) -> Lines:
    if facts.band_pct is None or facts.close is None:
        return ()
    amount = holding.shares * facts.close * facts.band_pct / 100 / _THOUSAND
    return (f"On your {holding.shares:,} shares: about ±{amount:,.2f}M VND.",)


def readjusted_levels_lines(holding: Holding, facts: MarketFacts) -> Lines:
    return (wording.READJUSTED_LEVELS_NOTE,) if holding.levels and facts.readjusted else ()


def levels_lines(
    checks: tuple[LevelCheck, ...], close: float | None, notes: Callable[[Level], Lines] | None = None,
) -> Lines:
    """The investor's words verbatim, labelled as theirs; the tool's words are reached or not and the distance.

    `notes` gives separate lines printed directly beneath a level's own line (never inside it): the level line
    is identical with or without them.
    """
    body = tuple(
        line for check in checks for line in (_level_line(check, close), *(notes(check.level) if notes else ()))
    ) or (wording.LEVELS_NONE,)
    return (wording.LEVELS_HEADING, *body, wording.LEVELS_CLOSING)


def _level_line(check: LevelCheck, close: float | None) -> str:
    level = check.level
    prefix = f"{one_line(level.text)}{LEVEL_LABEL}{level.entered.isoformat()}): "
    if check.reached is None:
        return prefix + wording.LEVELS_NOT_CHECKED + "."
    distance = wording.fmt_distance_pct(check.distance_pct)
    if check.reached:
        return (
            f"{prefix}REACHED. The last close, {wording.fmt_price(close)}, is {level.comparator} it, by {distance}."
        )
    return f"{prefix}not reached; the level {wording.fmt_price(level.price)} is {distance} {level.comparator} the close."


def one_line(text: str) -> str:
    """The investor's text on one line: control characters become spaces."""
    return "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in text)


def holdings_listed_lines(pairs: tuple[tuple[Holding, MarketFacts], ...]) -> Lines:
    """Weights and the upper bound; only with two or more holdings, and only holdings-derived."""
    if len(pairs) < 2:
        return ()
    values = {h.ticker: h.shares * f.close for h, f in pairs if f.close is not None}
    total = sum(values.values())
    weights = {ticker: value / total for ticker, value in values.items()} if total > 0 else {}
    entries = ", ".join(
        f"{h.ticker} {wording.fmt_weight(weights[h.ticker] * 100)}" if h.ticker in weights
        else f"{h.ticker} no weight (no stored close)"
        for h, _ in pairs
    )
    # Rule 4: only a range whose hit-rate was measured goes into the figure; an uncalibrated band is left out and said so
    ranged = [
        (weights[h.ticker], f.band_pct) for h, f in pairs
        if f.band_pct is not None and f.calibrated is True and h.ticker in weights
    ]
    unmeasured = sum(1 for h, f in pairs if f.band_pct is not None and f.calibrated is not True and h.ticker in weights)
    left_out = len(pairs) - len(ranged) - unmeasured
    lines = [f"HOLDINGS LISTED ({len(pairs)}): {entries}"]
    if ranged:
        bound = sum(weight * band for weight, band in ranged)
        lines.append(
            "If every holding moved to the edge of its own range in the same direction, the listed holdings would "
            f"move about {bound:.1f}% (an upper bound for the usual ranges, not a forecast; larger moves are possible)."
        )
    else:
        lines.append("no listed holding has a range, so no upper bound is shown.")
    if unmeasured:
        plural = unmeasured != 1
        lines.append(
            f"{unmeasured} listed holding{'s' if plural else ''} {'have' if plural else 'has'} a range whose "
            f"reliability has not been measured and {'are' if plural else 'is'} left out of this figure."
        )
    if left_out:
        plural = left_out != 1
        lines.append(
            f"{left_out} listed holding{'s' if plural else ''} {'have' if plural else 'has'} no range "
            f"and {'are' if plural else 'is'} left out of this figure."
        )
    return tuple(lines)
