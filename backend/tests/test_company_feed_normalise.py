"""Cleaning, identity and hashing of company feed items (`company-feed`: stored text is cleaned,
bounded and in its original language; items are keyed for de-duplication).

Pure pandas tests: no vendor library, no database, no network.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.services.company_feed import normalise
from app.services.company_feed.normalise import UnexpectedFrame, frame_to_records, rss_items_to_records
from app.services.debate import news_feeds

from .company_feed_helpers import events_frame, events_row, news_frame, news_row


def _news(**overrides):
    return frame_to_records(news_frame(news_row(**overrides)), kind="news", ticker="SAB", source="vci")


def _event(**overrides):
    return frame_to_records(events_frame(events_row(**overrides)), kind="events", ticker="SAB", source="vci")


def _one(result):
    assert len(result.records) == 1
    return result.records[0]


# --- 4.2: cleaning -----------------------------------------------------------------------------


def test_cleaning_is_the_news_feeds_function_so_a_rename_there_fails_here():
    assert normalise.clean_text is news_feeds._clean


def test_markup_entities_and_invisible_characters_are_removed_with_diacritics_intact():
    """Scenario: Markup and invisible characters are removed."""
    record = _one(_news(news_title="<b>SAB:</b> Th​ông báo &amp; kết quả‮\U000e0041"))

    assert record.title == "SAB: Thông báo & kết quả"
    assert not any(unicodedata.category(c)[0] == "C" for c in record.title)


def test_double_escaped_markup_does_not_come_back_as_markup():
    record = _one(_news(news_title="Tin &lt;script&gt;alert(1)&lt;/script&gt; mới"))

    assert "<" not in record.title and ">" not in record.title


def test_composed_and_decomposed_forms_store_the_same_text_and_item_id():
    """Scenario: Composed and decomposed forms agree."""
    composed = unicodedata.normalize("NFC", "Thông báo kết quả kinh doanh")
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed

    first, second = _one(_news(news_title=composed)), _one(_news(news_title=decomposed))

    assert first.title == second.title == composed
    assert first.item_id == second.item_id
    assert first.content_hash == second.content_hash


def test_titles_are_capped_at_500_and_other_strings_at_200():
    """Scenario: Oversized text is bounded."""
    long_text = "Đ" * 5000
    news = _one(_news(news_title=long_text))
    event = _one(_event(event_title_vi=long_text, category=long_text))

    assert normalise.COMPANY_TITLE_MAX == 500 and normalise.COMPANY_FIELD_MAX == 200
    assert len(news.title) == 500
    assert len(event.title) == 500
    assert len(json.loads(event.fields_json)["category"]) == 200


def test_the_language_is_not_changed_and_the_english_variant_is_not_the_title():
    """Scenario: The language is not changed."""
    record = _one(_event(event_title_vi="Họp ĐHĐCĐ thường niên 2026", event_title_en="Annual meeting 2026"))

    assert record.title == "Họp ĐHĐCĐ thường niên 2026"
    assert "Annual meeting" not in record.fields_json


def test_a_body_column_is_dropped_and_reported():
    """Scenario: A body column is dropped."""
    body = "Nội dung đầy đủ của bản tin rất dài " * 20
    result = _news(news_full_content=body, news_short_content="Tóm tắt")

    record = _one(result)
    assert sorted(result.body_columns_filled) == ["news_full_content", "news_short_content"]
    assert "Nội dung đầy đủ" not in record.fields_json + (record.title or "")
    assert "Tóm tắt" not in record.fields_json + (record.title or "")


def test_an_empty_body_column_is_not_reported():
    assert _news(news_full_content="", news_short_content=None).body_columns_filled == ()


def test_non_scalar_cells_are_skipped_and_counted():
    result = _event(category=["DIVIDEND", "OTHER"], action_type_vi={"a": 1})

    fields = json.loads(_one(result).fields_json)
    assert result.skipped_cells == 2
    assert "category" not in fields and "action_type_vi" not in fields
    assert fields["event_code"] == "DIV"


def test_missing_values_and_numpy_scalars_become_plain_json_values():
    """Scenario: Events with missing values store valid JSON."""
    rows = [
        events_row(exright_date=np.nan, payout_date=pd.NaT, value_per_share=np.float64(3000.0), exercise_ratio=np.float64("inf")),
        events_row(event_title_vi="Khác", exright_date=None, value_per_share=np.nan, issue_date=pd.Timestamp("2026-04-23")),
    ]
    result = frame_to_records(events_frame(*rows), kind="events", ticker="SAB", source="vci")

    for record in result.records:
        strict = json.loads(record.fields_json, parse_constant=lambda name: pytest.fail(f"non-JSON constant {name}"))
        assert strict["exright_date"] is None
        assert json.dumps(strict, allow_nan=False)
    first, second = (json.loads(r.fields_json) for r in result.records)
    assert first["payout_date"] is None
    assert first["value_per_share"] == 3000.0 and type(first["value_per_share"]) is float
    assert first["exercise_ratio"] is None
    assert second["issue_date"] == "2026-04-23T00:00:00"


def test_a_whole_number_hashes_the_same_whether_pandas_made_it_an_int_or_a_float():
    """pandas makes a column int64 when no row is null and float64 when one is: the same event
    must not look revised (a new version, a false `possible gap`) when only that changes."""
    whole_frame = events_frame(events_row(value_per_share=3000, exercise_ratio=1))
    assert whole_frame["value_per_share"].dtype.kind == "i"
    with_null = events_frame(
        events_row(value_per_share=3000, exercise_ratio=1),
        events_row(event_title_vi="Khác", value_per_share=np.nan, exercise_ratio=np.nan),
    )
    assert with_null["value_per_share"].dtype.kind == "f"

    whole = frame_to_records(whole_frame, kind="events", ticker="SAB", source="vci").records[0]
    mixed = frame_to_records(with_null, kind="events", ticker="SAB", source="vci").records[0]

    assert whole.content_hash == mixed.content_hash and whole.fields_json == mixed.fields_json


def test_a_blank_string_and_a_null_store_the_same_value():
    blank, null = _event(action_type_vi=""), _event(action_type_vi=None)

    assert _one(blank).content_hash == _one(null).content_hash


def test_news_rows_are_stored_under_the_requested_ticker_not_the_frames_empty_one():
    record = _one(_news())

    assert (record.kind, record.ticker, record.source) == ("news", "SAB", "vci")


def test_dates_keep_the_vendors_value_without_timezone_shifting():
    news, event = _one(_news(public_date="2026-08-28T17:39:58")), _one(_event(public_date="2026-05-08T00:00:00"))

    assert news.published_at == "2026-08-28T17:39:58"
    assert event.published_at == "2026-05-08T00:00:00"
    assert _one(_news(public_date="2026-08-28 17:39:58")).published_at == "2026-08-28T17:39:58"
    assert _one(_news(public_date="2026-08-28")).published_at == "2026-08-28"


def test_an_unparseable_date_is_stored_as_given_not_dropped():
    assert _one(_news(public_date="28/08/2026")).published_at == "28/08/2026"


def test_the_events_title_is_the_vietnamese_one_and_the_news_title_is_news_title():
    assert _one(_event()).title == "Trả cổ tức bằng tiền mặt - Đợt 2 2025 - 3,000 VND"
    assert _one(_news()).title == "SAB: Giải trình BCTC bán niên soát xét năm 2026"


def test_repeated_rows_in_one_frame_give_one_record():
    frame = pd.concat([news_frame(news_row()), news_frame(news_row())], ignore_index=True)

    assert len(frame_to_records(frame, kind="news", ticker="SAB", source="vci").records) == 1


# --- 4.3: identity, versions, required columns -------------------------------------------------


def test_item_id_is_stable_and_short_and_the_hash_is_a_sha256():
    first, second = _one(_event()), _one(_event())

    assert first.item_id == second.item_id and len(first.item_id) == 16
    assert first.content_hash == second.content_hash and len(first.content_hash) == 64
    assert int(first.item_id, 16) >= 0 and int(first.content_hash, 16) >= 0


def test_a_revisable_field_changes_the_hash_but_not_the_item_id():
    """Scenario: A revised item becomes a new version (identity half)."""
    before = _one(_event(payout_date=np.nan))
    after = _one(_event(payout_date="2026-08-28T00:00:00"))

    assert before.item_id == after.item_id
    assert before.content_hash != after.content_hash


@pytest.mark.parametrize("column, value", [
    ("event_code", "ISS"), ("category", "OTHER"), ("display_date1", "2026-07-30T00:00:00"),
    ("display_date2", "2026-05-09T00:00:00"), ("record_date", "2026-07-30"), ("exright_date", "2026-07-29"),
    ("payout_date", "2026-09-01T00:00:00"), ("issue_date", "2026-04-23"), ("listing_date", "2026-05-01"),
    ("start_date", "2026-01-01"), ("end_date", "2026-02-01"), ("value_per_share", 3500.0),
    ("exercise_ratio", 0.35), ("action_type_vi", "Tiền mặt"), ("action_type_en", "Cash"),
    ("event_title_vi", "Tiêu đề khác"), ("public_date", "2026-05-09T00:00:00"),
])
def test_content_hash_changes_with_every_stored_events_field(column, value):
    assert _one(_event()).content_hash != _one(_event(**{column: value})).content_hash


@pytest.mark.parametrize("column, value", [
    ("news_title", "Tiêu đề khác"), ("public_date", "2026-08-29T10:00:00"),
    ("news_source", "CafeF"), ("news_source_link", "https://example.invalid/a"), ("news_author", "Ban biên tập"),
])
def test_content_hash_changes_with_every_stored_news_field(column, value):
    assert _one(_news()).content_hash != _one(_news(**{column: value})).content_hash


def test_item_id_follows_the_identity_fields_only():
    base = _one(_event())

    assert _one(_event(event_code="ISS")).item_id != base.item_id
    assert _one(_event(event_title_vi="Khác")).item_id != base.item_id
    assert _one(_event(public_date="2026-05-09T00:00:00")).item_id != base.item_id
    assert _one(_event(value_per_share=1.0, exright_date="2026-01-01")).item_id == base.item_id


def test_item_id_differs_by_kind_ticker_and_source():
    one = _one(frame_to_records(news_frame(), kind="news", ticker="SAB", source="vci"))
    other_ticker = _one(frame_to_records(news_frame(), kind="news", ticker="VPB", source="vci"))
    other_source = _one(frame_to_records(news_frame(), kind="news", ticker="SAB", source="kbs"))

    assert len({one.item_id, other_ticker.item_id, other_source.item_id}) == 3


def test_a_changed_rss_snippet_changes_the_hash_but_not_the_item_id():
    """Scenario: The snippet is kept, the identity ignores it (identity half)."""
    published = datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc)
    feed = "https://example.invalid/feed.rss"

    first = rss_items_to_records([(published, "SAB công bố kết quả", "Bản tin ngắn")], source=feed).records[0]
    second = rss_items_to_records([(published, "SAB công bố kết quả", "Bản tin ngắn đã sửa")], source=feed).records[0]

    assert first.item_id == second.item_id
    assert first.content_hash != second.content_hash
    assert json.loads(first.fields_json) == {"snippet": "Bản tin ngắn"}


def test_rss_items_are_stored_without_a_ticker_in_utc_and_deduplicated():
    ict_time = datetime.fromisoformat("2026-10-08T10:00:00+07:00")
    feed = "https://example.invalid/feed.rss"

    records = rss_items_to_records([(ict_time, "Tin A", ""), (ict_time, "Tin A", ""), (ict_time, "Tin B", "mô tả")], source=feed).records

    assert [r.title for r in records] == ["Tin A", "Tin B"]
    assert all((r.kind, r.ticker, r.source) == ("rss", "", feed) for r in records)
    assert records[0].published_at == "2026-10-08T03:00:00+00:00"
    assert json.loads(records[0].fields_json) == {"snippet": None}


@pytest.mark.parametrize("column", ["news_title", "public_date"])
def test_a_news_frame_missing_a_required_column_is_an_unexpected_frame(column):
    """Scenario: A changed frame is an error (news without a title column)."""
    with pytest.raises(UnexpectedFrame, match=column):
        frame_to_records(news_frame().drop(columns=[column]), kind="news", ticker="SAB", source="vci")


@pytest.mark.parametrize("column", ["event_code", "event_title_vi", "public_date"])
def test_an_events_frame_missing_a_required_column_is_an_unexpected_frame(column):
    with pytest.raises(UnexpectedFrame, match=column):
        frame_to_records(events_frame().drop(columns=[column]), kind="events", ticker="SAB", source="vci")


def test_require_columns_accepts_an_empty_frame_with_no_columns():
    normalise.require_columns(pd.DataFrame(), "news")
    normalise.require_columns(pd.DataFrame(), "events")
    assert frame_to_records(pd.DataFrame(), kind="news", ticker="SAB", source="vci").records == ()


def test_an_unknown_kind_is_refused():
    with pytest.raises(ValueError):
        frame_to_records(news_frame(), kind="filings", ticker="SAB", source="vci")


def test_an_optional_column_missing_is_not_an_error():
    frame = events_frame().drop(columns=["action_type_vi", "payout_date"])

    record = _one(frame_to_records(frame, kind="events", ticker="SAB", source="vci"))

    assert "payout_date" not in json.loads(record.fields_json)
