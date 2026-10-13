"""The COMPANY block (`add-announcement-tags-and-insider-sizing`): its parts, tags, source-health line, the quiet
small-issue line and the one Scheduled line. Synthetic announcements only; no log, no network."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from app.services.brief.feed_source import FeedSnapshot, IssueClass
from app.services.brief.sections_company import company_lines

from .brief_announcement_rows import d, health, make_announcement, make_company, make_issue_item, make_trade_item
from .test_brief_support import brief_isolation, make_facts  # noqa: F401

FETCHED = datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc)


def _facts(items=(), *, feed="default", **company):
    if feed == "default":
        feed = FeedSnapshot("fetched", (), None, 0, FETCHED, FETCHED, False)
    return make_facts("AAA", company=make_company(items, **company), feed=feed)


def _text(facts, *, redact=False) -> str:
    return "\n".join(company_lines(facts, redact=redact))


def _news(text, *, published="2026-10-08", **fields):
    return make_announcement("news", f"AAA: {text}", published=published, **fields)


# --- the block exists only when the announcements were read --------------------------------------------------

def test_facts_without_announcement_facts_get_no_block():
    assert company_lines(make_facts("AAA"), redact=False) == ()


def test_a_holding_without_a_last_bar_gets_no_block():
    assert company_lines(make_facts("AAA", company=make_company(), last_bar=None, close=None), redact=False) == ()


def test_the_block_opens_with_its_heading_naming_the_source_and_the_third_party_label():
    lines = company_lines(_facts(), redact=False)

    assert lines[0].startswith("COMPANY (company-announcement source from VCI; text in curly quotes is third-party text")


# --- Needs a look and For information --------------------------------------------------------------------------

def test_a_new_insider_registration_is_under_needs_a_look_with_its_tag_and_basis():
    text = _text(_facts([make_trade_item("AAA", published="2026-10-08")]))

    needs = text.split("Needs a look since the last brief:")[1].split("For information:")[0]
    assert "- 2026-10-08, Insider or major-shareholder trade (event record)" in needs
    assert "For information: none found in what the source returned" in text


def test_an_item_before_the_previous_brief_is_not_listed_and_a_late_one_is():
    old = make_announcement("events", "x", published="2026-09-20", event_code="DIV")
    late = make_announcement("events", "y", published="2026-09-20", first_seen=d("2026-10-05"), event_code="DIV")

    assert "- 2026-09-20" not in _text(_facts([old]))
    assert "- 2026-09-20, Dividend (event record)" in _text(_facts([late]))


def test_a_registration_still_open_is_listed_again_and_marked():
    open_window = make_trade_item("AAA", published="2026-09-28", start="2026-10-01", end="2026-10-20")

    text = _text(_facts([open_window]))

    assert "listed again: window still open" in text.split("For information:")[0]


def test_the_first_brief_lists_the_last_14_days_and_says_so():
    recent = make_trade_item("AAA", published="2026-09-26")
    older = make_trade_item("AAA", published="2026-09-20", name="Fictional Old Ltd", start="2026-09-01", end="2026-09-30")

    text = _text(_facts([recent, older], previous=None))

    assert "Needs a look, last 14 days (there is no earlier brief for this ticker, so the last 14 calendar days are listed):" in text
    assert "- 2026-09-26," in text and "- 2026-09-20," not in text


def test_many_items_for_information_show_the_newest_ten_and_count_the_rest():
    items = [make_announcement("events", f"t{i}", published=f"2026-10-{1 + i % 8:02d}", event_code="DIV") for i in range(14)]

    text = _text(_facts(items, previous="2026-09-20"))

    assert text.count("\n- 2026-10-") == 10 and "4 more item(s) for information exist and are not shown (the newest 10 are shown)." in text


def test_nothing_found_versus_not_checked():
    assert "Needs a look since the last brief: none found in what the source returned" in _text(_facts())
    never = _facts(news=health("never_fetched"), events=health("never_fetched"), feed=FeedSnapshot("never_fetched"))

    text = _text(never)

    assert "Needs a look since the last brief: not checked" in text and "For information: not checked" in text
    assert "none found" not in text


def test_when_only_one_kind_was_fetched_none_found_names_the_kind_that_was_not():
    text = _text(_facts(news=health("never_fetched")))

    assert "none found in what the source returned (announcement source not checked)" in text


def test_a_failed_only_source_is_not_checked_either():
    text = _text(_facts(news=health("never_succeeded"), events=health("never_succeeded")))

    assert "For information: not checked" in text


# --- tags and basis --------------------------------------------------------------------------------------------

def test_a_board_resolution_is_unclassified_with_the_no_amount_sentence_and_nothing_is_called_routine():
    text = _text(_facts([_news("nghị quyết HĐQT")]))

    assert "- 2026-10-08, Other announcement, not classified; the title gives no amount" in text
    assert "The title does not give the amount; the notice does." in text
    assert not re.search(r"routine|minor|administrative", text, re.I)


def test_a_press_item_is_labelled_and_listed_for_information():
    text = _text(_facts([make_announcement("news", "A sector headline", published="2026-10-08")]))

    assert "Press item (may concern another company; not classified)" in text.split("For information:")[1]


def test_a_keyword_class_enabled_by_parameter_tags_with_the_title_keyword_basis():
    item = _news("cổ tức bằng tiền")

    assert "Other announcement, not classified" in _text(_facts([item]))  # disabled by default
    enabled = _text(_facts([item], enabled={"dividend"}))

    assert "- 2026-10-08, Dividend (title keyword)" in enabled


def test_a_titles_are_original_language_and_only_inside_curly_quotes():
    text = _text(_facts([_news("Đại hội đồng cổ đông thường niên")]))

    assert "Title (third-party text): “AAA: Đại hội đồng cổ đông thường niên”" in text


def test_markup_in_a_title_cannot_reach_the_block():
    nasty = make_announcement("news", "AAA: <b>x</b> [a](https://example.invalid/z) | y <", published="2026-10-08")

    text = _text(_facts([nasty]))

    assert "https://" not in text and "|" not in text and "[a]" not in text and "<" not in text and "(link removed)" in text


def test_a_share_issue_shows_its_class_ratio_and_dates_from_the_record_and_the_range_sentence():
    bonus = make_issue_item(IssueClass.BONUS, 0.1, published="2026-10-06", ex="2026-10-20", record="2026-10-21", title="synthetic issue title")

    text = _text(_facts([bonus]))

    assert "- 2026-10-06, Share issue or capital change (event record)" in text
    assert "From the event record: bonus shares; 10 new shares per 100 held; ex-date 2026-10-20; record date 2026-10-21." in text
    assert "The usual range is built from past prices only." in text


def test_an_additional_listing_is_for_information_without_the_range_sentence():
    text = _text(_facts([make_issue_item(IssueClass.OTHER, None, code="AIS", title="synthetic listing")]))

    assert "Share issue or capital change (event record)" in text.split("For information:")[1]
    assert "The usual range is built" not in text


# --- the small-issue summary -------------------------------------------------------------------------------------

def test_three_employee_issues_are_summarised_and_not_listed():
    issues = [make_issue_item(IssueClass.EMPLOYEE, r, title=f"issue {i}") for i, r in enumerate((0.001, 0.003, 0.005))]

    text = _text(_facts(issues))

    assert "3 small share issue(s), each under 1% of the shares (employee issues), not listed." in text
    assert "issue 0" not in text and "Needs a look since the last brief: none found" in text
    assert text.index("small share issue(s)") > text.index("For information:")


def test_a_material_bonus_is_listed_and_not_counted_in_the_summary():
    text = _text(_facts([make_issue_item(IssueClass.BONUS, 0.10, ex="2026-10-20")]))

    assert "small share issue" not in text and "Share issue or capital change (event record)" in text.split("For information:")[0]


def test_an_employee_issue_with_ratio_zero_uses_the_unstated_size_wording():
    text = _text(_facts([make_issue_item(IssueClass.EMPLOYEE, 0.0), make_issue_item(IssueClass.EMPLOYEE, 0.004)]))

    assert "2 small share issue(s), each under 1% of the shares or of unstated size (employee issues), not listed." in text


def test_the_summary_names_the_classes_present_with_no_title_or_date():
    issues = [make_issue_item(IssueClass.EMPLOYEE, 0.002, title="secret-title-1"), make_issue_item(IssueClass.BONUS, 0.004, title="secret-title-2")]

    line = next(l for l in company_lines(_facts(issues), redact=False) if "small share issue" in l)

    assert "(employee issues, bonus issues)" in line and "secret-title" not in line and not re.search(r"\d{4}-\d{2}", line)


def test_no_small_issue_means_no_summary_and_an_unchecked_source_means_none():
    assert "small share issue" not in _text(_facts())
    unchecked = _facts([make_issue_item(IssueClass.EMPLOYEE, 0.002)], news=health("never_fetched"), events=health("never_fetched"))

    assert "small share issue" not in _text(unchecked)


# --- source health ------------------------------------------------------------------------------------------------

def test_answered_with_an_old_newest_item_prints_both_dates_the_count_the_limit_and_the_gap():
    facts = _facts(news=health(n=50, newest="2026-08-28"), events=health(n=12, newest="2026-10-08"))

    text = _text(facts)

    assert (
        "announcement source answered 2026-10-10; 50 items returned; newest 2026-08-28 (the source's limit per call; older "
        "items are not retrievable), 42 days before the last bar; nothing newer was returned; the last answer was 1 calendar day after the last bar"
    ) in text
    assert "corporate events: answered 2026-10-10; 12 items returned; newest 2026-10-08, 1 day before the last bar; nothing newer was returned; the last answer was 1 calendar day after the last bar" in text
    assert "stale" not in text.lower()


def test_the_age_of_the_answer_is_printed_without_a_stale_label():
    facts = _facts(news=health(answered="2026-10-04"), events=health(answered="2026-10-04"))

    text = _text(facts)

    assert "the last answer was 5 calendar days before the last bar" in text and "An announcement made after the last fetch is not shown." in text
    assert "stale" not in text.lower()


def test_a_failed_latest_attempt_names_its_date_error_class_and_the_last_answer():
    facts = _facts(news=health(failed=True, error="rate_limited", answered="2026-10-01", attempt="2026-10-09T08:00:00"))

    text = _text(facts)

    assert "announcement source: the latest attempt 2026-10-09 08:00 UTC failed (rate_limited); last answer 2026-10-01" in text
    assert "To fetch (run by hand; this brief does not run it): python backend/scripts/snapshot_company_feed.py --tickers AAA" in text


def test_never_fetched_says_so_and_prints_the_command_but_does_not_run_it():
    text = _text(_facts(news=health("never_fetched"), events=health("never_fetched"), feed=FeedSnapshot("never_fetched")))

    assert "announcement source: never fetched for AAA; announcements not checked" in text
    assert "corporate events: never fetched for AAA; announcements not checked" in text
    assert "To fetch (run by hand; this brief does not run it):" in text and "An announcement made after the last fetch is not shown." not in text.split("Scheduled")[0]


def test_never_succeeded_and_unreadable_have_their_own_wording():
    text = _text(_facts(news=health("never_succeeded"), events=health("unreadable")))

    assert "announcement source: no fetch has succeeded yet for AAA; announcements not checked" in text
    assert "corporate events: the stored items could not be read this run, which is not the same as none found or never fetched" in text


def test_an_answer_with_no_items_says_none_stored():
    text = _text(_facts(news=health(n=0, newest=None)))

    assert "announcement source answered 2026-10-10; 0 items returned; newest no item stored" in text


def test_unreadable_rows_are_counted():
    assert "2 stored announcement row(s) could not be read (company-announcement source)." in _text(_facts(unreadable=2))


# --- the one Scheduled line ---------------------------------------------------------------------------------------

def _feed(*events):
    return FeedSnapshot("fetched", tuple(events), None, 0, FETCHED, FETCHED, False)


def test_a_meeting_with_a_record_date_in_the_window_is_scheduled_with_its_field_name_and_no_meeting_date_claim():
    meeting = make_announcement("events", "synthetic meeting", published="2026-09-01", event_code="AGME", record_date="2026-10-12")

    text = _text(_facts([meeting]))

    assert "shareholder meeting event, source dates: record_date 2026-10-12" in text
    assert not re.search(r"meeting date (is|was)|meeting on", text)
    assert text.splitlines()[-1].endswith("An announcement made after the last fetch is not shown.")


def test_all_three_source_dates_of_a_meeting_are_printed_with_their_names():
    meeting = make_announcement(
        "events", "m", published="2026-09-01", event_code="EGME", record_date="2026-10-12", exright_date="2026-10-13", issue_date="2026-10-15",
    )

    text = _text(_facts([meeting]))

    assert "extraordinary shareholder meeting event, source dates: record_date 2026-10-12, exright_date 2026-10-13, issue_date 2026-10-15" in text


@pytest.mark.parametrize("date_text", ["2026-10-09", "2026-10-17", "2026-09-30"])
def test_a_meeting_date_on_or_before_the_last_bar_or_past_the_window_is_not_scheduled(date_text):
    meeting = make_announcement("events", "m", published="2026-09-01", event_code="AGME", record_date=date_text)

    assert "shareholder meeting event, source dates" not in _text(_facts([meeting]))


def test_a_scheduled_dividend_appears_on_the_company_scheduled_line_once():
    from app.services.brief.feed_source import Event

    cash = Event("DIV", d("2026-10-13"), d("2026-10-14"), None, 2000.0, None, d("2026-09-20"), None)

    text = _text(_facts(feed=_feed(cash)))

    assert text.count("Scheduled (") == 1 and "ex 2026-10-13, 2,000 VND a share, record 2026-10-14" in text


def test_nothing_scheduled_after_a_fetch_reads_none_found():
    assert "dated after the last bar, 2026-10-09): none found. An announcement made after the last fetch is not shown." in _text(_facts())


def test_an_unfetched_event_source_reads_not_checked_and_never_none():
    for feed in (None, FeedSnapshot("never_fetched"), FeedSnapshot("never_succeeded"), FeedSnapshot("unreadable")):
        text = _text(_facts(feed=feed))

        assert "Scheduled (company-announcement source): not checked" in text and "dated after the last bar" not in text


# --- the redacted copy ---------------------------------------------------------------------------------------------

def test_the_redacted_block_uses_the_fixed_period_and_never_mentions_the_issued_log():
    item = make_trade_item("AAA", published="2026-09-26")
    with_previous, without = _facts([item], previous="2026-10-02"), _facts([item], previous=None)

    redacted_with, redacted_without = _text(with_previous, redact=True), _text(without, redact=True)

    assert redacted_with == redacted_without
    assert "Needs a look, last 14 days before the last bar:" in redacted_with
    assert not re.search(r"since the last brief|first brief|earlier brief", redacted_with)


def test_the_full_block_does_differ_with_and_without_a_previous_brief():
    item = make_trade_item("AAA", published="2026-09-26")

    assert _text(_facts([item], previous="2026-10-02")) != _text(_facts([item], previous=None))


def test_needs_a_look_shows_the_newest_ten_and_counts_the_rest():
    items = [make_trade_item("AAA", name=f"Fictional {i} Ltd", published=f"2026-10-{3 + i % 6:02d}") for i in range(14)]

    text = _text(_facts(items))

    needs = text.split("For information:")[0]
    assert needs.count("\n- 2026-10-") == 10
    assert "4 more item(s) under this heading exist and are not shown (the newest 10 are shown)." in needs


def test_the_trigger_count_counts_every_listed_trade_not_only_the_ten_shown():
    from app.services.brief.sections_company import trades_trigger_count

    items = [make_trade_item("AAA", name=f"Fictional {i} Ltd", published="2026-10-08") for i in range(14)]

    assert trades_trigger_count((_facts(items),)).count == 14
