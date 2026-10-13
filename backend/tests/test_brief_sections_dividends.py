"""The dividend, ex-date and week lines inside whole briefs, over a temporary feed log, a temporary price database and
hypothetical holdings (`weekly-holdings-brief`, `add-dividend-and-ex-date-lines`)."""

from __future__ import annotations

import dataclasses
import re
import sqlite3
from datetime import date

from app.services.brief.company_facts import gather_company_facts
from app.services.brief.compose import TickerReport, build_brief
from app.services.brief.facts import gather_market_facts
from app.services.brief.levels import Readjusted

from .brief_event_rows import (
    BONUS, Bars, bars_from, div_row, iss_row, load_feed, raw_history_bars, sab_rows, sab_week_bars, vpb_rows,
)
from .test_brief_support import (  # noqa: F401
    brief_env, brief_isolation, ict, make_holding, make_issued_entry, make_level, make_log,
)

HISTORY = 400


def put(env, ticker: str, bars: Bars) -> None:
    env.add_ticker(ticker, bars.closes, list(bars.dates))
    conn = sqlite3.connect(env.db_path)
    conn.executemany(
        "UPDATE ohlcv SET open = ? WHERE ticker = ? AND date = ?", [(o, ticker, day) for o, day in zip(bars.opens, bars.dates)],
    )
    conn.commit()
    conn.close()


def facts_for(ticker: str, bars: Bars, *, entries=(), **kwargs):
    """Market facts plus the announcement facts the COMPANY block (and so the one Scheduled line) is built from."""
    now, log = ict(f"{bars.dates[-1]} 16:30"), make_log(*entries)
    facts = gather_market_facts(ticker, refresh=None, log=log, now=now, **kwargs)
    return dataclasses.replace(facts, company=gather_company_facts(ticker, facts, log, now, sizing=False))


def render(report: TickerReport, *, redact: bool, last_bar: str) -> str:
    return "\n".join(build_brief((report,), redact=redact, now=ict(f"{last_bar} 16:30")))


def sab_world(env, *, purchase=date(2025, 6, 10), levels=(), band=2.8, history=HISTORY):
    bars = sab_week_bars(history)
    put(env, "SAB", bars)
    load_feed({"SAB": sab_rows()})
    entry = make_issued_entry("SAB", as_of=bars.dates[-6], close=43.97, band_pct=band, band_lo=42.8, band_hi=45.2)
    facts = facts_for("SAB", bars, entries=(entry,))
    return TickerReport(make_holding("SAB", shares=1000, cost=41.80, purchase_date=purchase, levels=levels), facts), bars


# --- SAB, the measured week -------------------------------------------------------------------------------------

def test_the_measured_sab_week_in_the_full_brief(brief_env):
    level = make_level("below", 40.0, date(2026, 7, 15), "Own rule text for SAB")
    report, bars = sab_world(brief_env, levels=(level,))

    text = render(report, redact=False, last_bar=bars.dates[-1])

    assert (
        "Board move: -7.7% (47.00 -> 43.40); about 3,000 VND of that is the dividend that went ex on 2026-07-28. Excluding "
        "the dividend: -1.3% (43.97 -> 43.40). Last week's range was ±2.8%: the move excluding the dividend was inside it."
    ) in text
    assert "Board figures are calculated from the dividend (company-announcement source, events fetched 2026-10-10 12:11 UTC) and the stored closes; check your broker's figure." in text
    assert "Move: " not in text and "(42.80 to 45.20)" not in text  # the combined line replaces N1's move and range sentences
    assert "DIVIDENDS (company-announcement source; events last fetched 2026-10-10 12:11 UTC" in text
    assert "Scheduled (company-announcement source, events fetched 2026-10-10 12:11 UTC; dated after the last bar, 2026-07-30): none found." in text
    assert (
        "ex-dates since your purchase date (company-announcement source, which covers from 2017-05-15): 3,000 VND (ex 2025-06-30), "
        "2,000 VND (ex 2026-01-12), 3,000 VND (ex 2026-07-28)."
    ) in text
    assert "may be incomplete" not in text
    lines = text.splitlines()
    level_at = next(i for i, line in enumerate(lines) if line.startswith("Own rule text for SAB"))
    assert "REACHED" not in lines[level_at] and lines[level_at + 1].startswith("  Note from the company-announcement source: a dividend of 3,000 VND")
    assert lines[level_at].endswith("below the close.") or "not reached" in lines[level_at]  # the level line is N1's, unchanged


def test_a_brief_with_a_feed_has_a_dividends_block_and_one_scheduled_line_in_the_company_block_and_no_net_line_or_total(brief_env):
    report, bars = sab_world(brief_env)

    full = render(report, redact=False, last_bar=bars.dates[-1])

    assert re.search(r"^DIVIDENDS \(", full, re.M) and re.search(r"^COMPANY \(", full, re.M)
    assert not re.search(r"net line|\btotal\b", full, re.M | re.I)
    assert full.count("\nDIVIDENDS (") == 1 and full.count("Scheduled (") == 1
    lines = full.splitlines()
    scheduled_at = next(i for i, line in enumerate(lines) if line.startswith("Scheduled ("))
    company_at = next(i for i, line in enumerate(lines) if line.startswith("COMPANY ("))
    dividends_at = next(i for i, line in enumerate(lines) if line.startswith("DIVIDENDS ("))
    assert dividends_at < company_at < scheduled_at  # the Scheduled line sits in COMPANY, not under DIVIDENDS


def test_a_level_note_never_repeats_the_investors_text(brief_env):
    text_with_verb = "Sell 300 shares if the close is below 40.00"
    level = make_level("below", 40.0, date(2026, 7, 15), text_with_verb)
    report, bars = sab_world(brief_env, levels=(level,))

    text = render(report, redact=False, last_bar=bars.dates[-1])

    assert text.count(text_with_verb) == 1  # only the level's own line carries the investor's words
    assert "Note from the company-announcement source" in text


def test_the_level_line_is_identical_with_and_without_the_note(brief_env):
    level = make_level("below", 40.0, date(2026, 7, 15), "Own rule text for SAB")
    report, bars = sab_world(brief_env, levels=(level,))
    with_note = render(report, redact=False, last_bar=bars.dates[-1]).splitlines()
    early = make_level("below", 40.0, date(2026, 8, 1), "Own rule text for SAB")  # entered after the ex-date: no note
    without = render(TickerReport(make_holding("SAB", levels=(early,), purchase_date=date(2025, 6, 10)), report.facts), redact=False, last_bar=bars.dates[-1]).splitlines()

    line = next(l for l in with_note if l.startswith("Own rule text"))
    assert line.replace("2026-07-15", "2026-08-01") in without
    assert not any(l.startswith("  Note from") for l in without)


def test_the_redacted_copy_keeps_market_lines_and_drops_purchase_level_and_log_lines(brief_env):
    level = make_level("below", 40.0, date(2026, 7, 15), "Own rule text for SAB")
    report, bars = sab_world(brief_env, levels=(level,))

    text = render(report, redact=True, last_bar=bars.dates[-1])

    assert "DIVIDENDS (company-announcement source; events last fetched" in text and "Scheduled (company-announcement source" in text
    assert "Board move: -7.7% (47.00 -> 43.40); about 3,000 VND of that is the dividend that went ex on 2026-07-28." in text
    assert "Excluding the dividend: -1.3% (43.97 -> 43.40)." in text and "Board figures are calculated" in text
    for fragment in ("since your purchase date", "2025-06-10", "2026-07-15", "Note from", "Last week's range", "Move:", "first brief", "Recomputed", "may be incomplete"):
        assert fragment not in text, fragment


def test_a_holding_with_no_purchase_date_still_gets_the_market_lines_and_the_level_note(brief_env):
    level = make_level("below", 40.0, date(2026, 7, 15), "Own rule text for SAB")
    report, bars = sab_world(brief_env, purchase=None, levels=(level,))

    text = render(report, redact=False, last_bar=bars.dates[-1])

    assert "Cash dividends and share issues since your purchase date: not listed, because no purchase date is entered for this holding." in text
    assert "Board move: -7.7%" in text and "Note from the company-announcement source" in text and "Scheduled (" in text


def test_the_old_purchase_date_makes_the_list_incomplete_not_wrong(brief_env):
    report, bars = sab_world(brief_env, purchase=date(2017, 6, 1))

    text = render(report, redact=False, last_bar=bars.dates[-1])

    assert "This list may be incomplete for ex-dates before 2017-09-12" in text and "list is wrong" not in text


# --- week-1 and the issued log ------------------------------------------------------------------------------------

def test_a_week_with_no_issued_entry_recomputes_inside_the_combined_line_and_only_in_the_full_copy(brief_env):
    bars = sab_week_bars(HISTORY)
    put(brief_env, "SAB", bars)
    load_feed({"SAB": sab_rows()})
    report = TickerReport(make_holding("SAB", purchase_date=date(2025, 6, 10)), facts_for("SAB", bars))

    full = render(report, redact=False, last_bar=bars.dates[-1])
    redacted = render(report, redact=True, last_bar=bars.dates[-1])

    assert "first brief: no previous range." in full
    assert re.search(r"Range recomputed today from prices up to 2026-07-23; not an issued range: ±[\d.]+%: the move excluding the dividend was (inside|outside) it\.", full)
    assert "Recomputed" not in redacted and "recomputed" not in redacted and "first brief" not in redacted
    assert "Board move: -7.7%" in redacted


def test_a_quiet_week_one_ticker_gets_the_recomputed_line_in_the_full_copy_only(brief_env):
    bars = bars_from([("2026-10-08", 25.0, 25.0), ("2026-10-09", 25.1, 25.1)], history=HISTORY, level=25.0)
    put(brief_env, "AAA", bars)
    load_feed({"AAA": [div_row("AAA", 0, published="2025-01-10", ex="2025-02-10", vnd=500.0)]})
    report = TickerReport(make_holding("AAA"), facts_for("AAA", bars))

    full = render(report, redact=False, last_bar="2026-10-09")
    redacted = render(report, redact=True, last_bar="2026-10-09")

    assert re.search(r"Recomputed today from prices up to 2026-10-0\d; not an issued range: ±[\d.]+%\. The week's move of [+-][\d.]+% was (inside|outside) it\.", full)
    assert "Recomputed" not in redacted and "first brief" not in redacted


def test_the_week_1_line_is_not_printed_when_the_issued_brief_gave_no_range(brief_env):
    bars = bars_from([("2026-10-08", 25.0, 25.0), ("2026-10-09", 25.1, 25.1)], history=HISTORY, level=25.0)
    put(brief_env, "AAA", bars)
    load_feed({"AAA": [div_row("AAA", 0, published="2025-01-10", ex="2025-02-10", vnd=500.0)]})
    entry = make_issued_entry("AAA", as_of=bars.dates[-6], band_pct=None, band_lo=None, band_hi=None, status="ineligible", calibrated=None)

    full = render(TickerReport(make_holding("AAA"), facts_for("AAA", bars, entries=(entry,))), redact=False, last_bar="2026-10-09")

    assert "last week's brief gave no range" in full and "Recomputed" not in full


def test_a_rerun_on_the_same_bar_prints_the_same_week_text(brief_env):
    bars = sab_week_bars(HISTORY)
    put(brief_env, "SAB", bars)
    load_feed({"SAB": sab_rows()})
    first = render(TickerReport(make_holding("SAB"), facts_for("SAB", bars)), redact=False, last_bar=bars.dates[-1])
    own_entry = make_issued_entry("SAB", as_of=bars.dates[-1], close=43.40)  # the first run's own entry for the last bar

    second = render(TickerReport(make_holding("SAB"), facts_for("SAB", bars, entries=(own_entry,))), redact=False, last_bar=bars.dates[-1])

    assert first == second


# --- history not yet adjusted ----------------------------------------------------------------------------------------

def test_history_not_yet_adjusted_gets_a_note_and_a_status_clause_and_no_board_move(brief_env):
    bars = raw_history_bars(HISTORY)
    put(brief_env, "SAB", bars)
    load_feed({"SAB": sab_rows()})
    level = make_level("below", 40.0, date(2026, 7, 15), "Own rule text for SAB")
    report = TickerReport(make_holding("SAB", purchase_date=date(2025, 6, 10), levels=(level,)), facts_for("SAB", bars))

    text = render(report, redact=False, last_bar=bars.dates[-1])

    assert "History is not yet adjusted for the 2026-07-28 dividend; the stored move includes it." in text
    assert "Board move:" not in text and "Move: " in text
    assert "The brief does not change your level. Stored history is not yet adjusted for it." in text
    assert "History is not yet adjusted for the 2026-07-28 dividend" in render(report, redact=True, last_bar=bars.dates[-1])


# --- other tickers ---------------------------------------------------------------------------------------------------

def test_a_ticker_with_no_feed_rows_reads_as_never_fetched_with_the_command(brief_env):
    bars = bars_from([("2026-10-08", 25.0, 25.0), ("2026-10-09", 25.0, 25.0)], history=HISTORY, level=25.0)
    put(brief_env, "ZZZ", bars)
    load_feed({"SAB": sab_rows()})
    level = make_level("below", 24.0, date(2026, 9, 1), "Own rule text for ZZZ")
    report = TickerReport(make_holding("ZZZ", purchase_date=date(2025, 6, 10), levels=(level,)), facts_for("ZZZ", bars))

    text = render(report, redact=False, last_bar="2026-10-09")

    assert "No dividend or share issue can be listed or checked for ZZZ: its events have never been fetched, which is not the same as none found." in text
    assert "python backend/scripts/snapshot_company_feed.py --tickers ZZZ" in text
    assert "Whether an ex-date fell in this week is not known: no stored events are available for ZZZ." in text
    assert ": none found" not in text and "none found in what the source returned" not in text
    assert "Scheduled (company-announcement source): not checked" in text  # the one Scheduled line is in COMPANY and says so
    assert "events fetched" not in text.split("Scheduled (")[1].splitlines()[0]
    assert "since your purchase date" not in text and "Note from" not in text


def test_a_stock_dividend_since_purchase_is_listed_by_ratio_only_and_no_count_is_computed(brief_env):
    bars = bars_from([("2026-10-08", 25.0, 25.0), ("2026-10-09", 25.0, 25.0)], history=HISTORY, level=25.0)
    put(brief_env, "VPB", bars)
    load_feed({"VPB": vpb_rows()})
    level = make_level("below", 22.0, date(2026, 9, 2), "Own rule text for VPB")
    report = TickerReport(make_holding("VPB", shares=1000, purchase_date=date(2026, 9, 1), levels=(level,)), facts_for("VPB", bars))

    text = render(report, redact=False, last_bar="2026-10-09")

    assert "ex 2026-09-24, 26.04 new shares per 100 held. They change your share count." in text
    assert "ratio not checked against your broker" in text
    assert "a share issue of 26.04 new shares per 100 held went ex on 2026-09-24, after you entered this level on 2026-09-02" in text
    assert not re.search(r"1,260|1260|1,000 shares become|new share count|multiplier|factor", text)
    assert "announced 2026-04-24" not in text  # the VPB placement with no ex-date is not an investor issue and not pending (not BONUS)


def test_a_bonus_in_the_window_has_a_market_line_a_holding_line_and_no_shifted_range(brief_env):
    bars = bars_from([("2026-10-08", 25.0, 25.0), ("2026-10-09", 25.0, 25.0)], history=HISTORY, level=25.0)
    put(brief_env, "FPT", bars)
    load_feed({"FPT": [iss_row("FPT", BONUS, 1, published="2026-09-25", ex="2026-10-14", ratio=0.15)]})
    report = TickerReport(make_holding("FPT"), facts_for("FPT", bars))

    full = render(report, redact=False, last_bar="2026-10-09")
    redacted = render(report, redact=True, last_bar="2026-10-09")

    market = "Share issue in the window (company-announcement source): ex 2026-10-14, 15 new shares per 100 held. The board price is adjusted for the issue the same day, so the range above does not apply from then."
    assert market in full and market in redacted
    assert "Your share count and cost per share change from 2026-10-14; update your entries." in full
    assert "update your entries" not in redacted and "about" not in market


def test_a_dividend_in_the_window_shifts_the_displayed_range(brief_env):
    bars = bars_from([("2026-10-08", 25.0, 25.0), ("2026-10-09", 25.0, 25.0)], history=HISTORY, level=25.0)
    put(brief_env, "AAA", bars)
    load_feed({"AAA": [div_row("AAA", 0, published="2026-09-25", ex="2026-10-14", vnd=2000.0, record="2026-10-15")]})
    facts = facts_for("AAA", bars)
    report = TickerReport(make_holding("AAA"), facts)

    redacted = render(report, redact=True, last_bar="2026-10-09")

    low, high = round(facts.band_lo - 2.0, 2), round(facts.band_hi - 2.0, 2)
    assert f"From that day the whole range moves down by the dividend: about {low:.2f} to {high:.2f}." in redacted
    assert "Record date 2026-10-15; payout not announced." in redacted


def test_an_adjusted_dividend_in_the_last_week_of_a_ticker_that_pays_a_small_amount(brief_env):
    bars = bars_from(
        [("2026-10-02", 30.0, 30.0), ("2026-10-05", 30.0, 30.0), ("2026-10-06", 30.0, 30.0), ("2026-10-07", 29.9, 29.9),
         ("2026-10-08", 29.9, 29.9), ("2026-10-09", 30.0, 30.0)], history=HISTORY, level=30.0,
    )
    put(brief_env, "MWG", bars)
    load_feed({"MWG": [div_row("MWG", 0, published="2026-09-20", ex="2026-10-07", vnd=1000.0, record="2026-10-08")]})
    entry = make_issued_entry("MWG", as_of="2026-10-02", close=30.0, band_pct=2.5)
    report = TickerReport(make_holding("MWG", purchase_date=date(2026, 1, 5)), facts_for("MWG", bars, entries=(entry,)))

    text = render(report, redact=False, last_bar="2026-10-09")

    assert "Board move: " in text and "about 1,000 VND of that is the dividend that went ex on 2026-10-07" in text
    assert "Excluding the dividend: +0.0% (30.00 -> 30.00)." in text.replace("0.0%", "0.0%")


# --- the re-adjusted note --------------------------------------------------------------------------------------------

def test_the_readjusted_note_names_the_dividend_that_explains_it(brief_env):
    bars = sab_week_bars(HISTORY)
    put(brief_env, "SAB", bars)
    load_feed({"SAB": sab_rows()})
    entry = make_issued_entry("SAB", as_of="2026-07-23", close=46.60, band_pct=2.8)
    facts = facts_for("SAB", bars, entries=(entry,))

    text = render(TickerReport(make_holding("SAB"), facts), redact=False, last_bar=bars.dates[-1])
    redacted = render(TickerReport(make_holding("SAB"), facts), redact=True, last_bar=bars.dates[-1])

    assert facts.readjusted == Readjusted("2026-07-23", 43.97, 46.60)
    explanation = "The company-announcement source lists a dividend of 3,000 VND a share ex 2026-07-28, after 2026-07-23; the brief has not checked that it accounts for the difference."
    assert explanation in text and explanation in redacted


def test_no_explanation_when_the_feed_lists_nothing_after_the_logged_date(brief_env):
    bars = sab_week_bars(HISTORY)
    put(brief_env, "SAB", bars)
    load_feed({"SAB": [rows for rows in sab_rows() if rows["exright_date"] != "2026-07-28"]})
    entry = make_issued_entry("SAB", as_of="2026-07-23", close=46.60, band_pct=2.8)

    text = render(TickerReport(make_holding("SAB"), facts_for("SAB", bars, entries=(entry,))), redact=False, last_bar=bars.dates[-1])

    assert "NOTE: the close stored for 2026-07-23" in text and "accounts for the difference" not in text


def test_a_failed_feed_read_never_removes_the_holding(brief_env, monkeypatch):
    from app.services.brief import feed_source

    bars = sab_week_bars(HISTORY)
    put(brief_env, "SAB", bars)
    monkeypatch.setattr(feed_source.store, "last_fetch", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("locked")))
    report = TickerReport(make_holding("SAB"), facts_for("SAB", bars))

    text = render(report, redact=False, last_bar=bars.dates[-1])

    assert "--- SAB" in text and "could not build this holding" not in text
    assert "its stored events could not be read this run, which is not the same as none found or never fetched" in text
