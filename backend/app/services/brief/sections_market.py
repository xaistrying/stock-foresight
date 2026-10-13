"""Sections that render market facts only: the header, the close, the week, the next 5 sessions, notes.

Pure functions from `MarketFacts` to a tuple of lines. Nothing here receives the investor's data, so
the redacted copy can be built from these alone.
"""

from __future__ import annotations

from app.services.brief import sections_market_dividends as dividends
from app.services.brief import wording
from app.services.brief.facts import MarketFacts
from app.services.brief.timing import STALE_AFTER_CALENDAR_DAYS
from app.services.brief.week import WeekFacts

Lines = tuple[str, ...]


# --- the top of the brief ---------------------------------------------------------------------------
def title_line(facts: tuple[MarketFacts, ...]) -> str:
    newest = _newest_bar(facts)
    if newest is None:
        return wording.TITLE_NO_PRICES
    return f"WEEKLY CHECK · newest last bar {newest} · covers the 5 sessions after {newest}"


def refresh_lines(facts: tuple[MarketFacts, ...]) -> Lines:
    """The refresh and last-bar line; a ticker with its own last bar is named, never folded into one date."""
    if all(f.refresh == "skipped" for f in facts):
        head = wording.NOT_REFRESHED_LINE
    else:
        problems = [f"{f.ticker} ({_refresh_problem(f)})" for f in facts if f.refresh in ("failed", "not_attempted")]
        head = f"Prices refreshed this run, except {', '.join(problems)}." if problems else wording.REFRESHED_LINE
    return (f"{head} {_last_bar_sentence(facts)}",)


def _last_bar_sentence(facts: tuple[MarketFacts, ...]) -> str:
    bars = {f.last_bar for f in facts}
    if len(bars) == 1 and None not in bars:
        return wording.LAST_BAR_ALL.format(date=next(iter(bars)))
    return "Last bar: " + "; ".join(f"{f.ticker} {f.last_bar or 'none stored'}" for f in facts) + "."


def _refresh_problem(facts: MarketFacts) -> str:
    state = "failed" if facts.refresh == "failed" else "not attempted"
    return f"{state}: {facts.refresh_detail}" if facts.refresh_detail else state


# --- one ticker -------------------------------------------------------------------------------------
def ticker_header(facts: MarketFacts) -> Lines:
    return (f"--- {facts.ticker} ---",)


def close_lines(facts: MarketFacts) -> Lines:
    if facts.close is None:
        return ()
    mark = f", {wording.PROVISIONAL_MARK}" if facts.provisional else ""
    return (f"Close {wording.fmt_price(facts.close)} ({facts.last_bar}{mark})",)


def note_lines(facts: MarketFacts) -> Lines:
    """A failed or skipped refresh, and any staleness, stated per ticker."""
    lines: list[str] = []
    if facts.refresh in ("failed", "not_attempted"):
        where = f"last bar {facts.last_bar}" if facts.last_bar else "no stored prices"
        lines.append(f"Prices: refresh failed; {where} ({_refresh_problem(facts)}).")
        lines.append(wording.STALE_REFRESH_WARNING)
    if "behind_newest" in facts.stale_reasons:
        lines.append(wording.stale_behind_warning(facts.last_bar))
    if "old" in facts.stale_reasons:
        lines.append(wording.stale_old_warning(facts.last_bar, STALE_AFTER_CALENDAR_DAYS))
    return tuple(lines)


def readjusted_lines(facts: MarketFacts) -> Lines:
    note = facts.readjusted
    if note is None:
        return ()
    line = (
        f"NOTE: the close stored for {note.date} is now {wording.fmt_price(note.stored)}; the brief issued then "
        f"showed {wording.fmt_price(note.issued)}. Stored prices may have been re-adjusted (for example after a "
        f"dividend or share issue). {wording.READJUSTED_LIMIT}"
    )
    return (line, *dividends.readjusted_explanation(facts))  # a feed ex-date that would explain it, if there is one


# --- the week just ended ----------------------------------------------------------------------------
def week_lines(facts: MarketFacts, *, with_previous_range: bool = True) -> Lines:
    """The week and, unless `with_previous_range` is False, what the issued log says about last week's range.

    Everything read from the log (first brief, last week's range, the comparison, the recomputed range of a
    week-1 ticker) reveals how long a ticker has been in the investor's briefs, so the redacted copy leaves
    all of it out. Ex-dates from the feed change the block only through `dividends.week_extras`: a
    one-event ADJUSTED week prints the combined line instead of the move line (and, with the log, instead of
    the inside/outside sentence), and notes follow for the other cases.
    """
    week = facts.week
    if week is None:
        return (wording.WEEK_HEADING, wording.WEEK_UNAVAILABLE)
    extras = dividends.week_extras(facts, with_previous_range=with_previous_range)
    move = (
        f"Move: {wording.fmt_signed_pct(week.move_pct)} ({wording.fmt_price(week.base_close)} on {week.base_date} "
        f"-> {wording.fmt_price(week.last_close)} on {week.last_date})."
    )
    heading = f"{wording.WEEK_HEADING} ({week.first_date} to {week.last_date})"
    head = (heading, *(extras.combined or (move,)))
    if not with_previous_range:
        return (*head, *extras.notes)
    previous = () if extras.replaces_previous_range else (_previous_range_sentence(week),)
    return (*head, *previous, wording.WEEK_COMPARE_LIMIT, *extras.notes, *extras.week_one)


def _previous_range_sentence(week: WeekFacts) -> str:
    if week.kind == "first":
        return f"{wording.FIRST_BRIEF}."
    if week.kind == "no_match":
        return (
            f"no range was issued for the week starting after {week.base_date}; "
            f"the latest one on file is for {week.latest_on_file}."
        )
    if week.kind == "no_band":
        return f"last week's brief gave no range ({wording.status_phrase(week.prior_status or '')})."
    edges = (
        f" ({wording.fmt_price(week.band_lo)} to {wording.fmt_price(week.band_hi)})" if week.band_lo is not None else ""
    )
    verdict = "inside" if week.inside else "outside"
    provisional = f" {wording.PROVISIONAL_ISSUE_NOTE}" if week.prior_provisional else ""
    return f"Last week's range was {wording.fmt_band(week.band_pct)}{edges}: the close was {verdict} it.{provisional}"


# --- the next 5 trading days ------------------------------------------------------------------------
def next_five_lines(facts: MarketFacts) -> Lines:
    if facts.band_pct is None:
        return (wording.NEXT_FIVE_HEADING, wording.no_range_text(
            facts.status, facts.reasons, ticker=facts.ticker, error_class=facts.error_class,
        ))
    range_line = (
        f"{wording.RANGE_LABEL}: about {wording.fmt_price(facts.band_lo)} to {wording.fmt_price(facts.band_hi)} "
        f"per share ({wording.fmt_band(facts.band_pct)})."
    )
    if facts.range_coverage is None:
        return (wording.NEXT_FIVE_HEADING, range_line, wording.not_measured(facts.ticker))
    return (wording.NEXT_FIVE_HEADING, range_line, wording.coverage_sentence(facts.range_coverage))


def _newest_bar(facts: tuple[MarketFacts, ...]) -> str | None:
    return max((f.last_bar for f in facts if f.last_bar), default=None)
