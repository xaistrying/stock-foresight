"""Tags, listing and the needs-a-look split (`add-announcement-tags-and-insider-sizing`, "The COMPANY block separates ...",
"Announcements carry a type tag and a basis, and no tag says routine", "Keyword classes are enabled only after a labelled
accuracy check")."""

from __future__ import annotations

import re
import unicodedata

import pytest

from app.services.brief import announcement_keywords as kw
from app.services.brief.announcements import (
    FIRST_BRIEF_LOOKBACK_DAYS, INFO_ITEMS_MAX, NEEDS_ITEMS_MAX, Tag, build_listing, classify, is_new,
)
from app.services.brief.feed_source import IssueClass

from .brief_announcement_rows import d, make_announcement, make_issue_item, make_trade_item
from .test_brief_support import brief_isolation  # noqa: F401

ALL = frozenset(kw.KEYWORDS)
LAST_BAR = d("2026-10-09")
PREVIOUS = d("2026-10-02")


def _news(text, *, published="2026-10-08", **fields):
    return make_announcement("news", f"AAA: {text}", published=published, **fields)


# --- event-record tags ---------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("code", "tag"),
    [("DDIND", Tag.TRADE), ("DDINS", Tag.TRADE), ("DDRP", Tag.TRADE), ("ISS", Tag.CAPITAL), ("AIS", Tag.CAPITAL),
     ("DIV", Tag.DIVIDEND), ("AGME", Tag.MEETING), ("EGME", Tag.MEETING), ("OTHE", Tag.UNCLASSIFIED), ("SUSP", Tag.UNCLASSIFIED),
     ("AGMR", Tag.UNCLASSIFIED), ("MA", Tag.UNCLASSIFIED), ("MOVE", Tag.UNCLASSIFIED), ("NLIS", Tag.UNCLASSIFIED),
     ("RETU", Tag.UNCLASSIFIED), ("ZZZZ", Tag.UNCLASSIFIED), (None, Tag.UNCLASSIFIED)],
)
def test_the_event_code_gives_the_tag_and_the_basis_event_record(code, tag):
    got = classify(make_announcement("events", "title with no keyword", event_code=code), "AAA")

    assert got.tag is tag
    assert got.basis == ("event record" if tag is not Tag.UNCLASSIFIED else None)


def test_an_insider_code_is_tagged_without_keywords_even_when_a_class_is_enabled():
    got = classify(make_trade_item("AAA", title="Name - Đăng kí Bán 5 AAA"), "AAA", ALL)

    assert (got.tag, got.basis) == (Tag.TRADE, "event record")


def test_an_event_title_is_never_keyword_classified():
    got = classify(make_announcement("events", "AAA: cổ tức", event_code="OTHE"), "AAA", ALL)

    assert got.tag is Tag.UNCLASSIFIED


# --- keyword tags -------------------------------------------------------------------------------------

def test_only_the_classes_that_passed_the_labelled_check_are_enabled():
    assert kw.ENABLED_KEYWORD_CLASSES == frozenset({kw.CAPITAL, kw.MEETING, kw.PERSONNEL})
    assert kw.DIVIDEND not in kw.ENABLED_KEYWORD_CLASSES and kw.RESULTS not in kw.ENABLED_KEYWORD_CLASSES


def test_a_disabled_class_leaves_a_title_unclassified_and_an_enabled_one_does_not():
    assert classify(_news("thông báo chi trả cổ tức bằng tiền"), "AAA").tag is Tag.UNCLASSIFIED  # dividend: disabled
    assert classify(_news("thông báo ký hợp đồng kiểm toán BCTC"), "AAA").tag is Tag.UNCLASSIFIED  # results: disabled
    assert classify(_news("AAA: phát hành cổ phiếu thưởng"), "AAA").tag is not Tag.UNCLASSIFIED  # capital: enabled


@pytest.mark.parametrize(
    ("phrase", "tag"),
    [("cổ tức bằng tiền", Tag.DIVIDEND), ("đại hội đồng cổ đông thường niên", Tag.MEETING), ("báo cáo tài chính quý", Tag.RESULTS),
     ("bổ nhiệm phó giám đốc", Tag.PERSONNEL), ("tăng vốn điều lệ", Tag.CAPITAL)],
)
def test_an_enabled_class_tags_a_company_filing_with_the_basis_title_keyword(phrase, tag):
    got = classify(_news(phrase), "AAA", ALL)

    assert (got.tag, got.basis) == (tag, "title keyword")


def test_a_class_not_enabled_leaves_its_titles_unclassified():
    got = classify(_news("báo cáo tài chính quý"), "AAA", frozenset({kw.DIVIDEND}))

    assert got.tag is Tag.UNCLASSIFIED


def test_the_capital_class_wins_over_the_dividend_class():
    assert classify(_news("trả cổ tức bằng cổ phiếu thưởng"), "AAA", ALL).tag is Tag.CAPITAL


def test_two_non_capital_classes_give_unclassified():
    assert classify(_news("báo cáo tài chính và bổ nhiệm"), "AAA", ALL).tag is Tag.UNCLASSIFIED


@pytest.mark.parametrize(
    "phrase",
    ["mua lại trước hạn trái phiếu", "phát hành trái phiếu riêng lẻ", "nhận thông báo xử phạt thuế",
     "dỡ bỏ hạn chế chuyển nhượng cổ phiếu ESOP", "nghị quyết HĐQT", "Nghị quyết Hội đồng quản trị"],
)
def test_a_bond_a_penalty_a_transfer_restriction_and_a_bare_board_resolution_match_no_class(phrase):
    assert classify(_news(phrase), "AAA", ALL).tag is Tag.UNCLASSIFIED


@pytest.mark.parametrize("title", ["Some headline about the sector", "AAAA: other ticker", "BBB: cổ tức", "AAA cổ tức"])
def test_a_news_title_not_starting_with_the_ticker_and_a_colon_is_a_press_item(title):
    got = classify(make_announcement("news", title), "AAA", ALL)

    assert got.tag is Tag.PRESS and got.basis is None


def test_the_keyword_match_ignores_case_and_normalisation():
    assert classify(_news(unicodedata.normalize("NFD", "CỔ TỨC bằng tiền")), "AAA", ALL).tag is Tag.DIVIDEND


def test_the_word_routine_is_in_no_keyword_and_no_tag():
    assert not any("routine" in p for ps in kw.KEYWORDS.values() for p in ps)
    assert not any("routine" in t.value or "routine" in t.name.lower() for t in Tag)


# --- membership ------------------------------------------------------------------------------------------

def test_an_item_after_the_previous_last_bar_is_new():
    assert is_new(make_announcement(published="2026-10-03"), LAST_BAR, PREVIOUS)
    assert not is_new(make_announcement(published="2026-10-02"), LAST_BAR, PREVIOUS)  # on the previous bar: already seen


def test_a_late_snapshot_item_first_seen_after_the_previous_bar_is_new_unless_from_the_first_fetch():
    late = make_announcement(published="2026-09-20", first_seen=d("2026-10-05"))
    history = make_announcement(published="2026-09-20", first_seen=d("2026-10-05"), from_first_fetch=True)

    assert is_new(late, LAST_BAR, PREVIOUS) and not is_new(history, LAST_BAR, PREVIOUS)


def test_with_no_previous_brief_the_last_fourteen_days_are_listed():
    assert FIRST_BRIEF_LOOKBACK_DAYS == 14
    assert is_new(make_announcement(published="2026-09-25"), LAST_BAR, None)
    assert not is_new(make_announcement(published="2026-09-24"), LAST_BAR, None)


def test_a_new_insider_registration_is_listed_under_needs_a_look_and_not_for_information():
    listing = build_listing((make_trade_item("AAA", published="2026-10-08"),), "AAA", LAST_BAR, PREVIOUS)

    assert [l.classified.tag for l in listing.needs_look] == [Tag.TRADE] and listing.information == ()
    assert listing.needs_look[0].is_new and not listing.needs_look[0].relisted


def test_an_open_registration_from_last_week_is_listed_again_marked_relisted():
    old = make_trade_item("AAA", published="2026-09-28", start="2026-10-01", end="2026-10-20")

    listing = build_listing((old,), "AAA", LAST_BAR, PREVIOUS)

    assert [(l.is_new, l.relisted) for l in listing.needs_look] == [(False, True)]


def test_a_registration_whose_window_ended_is_not_listed_again():
    old = make_trade_item("AAA", published="2026-09-28", start="2026-09-29", end="2026-10-05")

    assert build_listing((old,), "AAA", LAST_BAR, PREVIOUS).needs_look == ()


def test_the_first_brief_flag_is_set_only_without_a_previous_brief():
    assert build_listing((), "AAA", LAST_BAR, None).lookback is True
    assert build_listing((), "AAA", LAST_BAR, PREVIOUS).lookback is False


def test_for_information_keeps_the_newest_ten_and_counts_the_rest():
    items = tuple(make_announcement("events", f"t{i}", published=f"2026-10-{1 + i % 8:02d}", event_code="DIV") for i in range(14))

    listing = build_listing(items, "AAA", LAST_BAR, d("2026-09-20"))

    assert INFO_ITEMS_MAX == 10 and len(listing.information_shown) == 10 and listing.information_more == 4
    dates = [l.classified.item.published_at for l in listing.information]
    assert dates == sorted(dates, reverse=True)


def test_needs_a_look_is_listed_in_full_but_shows_the_newest_ten():
    items = tuple(make_trade_item("AAA", name=f"Fictional {i} Ltd", published=f"2026-10-{3 + i % 6:02d}") for i in range(25))

    listing = build_listing(items, "AAA", LAST_BAR, PREVIOUS)

    assert len(listing.needs_look) == 25 and len(listing.needs_shown) == 10 and listing.needs_more == 15 and NEEDS_ITEMS_MAX == 10
    assert listing.needs_shown == listing.needs_look[:10]  # newest first


# --- the capital-change tag: material, small and additional listings --------------------------------------

def test_a_material_issue_is_listed_under_needs_a_look():
    bonus = make_issue_item(IssueClass.BONUS, 0.10, ex="2026-10-20")

    listing = build_listing((bonus,), "AAA", LAST_BAR, PREVIOUS)

    assert [l.classified.tag for l in listing.needs_look] == [Tag.CAPITAL] and listing.small_issues == ()


def test_a_non_employee_issue_of_unknown_size_is_material():
    placement = make_issue_item(IssueClass.PRIVATE_PLACEMENT, 0.0)

    assert len(build_listing((placement,), "AAA", LAST_BAR, PREVIOUS).needs_look) == 1


def test_small_issues_are_counted_and_not_listed():
    issues = (
        make_issue_item(IssueClass.EMPLOYEE, 0.001), make_issue_item(IssueClass.EMPLOYEE, 0.003),
        make_issue_item(IssueClass.EMPLOYEE, 0.005), make_issue_item(IssueClass.EMPLOYEE, 0.0),
        make_issue_item(IssueClass.EMPLOYEE, None), make_issue_item(IssueClass.BONUS, 0.004),
    )

    listing = build_listing(issues, "AAA", LAST_BAR, PREVIOUS)

    assert len(listing.small_issues) == 6 and listing.needs_look == () and listing.information == ()


def test_an_additional_listing_goes_to_for_information_with_the_capital_tag_and_is_never_small():
    ais = make_issue_item(IssueClass.OTHER, None, code="AIS")

    listing = build_listing((ais,), "AAA", LAST_BAR, PREVIOUS)

    assert listing.needs_look == () and listing.small_issues == ()
    assert [(l.classified.tag, l.classified.basis) for l in listing.information] == [(Tag.CAPITAL, "event record")]


def test_a_keyword_capital_change_in_a_company_filing_goes_under_needs_a_look():
    listing = build_listing((_news("tăng vốn điều lệ"),), "AAA", LAST_BAR, PREVIOUS, ALL)

    assert [l.classified.tag for l in listing.needs_look] == [Tag.CAPITAL]


def test_unclassified_and_press_items_are_for_information():
    items = (_news("nghị quyết HĐQT"), make_announcement("news", "A press headline"))

    listing = build_listing(items, "AAA", LAST_BAR, PREVIOUS)

    assert {l.classified.tag for l in listing.information} == {Tag.UNCLASSIFIED, Tag.PRESS} and listing.needs_look == ()


def test_the_listing_is_empty_when_nothing_is_new():
    old = make_announcement(published="2026-09-01", event_code="DIV")

    assert build_listing((old,), "AAA", LAST_BAR, PREVIOUS).information == ()


def test_the_sorting_is_newest_first_for_needs_a_look():
    items = (make_trade_item("AAA", name="Old", published="2026-10-03"), make_trade_item("AAA", name="New", published="2026-10-08"))

    dates = [l.classified.item.published_at for l in build_listing(items, "AAA", LAST_BAR, PREVIOUS).needs_look]

    assert dates == [d("2026-10-08"), d("2026-10-03")]


def test_no_tag_label_or_keyword_says_routine_minor_or_administrative():
    text = " ".join(t.value for t in Tag) + " ".join(p for ps in kw.KEYWORDS.values() for p in ps)

    assert not re.search(r"routine|minor|administrative", text, re.I)


def test_a_stock_dividend_title_is_claimed_by_the_capital_class_not_only_the_dividend_class():
    assert classify(_news("trả cổ tức bằng cổ phiếu"), "AAA", ALL).tag is Tag.CAPITAL


def test_the_wording_follows_the_named_constants_it_states():
    from app.services.brief import issue_size
    from app.services.brief import wording_company as wc

    assert f"{FIRST_BRIEF_LOOKBACK_DAYS} " in wc.NEEDS_FIRST and f"{FIRST_BRIEF_LOOKBACK_DAYS} " in wc.NEEDS_FIXED
    assert f"{issue_size.ISSUE_MATERIAL_RATIO:.0%}" in wc.SMALL_ISSUES and f"{issue_size.ISSUE_MATERIAL_RATIO:.0%}" in wc.SMALL_ISSUES_UNSTATED
