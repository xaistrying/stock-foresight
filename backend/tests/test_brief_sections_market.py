"""sections_market.py: the header, the close, the week, the next 5 sessions and the notes, from market facts only."""

from __future__ import annotations

import math
import re
import pytest

from app.services.brief import sections_market as sm
from app.services.brief import wording

from .test_brief_support import BACKEND, brief_isolation, ict, make_facts, make_week  # noqa: F401

NOW = ict("2026-10-09 16:30")


def _text(lines):
    return "\n".join(lines)


# --- header ---------------------------------------------------------------------------------------

def test_the_title_names_the_newest_last_bar_and_the_horizon_without_weekdays():
    title = sm.title_line((make_facts("AAA"), make_facts("BBB", last_bar="2026-10-07")))

    assert "2026-10-09" in title and "the 5 sessions after 2026-10-09" in title
    assert not re.search(r"Mon|Tue|Wed|Thu|Fri|Sat|Sun", title)


def test_the_title_without_any_stored_price():
    title = sm.title_line((make_facts(last_bar=None, close=None, status="no_prices"),))

    assert "no stored prices" in title


def test_the_refresh_line_when_every_ticker_was_refreshed():
    lines = sm.refresh_lines((make_facts("AAA"), make_facts("BBB")))

    assert lines[0] == "Prices refreshed this run. Last bar for every holding is 2026-10-09."
    assert len(lines) == 1


def test_the_refresh_line_without_a_refresh_says_so():
    lines = sm.refresh_lines((make_facts(refresh="skipped"),))

    assert lines[0].startswith(wording.NOT_REFRESHED_LINE) and "2026-10-09" in lines[0]


def test_the_refresh_line_names_a_failed_and_a_skipped_ticker():
    facts = (
        make_facts("AAA"),
        make_facts("BBB", refresh="failed", refresh_detail="RuntimeError"),
        make_facts("CCC", refresh="not_attempted", refresh_detail="vendor limit reached earlier in this run"),
    )

    text = _text(sm.refresh_lines(facts))

    assert "BBB" in text and "CCC" in text and "except" in text


def test_holdings_with_different_last_bars_are_not_given_one_date():
    facts = (make_facts("AAA"), make_facts("BBB", last_bar="2026-10-07", stale_reasons=("behind_newest",)))

    lines = sm.refresh_lines(facts)
    text = _text(lines)

    assert "for every holding" not in text
    assert "AAA 2026-10-09" in text and "BBB 2026-10-07" in text


def test_a_bar_older_than_five_calendar_days_warns_in_calendar_days():
    lines = sm.note_lines(make_facts(last_bar="2026-10-01", stale_reasons=("old",)))

    assert any("5 calendar days" in line and line.startswith("WARNING") for line in lines)


# --- ticker header, close, notes ------------------------------------------------------------------

def test_the_ticker_header():
    assert sm.ticker_header(make_facts("SAB")) == ("--- SAB ---",)


def test_the_close_line_and_its_provisional_mark():
    assert sm.close_lines(make_facts()) == ("Close 42.90 (2026-10-09)",)
    assert sm.close_lines(make_facts(provisional=True)) == ("Close 42.90 (2026-10-09, provisional)",)
    assert sm.close_lines(make_facts(close=None, last_bar=None, status="no_prices")) == ()


def test_a_failed_refresh_reads_refresh_failed_last_bar_with_a_stale_warning():
    lines = sm.note_lines(make_facts(refresh="failed", refresh_detail="RuntimeError"))

    assert any("refresh failed; last bar 2026-10-09" in line for line in lines)
    assert any(line.startswith("WARNING") and "stale" in line.lower() for line in lines)


def test_a_failed_refresh_without_a_bar_says_no_stored_prices():
    lines = sm.note_lines(make_facts(refresh="failed", refresh_detail="no_data", close=None, last_bar=None, status="no_prices"))

    assert any("refresh failed; no stored prices" in line for line in lines)


def test_a_skipped_ticker_is_reported_with_its_reason():
    lines = sm.note_lines(make_facts(refresh="not_attempted", refresh_detail="vendor limit reached earlier in this run"))

    assert any("refresh failed; last bar 2026-10-09" in line and "not attempted" in line for line in lines)


def test_a_good_refresh_and_a_fresh_bar_have_no_notes():
    assert sm.note_lines(make_facts()) == ()
    assert sm.note_lines(make_facts(refresh="skipped")) == ()


def test_a_holding_behind_the_others_carries_its_own_warning():
    lines = sm.note_lines(make_facts("BBB", last_bar="2026-10-07", stale_reasons=("behind_newest",)))

    assert any(line.startswith("WARNING") and "2026-10-07" in line and "stale" in line for line in lines)


def test_the_readjusted_close_note():
    from app.services.brief.levels import Readjusted

    lines = sm.readjusted_lines(make_facts(readjusted=Readjusted("2026-07-23", 43.60, 46.60)))

    text = _text(lines)
    assert "2026-07-23" in text and "43.60" in text and "46.60" in text
    assert "re-adjusted" in text and wording.READJUSTED_LIMIT in text
    assert wording.READJUSTED_LEVELS_NOTE not in text  # market data only: the levels sentence is the holding's
    assert sm.readjusted_lines(make_facts()) == ()


# --- THE WEEK JUST ENDED -----------------------------------------------------------------------

def test_the_week_block_with_a_band_inside():
    text = _text(sm.week_lines(make_facts()))

    assert "THE WEEK JUST ENDED (2026-10-05 to 2026-10-09)" in text
    assert "Move: +2.4% (41.00 on 2026-10-02 -> 42.00 on 2026-10-09)" in text
    assert "Last week's range was ±2.7% (39.91 to 42.12): the close was inside it" in text
    assert wording.WEEK_COMPARE_LIMIT in text


def test_the_week_block_outside():
    week = make_week(inside=False, last_close=43.5, move_pct=(43.5 / 41 - 1) * 100)

    assert "the close was outside it" in _text(sm.week_lines(make_facts(week=week)))


def test_the_first_brief_sentence():
    text = _text(sm.week_lines(make_facts(week=make_week(kind="first", band_pct=None, band_lo=None, band_hi=None, inside=None))))

    assert wording.FIRST_BRIEF in text and "Last week's range" not in text


def test_a_skipped_week_names_the_latest_on_file():
    week = make_week(kind="no_match", latest_on_file="2026-09-25", band_pct=None, band_lo=None, band_hi=None, inside=None)

    assert "no range was issued for the week starting after 2026-10-02; the latest one on file is for 2026-09-25" in _text(
        sm.week_lines(make_facts(week=week))
    )


def test_a_week_whose_issued_brief_gave_no_range():
    week = make_week(kind="no_band", prior_status="ineligible", band_pct=None, band_lo=None, band_hi=None, inside=None)

    assert "last week's brief gave no range (the ticker was not eligible for a range)" in _text(
        sm.week_lines(make_facts(week=week))
    )


def test_a_provisional_issue_is_marked_in_the_sentence():
    text = _text(sm.week_lines(make_facts(week=make_week(prior_provisional=True))))

    assert wording.PROVISIONAL_ISSUE_NOTE in text


def test_a_week_that_cannot_be_formed():
    text = _text(sm.week_lines(make_facts(week=None)))

    assert "THE WEEK JUST ENDED" in text and wording.WEEK_UNAVAILABLE in text


def test_no_log_return_is_ever_shown():
    text = _text(sm.week_lines(make_facts()))

    assert "log" not in text.lower() and "ln(" not in text


# --- NEXT 5 TRADING DAYS ---------------------------------------------------------------------------

def test_an_ok_range_shows_the_edges_the_band_and_the_derived_coverage_sentence():
    lines = sm.next_five_lines(make_facts())

    assert lines[0] == "NEXT 5 TRADING DAYS"
    low, high = 42.90 * math.exp(-0.027), 42.90 * math.exp(0.027)
    assert lines[1] == f"Usual range (typical 5-session move): about {low:.2f} to {high:.2f} per share (±2.7%)."
    assert lines[2] == wording.coverage_sentence(0.68)


def test_an_uncalibrated_range_replaces_the_coverage_sentence():
    lines = sm.next_five_lines(make_facts("OUT", status="uncalibrated", calibrated=False, range_coverage=None))

    text = _text(lines)
    assert "Usual range" in text and wording.not_measured("OUT") in text
    assert "2 weeks in 3" not in text


@pytest.mark.parametrize(
    ("fields", "fragment"),
    [
        ({"status": "ineligible", "reasons": ("stale", "near_gap")}, "No range this week: stored prices are out of date; there is a gap"),
        ({"status": "model_unavailable"}, "volatility model file is missing or unusable"),
        ({"status": "range_out_of_bounds"}, "recent prices look abnormal"),
        ({"status": "no_prices", "close": None, "last_bar": None}, "No stored prices for AAA."),
        ({"status": "error", "error_class": "KeyError"}, "could not be computed (KeyError); see the log."),
    ],
)
def test_every_non_ok_status_has_its_wording_and_no_band(fields, fragment):
    nulls = dict(band_pct=None, band_lo=None, band_hi=None, range_coverage=None, calibrated=None)
    lines = sm.next_five_lines(make_facts(**{**nulls, **fields}))

    text = _text(lines)
    assert fragment in text and "Usual range" not in text and "±" not in text


def test_without_the_previous_range_only_the_move_remains():
    lines = sm.week_lines(make_facts(), with_previous_range=False)

    assert len(lines) == 2 and lines[0].startswith("THE WEEK JUST ENDED") and lines[1].startswith("Move:")
    assert "Last week" not in _text(lines) and wording.WEEK_COMPARE_LIMIT not in lines
