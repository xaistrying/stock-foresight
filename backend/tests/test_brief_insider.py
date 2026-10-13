"""The trade record: title parser, direction cross-check, window state (`add-announcement-tags-and-insider-sizing`,
"An insider or major-shareholder trade line states what the record says, and where its window stands")."""

from __future__ import annotations

import unicodedata

import pytest

from app.services.brief.insider import TRADE_TITLE, WindowStatus, parse_trade, window_is_open, window_status

from .brief_announcement_rows import d, make_announcement, make_trade_item
from .test_brief_support import brief_isolation  # noqa: F401

AS_OF = d("2026-10-09")


def test_a_sell_title_with_a_quantity_is_read():
    trade = parse_trade(make_trade_item("AAA", name="Fictional Capital Ltd", qty="30,000,000"), "AAA", AS_OF)

    assert (trade.name, trade.direction, trade.quantity) == ("Fictional Capital Ltd", "sale", 30_000_000)


def test_a_buy_title_reads_as_a_purchase():
    trade = parse_trade(make_trade_item("AAA", act="Buy", qty="500"), "AAA", AS_OF)

    assert (trade.direction, trade.quantity) == ("purchase", 500)


def test_a_title_without_a_quantity_has_a_direction_and_no_quantity():
    trade = parse_trade(make_trade_item("AAA", qty=None), "AAA", AS_OF)

    assert trade.direction == "sale" and trade.quantity is None and trade.name == "Fictional Capital Ltd"


@pytest.mark.parametrize("qty", ["0", "99999999999999"])
def test_a_zero_or_absurd_quantity_is_not_read(qty):
    assert parse_trade(make_trade_item("AAA", qty=qty), "AAA", AS_OF).quantity is None


def test_the_direction_from_the_action_field_must_agree_with_the_title():
    trade = parse_trade(make_trade_item("AAA", act="Buy", action="Sell"), "AAA", AS_OF)  # title Mua, field Sell

    assert trade.direction is None and trade.quantity is None


def test_an_unknown_or_missing_action_field_is_not_trusted():
    assert parse_trade(make_trade_item("AAA", action=None), "AAA", AS_OF).direction is None
    assert parse_trade(make_trade_item("AAA", action="Transfer"), "AAA", AS_OF).direction is None


def test_a_title_for_another_ticker_is_not_read():
    trade = parse_trade(make_trade_item("BBB"), "AAA", AS_OF)

    assert trade.direction is None and trade.quantity is None


def test_a_title_in_another_shape_is_not_read():
    trade = parse_trade(make_announcement("events", "just some words", event_code="DDIND", action_type_en="Sell"), "AAA", AS_OF)

    assert trade.name is None and trade.direction is None


def test_the_alternate_spelling_of_the_word_is_accepted():
    assert TRADE_TITLE.match("Name - Đăng ký Bán 10 AAA")


def test_a_decomposed_title_is_read():
    title = unicodedata.normalize("NFD", "Name - Đăng kí Bán 10 AAA")

    assert parse_trade(make_trade_item("AAA", title=title), "AAA", AS_OF).quantity == 10


def test_the_name_is_everything_before_the_last_marker():
    trade = parse_trade(make_trade_item("AAA", title="A - B - Đăng kí Bán 5 AAA"), "AAA", AS_OF)

    assert trade.name == "A - B"


# --- the window --------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("start", "end", "status"),
    [
        ("2026-10-12", "2026-11-10", WindowStatus.NOT_STARTED),
        ("2026-10-09", "2026-10-20", WindowStatus.UNDER_WAY),  # starts on the last bar
        ("2026-10-01", "2026-10-09", WindowStatus.UNDER_WAY),  # ends on the last bar
        ("2026-09-01", "2026-10-08", WindowStatus.ENDED),
        (None, "2026-10-08", WindowStatus.UNKNOWN),
        ("2026-10-01", None, WindowStatus.UNKNOWN),
    ],
)
def test_window_states_on_every_case(start, end, status):
    assert window_status(d(start) if start else None, d(end) if end else None, AS_OF) is status


def test_a_record_published_after_its_window_ended_is_ended_not_planned():
    trade = parse_trade(make_trade_item("AAA", published="2026-10-08", start="2026-08-01", end="2026-09-01"), "AAA", AS_OF)

    assert trade.status is WindowStatus.ENDED and trade.item.published_at > trade.end


def test_the_window_length_in_weeks_is_rounded_up_and_counts_both_ends():
    assert parse_trade(make_trade_item("AAA", start="2026-10-12", end="2026-10-23"), "AAA", AS_OF).weeks == 2  # 12 days
    assert parse_trade(make_trade_item("AAA", start="2026-10-12", end="2026-10-18"), "AAA", AS_OF).weeks == 1  # 7 days
    assert parse_trade(make_trade_item("AAA", start="2026-10-12", end="2026-10-19"), "AAA", AS_OF).weeks == 2  # 8 days
    assert parse_trade(make_trade_item("AAA", start=None), "AAA", AS_OF).weeks is None


def test_a_window_extends_past_the_brief_only_beyond_seven_calendar_days():
    near = parse_trade(make_trade_item("AAA", end="2026-10-16"), "AAA", AS_OF)
    far = parse_trade(make_trade_item("AAA", end="2026-10-17"), "AAA", AS_OF)

    assert not near.extends_past(AS_OF) and far.extends_past(AS_OF)


def test_an_open_window_is_not_started_or_under_way_and_a_missing_date_is_not_open():
    assert window_is_open(make_trade_item("AAA"), AS_OF)
    assert not window_is_open(make_trade_item("AAA", start="2026-09-01", end="2026-10-01"), AS_OF)
    assert not window_is_open(make_trade_item("AAA", start=None), AS_OF)


def test_the_event_code_class_is_not_read():
    for code in ("DDIND", "DDINS", "DDRP"):
        assert parse_trade(make_trade_item("AAA", code=code), "AAA", AS_OF).direction == "sale"
