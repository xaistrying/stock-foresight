"""Assemble the brief from an ordered list of section functions.

Each section is `(TickerReport, redact) -> tuple[str, ...]`. A later change adds a module with its own
sections and one entry in `TICKER_SECTIONS`, or one counter in `TRIGGER_COUNTERS`; nothing here or in
the existing sections is rewritten. In the redacted copy only market-facts sections run: the
investor's sections are not called, and fixed lines stand in for them.

Before anything is shown, one last pass scans every line the tool wrote (never the investor's own
words) for transaction words, Confidence and Market Sentiment, and fails closed with the line number.
Quoted third-party text (announcement titles and counterparty names, between U+201C and U+201D, produced only
by `third_party_text.third_party()`) is the one other thing the scan does not read; a line that still holds
one of those two characters once the well-formed spans are removed is rejected, so an unpaired quote cannot
hide anything.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from app.services.brief import sections_holding as holding_sections
from app.services.brief import sections_company as company_sections
from app.services.brief import sections_holding_dividends as holding_dividends
from app.services.brief import sections_market as market_sections
from app.services.brief import sections_market_dividends as market_dividends
from app.services.brief import wording, wording_company
from app.services.brief.facts import MarketFacts, with_staleness
from app.services.brief.holdings import Holding
from app.services.brief.levels import check_levels
from app.services.brief.third_party_text import CLOSE, OPEN, strip_spans
from app.services.brief.wording import TriggerCount

logger = logging.getLogger(__name__)
Lines = tuple[str, ...]


class BriefTextGuardError(Exception):
    """A line the tool wrote failed the final text scan. The message names the line number only."""


@dataclass(frozen=True)
class TickerReport:
    holding: Holding
    facts: MarketFacts


SectionFn = Callable[[TickerReport, bool], Lines]
TriggerCounter = Callable[[tuple[TickerReport, ...]], TriggerCount | None]  # None: this count is not printed


def joins_next(section: SectionFn) -> SectionFn:
    """Mark a section whose lines sit directly above the next section's, with no blank line between."""
    section.joins_next = True  # type: ignore[attr-defined]
    return section


@joins_next
def _header(report: TickerReport, redact: bool) -> Lines:
    if redact:
        return market_sections.ticker_header(report.facts)
    return holding_sections.ticker_header(report.holding)


def _position(report: TickerReport, redact: bool) -> Lines:
    lines = market_sections.close_lines(report.facts)
    if not redact:
        lines += holding_sections.position_lines(report.holding, report.facts)
    lines += market_sections.note_lines(report.facts) + market_sections.readjusted_lines(report.facts)
    if not redact:
        lines += holding_sections.readjusted_levels_lines(report.holding, report.facts)
    return lines


def _week(report: TickerReport, redact: bool) -> Lines:
    return market_sections.week_lines(report.facts, with_previous_range=not redact)


def _next_five(report: TickerReport, redact: bool) -> Lines:
    lines = market_sections.next_five_lines(report.facts) + market_dividends.window_lines(report.facts)
    if redact:
        return lines
    return lines + holding_sections.range_amount_lines(report.holding, report.facts) + holding_dividends.update_entries_lines(report.facts)


def _dividends(report: TickerReport, redact: bool) -> Lines:
    lines = market_dividends.dividends_lines(report.facts)
    if redact or not lines:
        return lines
    return lines + holding_dividends.since_purchase_lines(report.holding, report.facts)


def _company(report: TickerReport, redact: bool) -> Lines:
    """The COMPANY block; a failure prints one visible line and leaves the holding's other sections (levels included) alone."""
    try:
        return company_sections.company_lines(report.facts, redact=redact)
    except Exception as error:  # noqa: BLE001 - one block must not take the holding's levels down with it
        logger.exception("building the COMPANY block for %s failed", report.facts.ticker)
        return (wording_company.COMPANY_FAILED.format(error=type(error).__name__),)


def _levels(report: TickerReport, redact: bool) -> Lines:
    if redact:
        return (f"YOUR LEVELS: {wording.REDACTED_LEVELS_LINE}",)
    checks = check_levels(report.holding.levels, report.facts.close)
    return holding_sections.levels_lines(
        checks, report.facts.close, notes=lambda level: holding_dividends.level_note_lines(level, report.facts),
    )


TICKER_SECTIONS: tuple[SectionFn, ...] = (_header, _position, _week, _next_five, _dividends, _company, _levels)


def level_trigger_count(reports: tuple[TickerReport, ...]) -> TriggerCount:
    """The investor's levels checked against a stored close and reached, across all holdings."""
    checks = [c for r in reports for c in check_levels(r.holding.levels, r.facts.close)]
    unchecked = sum(c.reached is None for c in checks)
    note = wording.unchecked_levels_note(unchecked) if unchecked else ""
    return TriggerCount(wording.LEVELS_REACHED_LABEL, sum(c.reached is True for c in checks), note)


def _facts(reports: tuple[TickerReport, ...]) -> tuple[MarketFacts, ...]:
    return tuple(r.facts for r in reports)


def trades_trigger_count(reports: tuple[TickerReport, ...]) -> TriggerCount | None:
    """Registered trades by a major shareholder or insider that are new since the last brief, across all holdings."""
    return company_sections.trades_trigger_count(_facts(reports))


def issues_trigger_count(reports: tuple[TickerReport, ...]) -> TriggerCount | None:
    """Share issues or capital changes that are new since the last brief, across all holdings."""
    return company_sections.issues_trigger_count(_facts(reports))


def unchecked_trigger_count(reports: tuple[TickerReport, ...]) -> TriggerCount | None:
    """Holdings whose announcements were not checked; None (not printed) when every holding was checked."""
    return company_sections.unchecked_trigger_count(_facts(reports))


# A later change appends its own counter here; the line's format, position and word guard are not edited.
TRIGGER_COUNTERS: tuple[TriggerCounter, ...] = (
    level_trigger_count, trades_trigger_count, issues_trigger_count, unchecked_trigger_count,
)


def build_brief(
    reports: tuple[TickerReport, ...],
    *,
    redact: bool,
    now: datetime,
    sections: tuple[SectionFn, ...] = TICKER_SECTIONS,
    trigger_counters: tuple[TriggerCounter, ...] = TRIGGER_COUNTERS,
) -> Lines:
    """The brief as a tuple of lines: head, one block per holding, footer, disclaimer."""
    facts = with_staleness(tuple(r.facts for r in reports), now)
    reports = tuple(replace(r, facts=f) for r, f in zip(reports, facts))
    _check_disclaimer(facts)

    lines: list[str] = [market_sections.title_line(facts)]
    if any(f.provisional for f in facts):
        lines.append(wording.PROVISIONAL_WARNING)
    if redact:
        lines.append(wording.REDACTED_NOTICE)
    else:
        counts = tuple(c for c in (counter(reports) for counter in trigger_counters) if c is not None)
        lines.append(wording.triggers_line(counts))
    lines += market_sections.refresh_lines(facts)
    lines += [wording.UNITS_LINE, wording.HEADER_SENTENCE]
    if not redact:
        listed = holding_sections.holdings_listed_lines(tuple((r.holding, r.facts) for r in reports))
        lines += ("", *listed) if listed else ()
    for report in reports:
        lines += ["", *_guarded_block(report, redact, sections)]
    lines += ["", wording.FOOTER, wording.BRIEF_DISCLAIMER]
    _scan(lines, () if redact else _investor_texts(reports))
    return tuple(lines)


def _check_disclaimer(facts: tuple[MarketFacts, ...]) -> None:
    """The disclaimer says "About 2 weeks in 3": any coverage seen in the facts must agree, or nothing is built."""
    coverages = {f.range_coverage for f in facts if f.range_coverage is not None}
    coverages |= {f.model.range_coverage for f in facts if f.model is not None}
    for coverage in sorted(coverages):
        wording.disclaimer_for(coverage)


def _guarded_block(report: TickerReport, redact: bool, sections: tuple[SectionFn, ...]) -> Lines:
    """One holding's block; a failure prints a visible line for that holding only."""
    try:
        return _ticker_block(report, redact, sections)
    except Exception as error:  # noqa: BLE001 - one holding must not take the others down
        logger.exception("building the block for %s failed", report.facts.ticker)
        return (f"--- {report.facts.ticker} ---", f"could not build this holding: {type(error).__name__}")


def _ticker_block(report: TickerReport, redact: bool, sections: tuple[SectionFn, ...]) -> Lines:
    lines: list[str] = []
    attach = False  # the previous section asked to sit directly above this one
    for section in sections:
        part = section(report, redact)
        if not part:
            continue
        if lines and not attach:
            lines.append("")
        lines += part
        attach = getattr(section, "joins_next", False)
    return tuple(lines)


def _investor_texts(reports: tuple[TickerReport, ...]) -> tuple[str, ...]:
    texts = {t for r in reports for level in r.holding.levels for t in (level.text, holding_sections.one_line(level.text))}
    return tuple(sorted(texts, key=len))  # shortest first: the scan tries the one that exempts the least


def _tool_part(line: str, investor_texts: tuple[str, ...]) -> str:
    """The part of a line the tool wrote. The investor's own words are exempt only where a level line prints them, at the
    start of the line and followed by the level label (never by substring: a one-letter text would hide a tool word)."""
    for text in investor_texts:
        if line.startswith(text + holding_sections.LEVEL_LABEL):
            return line[len(text):]
    return line


def _scan(lines: list[str], investor_texts: tuple[str, ...]) -> None:
    for number, line in enumerate(lines, start=1):
        tool_text = strip_spans(_tool_part(line, investor_texts))  # quoted third-party text: the other thing the scan does not read
        if OPEN in tool_text or CLOSE in tool_text or wording.tool_text_violations(tool_text) or (
            line.startswith(wording.TRIGGERS_PREFIX) and wording.judgement_words_in(line)
        ):
            raise BriefTextGuardError(f"the brief text guard rejected line {number}; nothing was shown")
