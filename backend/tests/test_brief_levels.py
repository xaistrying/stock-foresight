"""levels.py: the investor's levels against the last close, and the re-adjusted-close detector."""

from __future__ import annotations

import pytest

from app.services.brief.levels import LevelCheck, check_level, detect_readjusted

from .test_brief_support import brief_isolation, make_issued_entry, make_level, sessions_ending  # noqa: F401


def test_a_below_level_is_reached_when_the_close_is_under_it():
    check = check_level(make_level("below", 41.60), 41.20)

    assert check.reached is True and check.distance_pct == pytest.approx(0.4 / 41.20 * 100)


def test_a_below_level_not_reached():
    check = check_level(make_level("below", 41.60), 42.90)

    assert check.reached is False and check.distance_pct == pytest.approx(1.3 / 42.90 * 100)


def test_an_above_level_both_ways():
    assert check_level(make_level("above", 44.0), 44.5).reached is True
    assert check_level(make_level("above", 44.0), 43.5).reached is False


def test_equal_is_not_reached_with_zero_distance():
    for comparator in ("below", "above"):
        check = check_level(make_level(comparator, 41.60), 41.60)
        assert check.reached is False and check.distance_pct == 0.0


def test_the_spec_distances_to_one_decimal():
    assert round(check_level(make_level("below", 41.60), 41.20).distance_pct, 1) == 1.0  # 0.4 / 41.2 = 0.97
    assert round(check_level(make_level("below", 41.60), 42.90).distance_pct, 1) == 3.0  # 1.3 / 42.9 = 3.03


def test_no_close_means_not_checked():
    check = check_level(make_level(), None)

    assert check == LevelCheck(make_level(), None, None)


# --- the re-adjusted close detector ---------------------------------------------------------------

DATES = sessions_ending("2026-10-09", 10)


def _closes(value=43.60):
    return [value] * 10


def test_a_changed_stored_close_is_detected():
    entry = make_issued_entry(as_of=DATES[2], close=46.60)

    note = detect_readjusted((entry,), DATES, _closes(43.60))

    assert (note.date, note.stored, note.issued) == (DATES[2], 43.60, 46.60)


def test_equal_closes_give_no_note():
    assert detect_readjusted((make_issued_entry(as_of=DATES[2], close=43.60),), DATES, _closes(43.60)) is None


def test_a_difference_within_half_a_price_unit_gives_no_note():
    assert detect_readjusted((make_issued_entry(as_of=DATES[2], close=43.604),), DATES, _closes(43.60)) is None
    assert detect_readjusted((make_issued_entry(as_of=DATES[2], close=43.606),), DATES, _closes(43.60)) is not None


def test_a_date_outside_the_stored_window_gives_no_note():
    entry = make_issued_entry(as_of="2020-01-03", close=46.60)

    assert detect_readjusted((entry,), DATES, _closes()) is None


def test_no_earlier_entry_gives_no_note():
    assert detect_readjusted((), DATES, _closes()) is None


def test_the_most_recent_earlier_entry_is_the_one_used():
    old = make_issued_entry(as_of=DATES[1], close=50.00)  # would differ, but is not the latest
    recent = make_issued_entry(as_of=DATES[4], close=43.60)

    assert detect_readjusted((old, recent), DATES, _closes(43.60)) is None


def test_an_entry_after_the_last_stored_bar_is_not_earlier():
    future = make_issued_entry(as_of="2026-10-15", close=99.0)
    earlier = make_issued_entry(as_of=DATES[4], close=43.60)

    assert detect_readjusted((earlier, future), DATES, _closes(43.60)) is None


def test_a_provisional_close_revised_on_the_same_date_is_flagged():
    entry = make_issued_entry(as_of=DATES[-1], close=22.90, provisional=True)
    closes = _closes(43.60)[:-1] + [23.00]

    note = detect_readjusted((entry,), DATES, closes)

    assert note is not None and note.date == DATES[-1]


def test_an_entry_without_a_date_or_close_is_ignored():
    entry = make_issued_entry(as_of=None, close=None, status="no_prices")

    assert detect_readjusted((entry,), DATES, _closes()) is None


def test_a_final_entry_for_the_last_bar_is_never_compared():
    final = make_issued_entry(as_of=DATES[-1], close=46.60, provisional=False)

    assert detect_readjusted((final,), DATES, _closes(43.60)) is None  # a same-bar re-run must not read its own entry


def test_a_final_entry_for_an_earlier_date_wins_over_its_provisional_twin():
    provisional = make_issued_entry(as_of=DATES[4], close=50.0, provisional=True)
    final = make_issued_entry(as_of=DATES[4], close=43.60, provisional=False)

    assert detect_readjusted((provisional, final), DATES, _closes(43.60)) is None


def test_the_result_does_not_depend_on_an_entry_for_the_last_bar():
    earlier = make_issued_entry(as_of=DATES[2], close=46.60)
    own = make_issued_entry(as_of=DATES[-1], close=43.60)

    assert detect_readjusted((earlier,), DATES, _closes(43.60)) == detect_readjusted((earlier, own), DATES, _closes(43.60))
