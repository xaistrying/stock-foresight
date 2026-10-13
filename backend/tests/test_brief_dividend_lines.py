"""The renderers of the dividend, ex-date and share-issue lines, for every state of the spec, with hypothetical data
(`weekly-holdings-brief`, `add-dividend-and-ex-date-lines`)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from app.services.brief import corporate_actions as ca
from app.services.brief import dividend_lines as dl
from app.services.brief import dividend_lines_holding as dh
from app.services.brief import wording
from app.services.brief.adjustment_status import AdjustmentStatus
from app.services.brief.feed_source import Event, FeedSnapshot, IssueClass, snapshot_command
from app.services.brief.week_move import WeekOne, board_move, week_plan

from .brief_event_rows import d, sab_week_bars
from .test_brief_support import brief_isolation  # noqa: F401

ADJUSTED, NOT_YET, UNCLEAR = AdjustmentStatus.ADJUSTED, AdjustmentStatus.NOT_YET_ADJUSTED, AdjustmentStatus.UNCLEAR
LAST_BAR = d("2026-10-09")
FETCHED_AT = datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc)
LABEL = "company-announcement source"


def cash(ex, vnd, record=None, payout=None, published="2026-05-08") -> Event:
    return Event("DIV", d(ex), d(record) if record else None, d(payout) if payout else None, vnd, None, d(published), None)


def issue(klass, ex, ratio, published="2026-08-20") -> Event:
    return Event("ISS", d(ex) if ex else None, None, None, None, ratio, d(published), klass)


def feed(*events, oldest="2017-05-15", unreadable=0, failed_at=None) -> FeedSnapshot:
    return FeedSnapshot(
        "fetched", events=tuple(events), oldest_event_date=d(oldest), unreadable=unreadable, last_success_at=FETCHED_AT,
        latest_attempt_at=failed_at or FETCHED_AT, latest_attempt_failed=failed_at is not None,
    )


# --- the header and the feed states ----------------------------------------------------------------------

def test_the_header_states_when_events_were_last_fetched_and_its_age_against_the_last_bar():
    assert dl.header_lines("SAB", feed(), LAST_BAR) == (
        "DIVIDENDS (company-announcement source; events last fetched 2026-10-10 12:11 UTC, 1 calendar day after the last bar)",
    )


@pytest.mark.parametrize(
    ("last_bar", "age"),
    [("2026-10-10", "on the last bar's date"), ("2026-10-02", "8 calendar days after the last bar"), ("2026-10-12", "2 calendar days before the last bar")],
)
def test_the_age_is_printed_as_is_with_no_staleness_threshold(last_bar, age):
    assert age in dl.header_lines("SAB", feed(), d(last_bar))[0]


def test_a_failed_latest_attempt_is_stated_beside_the_earlier_success():
    snapshot = feed(failed_at=datetime(2026, 10, 11, 8, 0, tzinfo=timezone.utc))

    header = dl.header_lines("SAB", snapshot, LAST_BAR)[0]

    assert "events last fetched 2026-10-10 12:11 UTC" in header and "the latest attempt 2026-10-11 08:00 UTC failed" in header


def test_never_fetched_prints_the_command_and_not_none_found():
    lines = dl.header_lines("SAB", FeedSnapshot("never_fetched"), LAST_BAR)

    assert lines[0] == "DIVIDENDS (company-announcement source)"
    assert lines[1] == (
        "No dividend or share issue can be listed or checked for SAB: its events have never been fetched, which is not the "
        "same as none found. To fetch (run by hand; this brief does not run it): " + snapshot_command(["SAB"])
    )
    assert "none found" not in lines[0]


def test_never_succeeded_says_no_fetch_has_succeeded():
    lines = dl.header_lines("SAB", FeedSnapshot("never_succeeded", latest_attempt_failed=True), LAST_BAR)

    assert "no fetch of its events has succeeded" in lines[1] and snapshot_command(["SAB"]) in lines[1]


def test_unreadable_rows_are_counted_after_a_fetch():
    lines = dl.header_lines("SAB", feed(unreadable=2), LAST_BAR)

    assert lines[1] == "2 feed row(s) could not be read (company-announcement source)."
    assert len(dl.header_lines("SAB", feed(), LAST_BAR)) == 1


# --- Scheduled and the older announcements ----------------------------------------------------------------------

def test_an_unreadable_feed_says_so_and_prints_the_command():
    lines = dl.header_lines("SAB", FeedSnapshot("unreadable"), LAST_BAR)

    assert lines[0] == "DIVIDENDS (company-announcement source)"
    assert "its stored events could not be read this run, which is not the same as none found or never fetched" in lines[1]
    assert snapshot_command(["SAB"]) in lines[1] and dl.scheduled_lines(FeedSnapshot("unreadable"), LAST_BAR) == ()


def test_a_long_scheduled_list_is_cut_at_ten_items():
    many = [cash(f"2026-11-{day:02d}", 1000.0 + day) for day in range(1, 26)]

    (line,) = dl.scheduled_lines(feed(*many), LAST_BAR)

    assert line.count("a share") == 10 and "and 15 more." in line and len(line) < 1200


def test_the_scheduled_line_lists_dated_events_and_ends_with_the_after_last_fetch_sentence():
    snapshot = feed(cash("2026-10-14", 2000.0, record="2026-10-15"), issue(IssueClass.BONUS, "2026-11-02", 0.1))

    (line,) = dl.scheduled_lines(snapshot, LAST_BAR)

    assert line == (
        "Scheduled (company-announcement source, events fetched 2026-10-10 12:11 UTC; dated after the last bar, 2026-10-09): ex 2026-10-14, 2,000 VND a share, "
        "record 2026-10-15; ex 2026-11-02, 10 new shares per 100 held. An announcement made after the last fetch is not shown."
    )


def test_scheduled_none_found_only_after_a_fetch():
    (line,) = dl.scheduled_lines(feed(), LAST_BAR)

    assert "none found. An announcement made after the last fetch is not shown." in line
    assert dl.scheduled_lines(FeedSnapshot("never_fetched"), LAST_BAR) == ()
    assert dl.scheduled_lines(FeedSnapshot("never_succeeded"), LAST_BAR) == ()


def test_a_pending_announcement_and_a_rights_offer_are_on_the_scheduled_line():
    snapshot = feed(issue(IssueClass.BONUS, None, 0.1279, published="2026-04-28"), issue(IssueClass.RIGHTS_OFFER, "2026-10-20", 0.2))

    (line,) = dl.scheduled_lines(snapshot, LAST_BAR)

    assert "announced 2026-04-28, no ex-date yet: bonus shares, 12.79 new shares per 100 held (not applied until an ex-date is set)" in line
    assert "rights offer, ex 2026-10-20: read the notice; not calculated" in line


def test_a_pending_stock_dividend_without_a_ratio_names_it_without_a_number():
    (line,) = dl.scheduled_lines(feed(issue(IssueClass.STOCK_DIVIDEND, None, None, published="2026-06-01")), LAST_BAR)

    assert "announced 2026-06-01, no ex-date yet: stock dividend (not applied until an ex-date is set)" in line


def test_the_older_announcements_line_counts_and_is_quiet_about_why():
    snapshot = feed(
        issue(IssueClass.BONUS, None, 0.1279, published="2026-04-28"), issue(IssueClass.BONUS, None, 0.5, published="2019-04-26"),
        issue(IssueClass.STOCK_DIVIDEND, None, 0.2, published="2020-06-26"),
    )

    lines = dl.scheduled_lines(snapshot, LAST_BAR)

    assert lines[-1] == "2 older announcement(s) with no ex-date are no longer shown."
    assert not re.search(r"lapsed|cancel|expired", lines[-1], re.I)


def test_no_older_line_when_nothing_is_older_or_the_feed_was_not_fetched():
    recent = feed(issue(IssueClass.BONUS, None, 0.1, published="2026-04-28"))

    assert len(dl.scheduled_lines(recent, LAST_BAR)) == 1
    assert len(dl.scheduled_lines(feed(), LAST_BAR)) == 1


# --- the window -------------------------------------------------------------------------------------------------

def test_a_dividend_in_the_window_with_the_shifted_range():
    in_window = (cash("2026-10-14", 2000.0, record="2026-10-15", payout="2026-11-10"),)

    (line,) = dl.window_lines(in_window, (41.74, 44.06))

    assert line == (
        "Ex-date in the window (company-announcement source): ex-dividend 2026-10-14, 2,000 VND per share (within 7 calendar "
        "days of the last bar). From that day the whole range moves down by the dividend: about 39.74 to 42.06. "
        "Record date 2026-10-15; payout 2026-11-10."
    )


def test_payout_not_announced_and_no_record_date():
    (line,) = dl.window_lines((cash("2026-10-14", 2000.0),), (41.74, 44.06))

    assert "Record date not announced; payout not announced." in line


def test_the_shifted_range_is_not_shown_when_it_cannot_be_or_more_than_one_ex_date_is_in_the_window():
    one = (cash("2026-10-14", 3000.0),)
    two = (cash("2026-10-14", 2000.0), cash("2026-10-15", 500.0))

    assert "the shifted range is not shown" in dl.window_lines(one, (2.5, 3.5))[0]
    assert "more than one ex-date; the shifted range is not shown" in dl.window_lines(two, (41.74, 44.06))[0]
    assert "about" not in dl.window_lines(two, (41.74, 44.06))[0].split("moves down")[-1]


def test_a_dividend_in_the_window_with_no_displayed_range():
    (line,) = dl.window_lines((cash("2026-10-14", 2000.0),), None)

    assert "The price moves down by the dividend from that day." in line and "about" not in line


def test_a_share_issue_in_the_window_has_no_shifted_range():
    (line,) = dl.window_lines((issue(IssueClass.STOCK_DIVIDEND, "2026-10-14", 0.2604104),), (41.74, 44.06))

    assert line == (
        "Share issue in the window (company-announcement source): ex 2026-10-14, 26.04 new shares per 100 held. The board "
        "price is adjusted for the issue the same day, so the range above does not apply from then."
    )


def test_a_rights_offer_in_the_window_says_read_the_notice():
    (line,) = dl.window_lines((issue(IssueClass.RIGHTS_OFFER, "2026-10-14", 0.2),), (41.74, 44.06))

    assert line == (
        "Rights offer in the window (company-announcement source): ex 2026-10-14. Read the notice; not calculated. The board "
        "price may be adjusted the same day, so the range above may not apply from then."
    )
    assert "about" not in line


def test_the_window_lines_for_an_issue_without_a_range_do_not_point_at_one():
    (line,) = dl.window_lines((issue(IssueClass.BONUS, "2026-10-14", 0.1),), None)

    assert "range" not in line and line.endswith("the same day.")


def test_the_holding_line_for_an_issue_in_the_window_tells_the_investor_to_update_entries():
    lines = dh.update_entries_lines((issue(IssueClass.BONUS, "2026-10-14", 0.1), cash("2026-10-15", 500.0), issue(IssueClass.RIGHTS_OFFER, "2026-10-16", 0.2)))

    assert lines == ("Your share count and cost per share change from 2026-10-14; update your entries.",)


# --- the lists since the purchase date -----------------------------------------------------------------------

def test_the_dividend_list_is_per_share_and_never_added_up():
    snapshot = feed(
        cash("2025-06-30", 3000.0), cash("2026-01-12", 2000.0), cash("2026-07-28", 3000.0), cash("2024-01-01", 999.0),
    )

    lines = dh.since_purchase_lines(snapshot, d("2025-06-10"), LAST_BAR)

    assert lines[0] == (
        "Cash, per share, ex-dates since your purchase date (company-announcement source, which covers from 2017-05-15): "
        "3,000 VND (ex 2025-06-30), 2,000 VND (ex 2026-01-12), 3,000 VND (ex 2026-07-28)."
    )
    assert not re.search(r"total|sum|yield|8,000", " ".join(lines), re.I)


def test_a_complete_list_carries_no_incomplete_sentence_and_none_found_is_stated():
    lines = dh.since_purchase_lines(feed(), d("2025-06-10"), LAST_BAR)

    assert lines[0].endswith("covers from 2017-05-15): none found.")
    assert not any("incomplete" in line for line in lines)


def test_an_incomplete_list_prints_the_horizon_the_oldest_date_and_the_lag():
    snapshot = feed(cash("2023-03-02", 1000.0), oldest="2022-07-19")

    lines = dh.since_purchase_lines(snapshot, d("2022-11-15"), LAST_BAR)

    assert (
        "This list may be incomplete for ex-dates before 2022-11-16: the source returns a limited number of past "
        "announcements, the oldest stored is dated 2022-07-19, and an announcement can come up to 120 days before its ex-date."
    ) in lines
    assert not any("wrong" in line for line in lines)


def test_no_purchase_date_replaces_both_lists_with_one_sentence():
    lines = dh.since_purchase_lines(feed(cash("2026-07-28", 3000.0)), None, LAST_BAR)

    assert lines == (
        "Cash dividends and share issues since your purchase date: not listed, because no purchase date is entered for this holding.",
    )


def test_a_feed_never_fetched_adds_no_since_purchase_lines():
    assert dh.since_purchase_lines(FeedSnapshot("never_fetched"), d("2025-06-10"), LAST_BAR) == ()
    assert dh.since_purchase_lines(None, d("2025-06-10"), LAST_BAR) == ()


def test_a_stock_dividend_since_purchase_shows_the_ratio_and_no_new_share_count():
    snapshot = feed(issue(IssueClass.STOCK_DIVIDEND, "2026-09-24", 0.2604104))

    lines = dh.since_purchase_lines(snapshot, d("2026-09-01"), LAST_BAR)

    assert (
        "Share issues since your purchase date (company-announcement source; ratio not checked against your broker): "
        "ex 2026-09-24, 26.04 new shares per 100 held. They change your share count."
    ) in lines


def test_placements_and_employee_issues_are_not_listed_so_the_issues_line_says_none():
    snapshot = feed(issue(IssueClass.PRIVATE_PLACEMENT, "2025-06-24", 0.3257), issue(IssueClass.EMPLOYEE, "2025-05-07", 0.00472))

    lines = dh.since_purchase_lines(snapshot, d("2025-01-01"), LAST_BAR)

    assert lines[-1].endswith("not checked against your broker): none.")
    assert not any("32.57" in line or "0.47" in line for line in lines)


def test_a_rights_offer_since_purchase_is_read_the_notice_not_applied():
    lines = dh.since_purchase_lines(feed(issue(IssueClass.RIGHTS_OFFER, "2025-12-08", 0.2)), d("2025-11-01"), LAST_BAR)

    assert "Rights offer to shareholders, ex 2025-12-08 (company-announcement source): read the notice; not calculated and not applied to your share count." in lines
    assert not any("20 new shares" in line for line in lines)


# --- the level notes -------------------------------------------------------------------------------------------------

def test_a_level_note_for_a_dividend_after_the_level_was_entered():
    status = ((cash("2026-07-28", 3000.0), ADJUSTED),)

    (note,) = dh.level_note_lines(feed(cash("2026-07-28", 3000.0)), status, d("2026-07-15"), LAST_BAR)

    assert note == (
        "  Note from the company-announcement source: a dividend of 3,000 VND a share went ex on 2026-07-28, after you entered "
        "this level on 2026-07-15. The board price was adjusted down by about that amount that day, and this level was set "
        "before it. The brief does not change your level."
    )


def test_a_level_note_for_an_issue_and_the_status_clauses():
    event = issue(IssueClass.STOCK_DIVIDEND, "2026-09-24", 0.2604104)

    adjusted = dh.level_note_lines(feed(event), ((event, ADJUSTED),), d("2026-09-01"), LAST_BAR)[0]
    not_yet = dh.level_note_lines(feed(event), ((event, NOT_YET),), d("2026-09-01"), LAST_BAR)[0]
    unclear = dh.level_note_lines(feed(event), ((event, UNCLEAR),), d("2026-09-01"), LAST_BAR)[0]

    assert "a share issue of 26.04 new shares per 100 held went ex on 2026-09-24, after you entered this level on 2026-09-01" in adjusted
    assert adjusted.endswith("The brief does not change your level.")
    assert not_yet.endswith("The brief does not change your level. Stored history is not yet adjusted for it.")
    assert unclear.endswith("Whether stored history is adjusted for it yet could not be told.")


def test_a_level_entered_on_or_after_the_ex_date_gets_no_note_and_a_rights_offer_never_does():
    event = cash("2026-07-28", 3000.0)
    offer = issue(IssueClass.RIGHTS_OFFER, "2026-08-10", 0.2)

    assert dh.level_note_lines(feed(event), ((event, ADJUSTED),), d("2026-07-28"), LAST_BAR) == ()
    assert dh.level_note_lines(feed(event), ((event, ADJUSTED),), d("2026-08-01"), LAST_BAR) == ()
    assert dh.level_note_lines(feed(offer), (), d("2026-07-01"), LAST_BAR) == ()


def test_a_level_note_has_no_investor_text_in_it_and_the_feed_never_fetched_gives_none():
    assert dh.level_note_lines(FeedSnapshot("never_fetched"), (), d("2026-07-01"), LAST_BAR) == ()
    assert dh.level_note_lines(None, (), d("2026-07-01"), LAST_BAR) == ()


# --- the week --------------------------------------------------------------------------------------------------------

def sab_move():
    bars = sab_week_bars()
    return board_move(cash("2026-07-28", 3000.0), bars.dates, bars.closes)


def test_the_combined_week_line_names_the_dividend_in_the_sentence_of_the_board_move():
    lines = dl.board_move_lines(sab_move(), dl.issued_range_clause(2.8, True, cash("2026-07-28", 3000.0), provisional=False), feed())

    assert lines[0] == (
        "Board move: -7.7% (47.00 -> 43.40); about 3,000 VND of that is the dividend that went ex on 2026-07-28. Excluding the "
        "dividend: -1.3% (43.97 -> 43.40). Last week's range was ±2.8%: the move excluding the dividend was inside it."
    )
    assert lines[1] == (
        "Board figures are calculated from the dividend (company-announcement source, events fetched 2026-10-10 12:11 UTC) and the stored closes; "
        "check your broker's figure."
    )
    assert lines[0].index("dividend") < lines[0].index("-1.3%")  # the dividend is named before any other figure


def test_the_combined_line_without_a_range_clause_is_the_redacted_form():
    lines = dl.board_move_lines(sab_move(), "", feed())

    assert lines[0].endswith("Excluding the dividend: -1.3% (43.97 -> 43.40).") and "range" not in lines[0]


def test_the_outside_verdict_and_the_provisional_note():
    event = cash("2026-07-28", 3000.0)

    outside = dl.issued_range_clause(1.0, False, event, provisional=True)

    assert outside == " Last week's range was ±1%: the move excluding the dividend was outside it. (that range was issued from a provisional bar)"


def test_the_combined_line_for_an_issue():
    event = issue(IssueClass.STOCK_DIVIDEND, "2026-09-22", 0.2604104)
    from .test_brief_week_move import issue_bars

    bars = issue_bars()
    move = board_move(event, bars.dates, bars.closes)

    lines = dl.board_move_lines(move, dl.issued_range_clause(2.8, False, event, provisional=False), feed())

    assert lines[0] == (
        "Board move: -30.6% (50.42 -> 35.00); the price adjustment for the share issue (26.04 new shares per 100 held) that "
        "went ex on 2026-09-22 is about 20.7% of the price. Excluding the issue: -12.5% (40.00 -> 35.00). Last week's range "
        "was ±2.8%: the move excluding the issue was outside it."
    )
    assert "share issue ratio" in lines[1]


def test_the_recomputed_clause_inside_the_combined_line():
    event = cash("2026-07-28", 3000.0)
    one = WeekOne("2026-07-23", -1.3, 2.7, True, None)

    clause = dl.recomputed_range_clause(one, event)

    assert clause == " Range recomputed today from prices up to 2026-07-23; not an issued range: ±2.7%: the move excluding the dividend was inside it."
    assert dl.recomputed_range_clause(WeekOne("2026-07-23", -1.3, None, None, None), event) == ""


def plan_for(event, status, snapshot=None):
    bars = sab_week_bars()
    return week_plan(snapshot or feed(event), ((event, status),), bars.dates, bars.closes)


def test_the_note_when_history_is_not_yet_adjusted():
    event = cash("2026-07-28", 3000.0)

    lines = dl.week_note_lines(plan_for(event, NOT_YET), "SAB", feed(event))

    assert lines == (
        "Ex-dividend 2026-07-28 (3,000 VND a share) fell in this week (company-announcement source, events fetched 2026-10-10 12:11 UTC). History is not yet adjusted "
        "for the 2026-07-28 dividend; the stored move includes it.",
    )


def test_the_issue_forms_of_the_week_notes():
    event = issue(IssueClass.BONUS, "2026-07-28", 0.1)

    not_yet = dl.week_note_lines(plan_for(event, NOT_YET), "SAB", feed(event))[0]
    unclear = dl.week_note_lines(plan_for(event, UNCLEAR), "SAB", feed(event))[0]

    assert "Share issue ex 2026-07-28 (10 new shares per 100 held) fell in this week (company-announcement source, events fetched 2026-10-10 12:11 UTC)." in not_yet
    assert "the stored move includes its effect on the price." in not_yet
    assert "cannot be told" in unclear and "leave out its effect on the price" in unclear


def test_the_unclear_note_claims_no_cause_it_did_not_measure():
    for sentence in (wording.WEEK_UNCLEAR_CASH, wording.WEEK_UNCLEAR_ISSUE, wording.READJUSTED_EXPLAINS_CASH, wording.READJUSTED_EXPLAINS_ISSUE):
        assert not re.search(r"ordinary day|would explain|because", sentence)


def test_the_note_when_it_cannot_be_told():
    lines = dl.week_note_lines(plan_for(cash("2026-07-28", 3000.0), UNCLEAR), "SAB", feed())

    assert lines[0].endswith(
        "Whether stored history is adjusted for the 2026-07-28 dividend yet cannot be told from the stored bars; "
        "the move shown may include or leave out the dividend."
    )


def test_two_events_list_each_status_and_no_board_move():
    first, second = cash("2026-07-28", 3000.0), cash("2026-07-29", 500.0)
    bars = sab_week_bars()
    plan = week_plan(feed(first, second), ((first, ADJUSTED), (second, NOT_YET)), bars.dates, bars.closes)

    (line,) = dl.week_note_lines(plan, "SAB", feed(first, second))

    assert line == (
        "Ex-dates in this week (company-announcement source, events fetched 2026-10-10 12:11 UTC): 2026-07-28 and 2026-07-29. A board move is not calculated for "
        "more than one. Adjustment status by date: 2026-07-28 adjusted, 2026-07-29 not yet adjusted."
    )


@pytest.mark.parametrize("snapshot", [FeedSnapshot("never_fetched"), FeedSnapshot("never_succeeded")])
def test_an_unknown_week_says_so(snapshot):
    bars = sab_week_bars()
    plan = week_plan(snapshot, (), bars.dates, bars.closes)

    assert dl.week_note_lines(plan, "SAB", snapshot) == ("Whether an ex-date fell in this week is not known: no stored events are available for SAB.",)


def test_no_note_when_no_ex_date_fell_in_the_week_or_the_week_is_combined():
    bars = sab_week_bars()

    assert dl.week_note_lines(week_plan(feed(), (), bars.dates, bars.closes), "SAB", feed()) == ()
    assert dl.week_note_lines(plan_for(cash("2026-07-28", 3000.0), ADJUSTED), "SAB", feed()) == ()
    assert dl.week_note_lines(None, "SAB", feed()) == ()


def test_the_week_1_line_with_and_without_a_comparison():
    inside = dl.week_one_lines(WeekOne("2026-10-02", 1.1, 2.7, True, None), feed())
    outside = dl.week_one_lines(WeekOne("2026-10-02", 3.4, 2.7, False, None), feed())
    unknown = dl.week_one_lines(WeekOne("2026-10-02", -1.3, 2.7, None, "unknown"), FeedSnapshot("never_fetched"))
    fell = dl.week_one_lines(WeekOne("2026-10-02", -1.3, 2.7, None, "not_adjusted"), feed())

    assert inside == (
        "Recomputed today from prices up to 2026-10-02; not an issued range: ±2.7%. The week's move of +1.1% was inside it. "
        "Ex-dates checked against the company-announcement source, events fetched 2026-10-10 12:11 UTC.",
    )
    assert "The week's move of +3.4% was outside it." in outside[0]
    assert unknown[0].endswith("The week's move of -1.3% is not compared with it: whether an ex-date fell in this week is not known.")
    assert "is not compared with it: an ex-date fell in this week. Ex-dates checked against the company-announcement source" in fell[0]


def test_the_week_1_line_says_when_it_could_not_be_recomputed():
    assert dl.week_one_lines(WeekOne("2026-10-02", 1.1, None, None, None)) == (
        "Last week's range could not be recomputed from the stored prices.",
    )


def test_the_explanation_line_of_the_readjusted_note():
    lines = dl.readjusted_explanation_lines(
        (cash("2026-07-28", 3000.0), issue(IssueClass.STOCK_DIVIDEND, "2026-09-24", 0.2604104)), d("2026-07-23"),
    )

    assert lines == (
        "The company-announcement source lists a dividend of 3,000 VND a share ex 2026-07-28, after 2026-07-23; the brief has not checked that it accounts for the difference.",
        "The company-announcement source lists a share issue of 26.04 new shares per 100 held ex 2026-09-24, after 2026-07-23; the brief has not checked that it accounts for the difference.",
    )
    assert dl.readjusted_explanation_lines((), d("2026-07-23")) == ()


# --- what no line may contain ----------------------------------------------------------------------------------------

def _every_rendered_line() -> list[str]:
    event = cash("2026-07-28", 3000.0, record="2026-07-29", payout="2026-08-28")
    bonus = issue(IssueClass.BONUS, "2026-09-24", 0.2604104)
    rights = issue(IssueClass.RIGHTS_OFFER, "2026-10-14", 0.2)
    pending = issue(IssueClass.BONUS, None, 0.1279, published="2026-04-28")
    old = issue(IssueClass.STOCK_DIVIDEND, None, 0.2, published="2020-06-26")
    snapshot = feed(event, bonus, rights, pending, old, cash("2026-10-14", 2000.0), unreadable=1, failed_at=FETCHED_AT)
    status = ((event, NOT_YET), (bonus, UNCLEAR))
    in_window = ca.events_in_window(snapshot.events, LAST_BAR)
    lines = [
        *dl.header_lines("SAB", snapshot, LAST_BAR), *dl.header_lines("ZZZ", FeedSnapshot("never_fetched"), LAST_BAR),
        *dl.scheduled_lines(snapshot, LAST_BAR), *dl.window_lines(in_window, (41.74, 44.06)),
        *dh.since_purchase_lines(snapshot, d("2025-06-10"), LAST_BAR), *dh.since_purchase_lines(snapshot, None, LAST_BAR),
        *dh.update_entries_lines(in_window), *dh.level_note_lines(snapshot, status, d("2026-07-01"), LAST_BAR),
        *dl.board_move_lines(sab_move(), dl.issued_range_clause(2.8, True, event, provisional=False), snapshot),
        *dl.week_note_lines(plan_for(event, NOT_YET), "SAB", feed(event)), *dl.week_one_lines(WeekOne("2026-10-02", 1.1, 2.7, True, None)),
        *dl.readjusted_explanation_lines((event,), d("2026-07-23")),
    ]
    return lines


def test_no_line_has_a_total_a_net_figure_an_amount_on_shares_or_a_new_share_count():
    text = "\n".join(_every_rendered_line())

    assert not re.search(r"\b(total|net|yield|entitle\w*|multiplier|factor)\b", text, re.I)
    assert not re.search(r"3,000,000|1,000 shares|new share count", text)


def test_every_feed_derived_line_names_its_source():
    for line in _every_rendered_line():
        feed_line = re.match(r"\s*(DIVIDENDS|Scheduled|Ex-date in the window|Share issue in the window|Rights offer|Cash, per share|Note from|Ex-dividend|Share issue ex|The company-announcement)", line)
        if feed_line:
            assert LABEL in line, line


def test_every_line_where_the_feed_decides_states_when_its_events_were_fetched():
    stamp = re.compile(r"events (last )?fetched 2026-10-10 12:11 UTC")
    event = cash("2026-07-28", 3000.0)
    snapshot = feed(event, cash("2026-10-14", 2000.0))
    deciding = [
        dl.header_lines("SAB", snapshot, LAST_BAR)[0], dl.scheduled_lines(snapshot, LAST_BAR)[0],
        dl.board_move_lines(sab_move(), "", snapshot)[1], dl.week_note_lines(plan_for(event, NOT_YET), "SAB", snapshot)[0],
        dl.week_one_lines(WeekOne("2026-10-02", 1.1, 2.7, True, None), snapshot)[0],
        dl.week_one_lines(WeekOne("2026-10-02", 1.1, 2.7, None, "not_adjusted"), snapshot)[0],
    ]

    assert all(stamp.search(line) for line in deciding), [line for line in deciding if not stamp.search(line)]


def test_every_rendered_line_passes_the_text_guard_and_the_brief_has_no_judgement_word():
    for line in _every_rendered_line():
        assert wording.tool_text_violations(line) == [], line


def test_the_new_constants_are_in_the_scanned_set_and_free_of_transaction_words():
    scanned = set(wording.fixed_sentences())
    new = (
        wording.DIVIDENDS_HEADER, wording.NOT_FETCHED, wording.SCHEDULED, wording.WINDOW_CASH, wording.LEVEL_NOTE_CASH,
        wording.BOARD_CASH, wording.WEEK_SEVERAL, wording.WEEK_ONE, wording.READJUSTED_EXPLAINS_CASH, wording.UPDATE_ENTRIES,
        wording.STATUS_NOT_YET, wording.WEEK_ONE_REASONS["unknown"], wording.STATUS_WORDS["UNCLEAR"],
    )

    assert set(new) <= scanned
    for sentence in scanned:
        assert wording.tool_text_violations(sentence) == [], sentence
    assert not any(re.search(r"\b(buy|sell|hold)\b", s, re.I) for s in scanned)


def test_the_only_instruction_is_the_owner_approved_update_your_entries():
    assert wording.UPDATE_ENTRIES.endswith("update your entries.")
    others = [s for s in wording.fixed_sentences() if re.search(r"\b(should|must|consider|recommend)\b", s, re.I)]
    assert others == []
