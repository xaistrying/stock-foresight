"""week.py: the week just ended and its comparison with the range that was issued."""

from __future__ import annotations

import math

import pytest

from app.services.brief.week import week_facts

from .test_brief_support import brief_isolation, make_issued_entry, sessions_ending  # noqa: F401

DATES = sessions_ending("2026-10-09", 8)  # ... 10-01, 10-02, 10-05 ... 10-09
D0 = DATES[-6]  # the bar the previous range was issued on


def _closes(first=41.00, last=42.00):
    """Eight closes: `first` is close[-6], the base of the week, and `last` is close[-1]."""
    return [40.0, 40.5, first, 41.2, 41.5, 41.4, 41.9, last]


def test_the_dates_and_closes_the_week_names():
    facts = week_facts(DATES, _closes(), ())

    assert (facts.first_date, facts.last_date, facts.base_date) == (DATES[-5], DATES[-1], D0)
    assert (facts.base_close, facts.last_close) == (41.0, 42.0)


def test_the_move_is_a_simple_percent_from_the_base_close():
    facts = week_facts(DATES, _closes(41.0, 42.0), ())

    assert facts.move_pct == pytest.approx((42.0 / 41.0 - 1) * 100)


def test_fewer_than_six_closes_has_no_week():
    assert week_facts(DATES[-5:], [1, 2, 3, 4, 5], ()) is None


def test_six_closes_are_enough():
    assert week_facts(DATES[-6:], [41.0, 41.2, 41.5, 41.4, 41.9, 42.0], ()) is not None


def test_no_entry_at_all_is_the_first_brief():
    assert week_facts(DATES, _closes(), ()).kind == "first"


def test_entries_none_matching_names_the_latest_on_file():
    old = make_issued_entry(as_of="2026-09-18")
    newer = make_issued_entry(as_of="2026-09-25")

    facts = week_facts(DATES, _closes(), (old, newer))

    assert facts.kind == "no_match" and facts.latest_on_file == "2026-09-25"


def test_a_matching_entry_without_a_band_gives_its_status():
    entry = make_issued_entry(as_of=D0, status="ineligible", band_pct=None, band_lo=None, band_hi=None)

    facts = week_facts(DATES, _closes(), (entry,))

    assert facts.kind == "no_band" and facts.prior_status == "ineligible"


def test_a_matching_entry_with_a_band_reports_inside():
    entry = make_issued_entry(as_of=D0, band_pct=2.7)  # the week's |ln(42/41)| is 2.41%

    facts = week_facts(DATES, _closes(41.0, 42.0), (entry,))

    assert facts.kind == "band" and facts.inside is True
    assert (facts.band_pct, facts.band_lo, facts.band_hi) == (2.7, 39.91, 42.12)


def test_a_larger_move_is_outside():
    entry = make_issued_entry(as_of=D0, band_pct=2.7)

    facts = week_facts(DATES, _closes(41.0, 42.4), (entry,))  # |ln(42.4/41)| = 3.36%

    assert facts.inside is False


def test_a_move_equal_to_the_band_is_inside():
    base, last = 41.0, 42.0
    band = abs(math.log(last / base)) * 100
    entry = make_issued_entry(as_of=D0, band_pct=band)

    assert week_facts(DATES, _closes(base, last), (entry,)).inside is True


def test_a_fall_is_measured_by_its_absolute_log_move():
    entry = make_issued_entry(as_of=D0, band_pct=2.7)

    assert week_facts(DATES, _closes(41.0, 39.5), (entry,)).inside is False  # |ln(39.5/41)| = 3.73%
    assert week_facts(DATES, _closes(41.0, 40.5), (entry,)).inside is True  # 1.23%


def test_a_constant_rescale_of_the_stored_closes_leaves_the_verdict_unchanged():
    entry = make_issued_entry(as_of=D0, band_pct=2.7)
    closes = _closes(41.0, 42.4)

    for factor in (0.5, 0.934, 3.0):
        scaled = week_facts(DATES, [c * factor for c in closes], (entry,))
        assert scaled.inside is False
        assert scaled.move_pct == pytest.approx(week_facts(DATES, closes, (entry,)).move_pct)


def test_a_same_day_rerun_takes_the_later_entry():
    earlier = make_issued_entry(as_of=D0, band_pct=1.0, issued_at="2026-10-02T04:00:00+00:00")
    later = make_issued_entry(as_of=D0, band_pct=2.7, issued_at="2026-10-02T09:00:00+00:00")

    facts = week_facts(DATES, _closes(41.0, 42.0), (earlier, later))  # the reader keeps file order

    assert facts.band_pct == 2.7


def test_a_provisional_issue_is_flagged():
    entry = make_issued_entry(as_of=D0, provisional=True)

    assert week_facts(DATES, _closes(), (entry,)).prior_provisional is True
    assert week_facts(DATES, _closes(), (make_issued_entry(as_of=D0),)).prior_provisional is False


def test_an_entry_for_the_last_bar_itself_is_not_read():
    own = make_issued_entry(as_of=DATES[-1], band_pct=2.7)

    assert week_facts(DATES, _closes(), (own,)).kind == "first"  # a re-run on the same bar still says first brief


def test_an_entry_after_the_last_bar_is_not_read():
    assert week_facts(DATES, _closes(), (make_issued_entry(as_of="2026-10-20"),)).kind == "first"


def test_a_degraded_final_entry_does_not_hide_a_good_provisional_one():
    good = make_issued_entry(as_of=D0, band_pct=2.7, provisional=True)
    degraded = make_issued_entry(as_of=D0, status="error", band_pct=None, band_lo=None, band_hi=None)

    facts = week_facts(DATES, _closes(41.0, 42.0), (good, degraded))

    assert facts.kind == "band" and facts.prior_provisional is True


def test_a_final_entry_with_a_band_wins_over_a_provisional_one():
    provisional = make_issued_entry(as_of=D0, band_pct=1.0, provisional=True)
    final = make_issued_entry(as_of=D0, band_pct=2.7)

    for order in ((provisional, final), (final, provisional)):
        facts = week_facts(DATES, _closes(), order)
        assert facts.band_pct == 2.7 and facts.prior_provisional is False


def test_the_horizon_is_the_models_single_source():
    from app.ml.volatility import HORIZON_SESSIONS
    from app.services.brief import week

    assert week.SESSIONS == HORIZON_SESSIONS
