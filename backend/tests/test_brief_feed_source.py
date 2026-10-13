"""The brief's one feed adapter (`weekly-holdings-brief`: "The brief reads the company feed through one adapter",
"Feed events are typed and unreadable rows are counted", "An issue class is derived inside the adapter")."""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import date, datetime, timezone

import numpy as np
import pytest

from app.db import company_feed_log
from app.services.brief import feed_source
from app.services.brief.feed_source import Event, IssueClass, read_events, snapshot_command

from .brief_event_rows import (
    BONUS, EMPLOYEE, PLACEMENT, RIGHTS, STOCK_DIV, div_row, iss_row, load_feed, record_status, sab_rows,
    vpb_rows,
)
from .company_feed_helpers import events_row
from .test_brief_support import brief_isolation  # noqa: F401


def _only(rows, ticker="SAB"):
    load_feed({ticker: rows})
    return read_events(ticker)


# --- typed events -------------------------------------------------------------------------------------

def test_events_are_typed_with_mixed_date_forms():
    row = div_row("SAB", 0, published="2026-05-08T00:00:00", ex="2026-07-28", vnd=3000.0, record="2026-07-29", payout="2026-08-28T00:00:00")

    snapshot = _only([row])

    assert snapshot.events == (Event(
        event_code="DIV", exright_date=date(2026, 7, 28), record_date=date(2026, 7, 29), payout_date=date(2026, 8, 28),
        value_per_share=3000.0, exercise_ratio=None, published_at=date(2026, 5, 8), issue_class=None,
    ),)
    assert snapshot.unreadable == 0


def test_a_row_with_an_unparseable_date_counts_as_unreadable_and_keeps_none():
    snapshot = _only([div_row("SAB", 0, published="2026-05-08", ex="soon", vnd=3000.0)])

    assert snapshot.events[0].exright_date is None
    assert snapshot.unreadable == 1


def test_a_row_without_an_event_code_is_counted_and_dropped():
    snapshot = _only([events_row(ticker="SAB", event_code=np.nan, event_title_vi="placeholder x", public_date="2026-05-08")])

    assert snapshot.events == () and snapshot.unreadable == 1


def test_an_event_holds_no_stored_title_or_other_string_but_the_codes():
    snapshot = _only([iss_row("SAB", BONUS, 1, published="2023-08-01", ex="2023-09-14", ratio=1.0)])
    event = snapshot.events[0]

    strings = [v for v in dataclasses.asdict(event).values() if isinstance(v, str)]
    assert strings == ["ISS"]  # the event code is the only string
    assert event.issue_class is IssueClass.BONUS and not isinstance(event.issue_class, str)
    assert not any(isinstance(v, str) and "thưởng" in v for v in vars(event).values())


# --- issue classes ------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("keyword", "expected"),
    [(BONUS, "BONUS"), (STOCK_DIV, "STOCK_DIVIDEND"), (RIGHTS, "RIGHTS_OFFER"), (PLACEMENT, "PRIVATE_PLACEMENT"), (EMPLOYEE, "EMPLOYEE")],
)
def test_each_stored_wording_maps_to_its_class(keyword, expected):
    snapshot = _only([iss_row("SAB", keyword, 1, published="2025-01-01", ex="2025-02-01", ratio=0.1)])

    assert snapshot.events[0].issue_class.name == expected


def test_the_wordings_of_the_spec_map_to_the_six_classes():
    titles = {
        "Cổ phiếu thưởng tỉ lệ 15.0%": "BONUS", "Trả Cổ tức bằng Cổ phiếu tỉ lệ 26.0%": "STOCK_DIVIDEND",
        "Quyền mua CP cho Cổ đông hiện hữu tỉ lệ 20.0%": "RIGHTS_OFFER", "Phát hành riêng lẻ tỉ lệ 32.6%": "PRIVATE_PLACEMENT",
        "Phát hành cho CBCNV tỉ lệ 0.5%": "EMPLOYEE", "Điều chỉnh khác": "OTHER",
    }
    rows = [
        events_row(ticker="SAB", event_code="ISS", event_title_vi=title, public_date=f"2025-01-{n + 1:02d}", exercise_ratio=0.1)
        for n, title in enumerate(titles)
    ]

    snapshot = _only(rows)

    assert sorted(e.issue_class.name for e in snapshot.events) == sorted(titles.values())


def test_a_title_with_two_keywords_takes_the_first_in_the_stated_order():
    row = events_row(ticker="SAB", event_code="ISS", event_title_vi=f"Phát hành {PLACEMENT} cho {EMPLOYEE}", public_date="2025-01-01", exercise_ratio=0.1)

    assert _only([row]).events[0].issue_class is IssueClass.PRIVATE_PLACEMENT


def test_a_title_is_matched_after_unicode_normalisation_and_casefold():
    import unicodedata

    row = events_row(
        ticker="SAB", event_code="ISS", event_title_vi=unicodedata.normalize("NFD", "CỔ PHIẾU  THƯỞNG 10%"),
        public_date="2025-01-01", exercise_ratio=0.1,
    )

    assert _only([row]).events[0].issue_class is IssueClass.BONUS


def test_an_issue_without_a_title_is_other_and_a_non_issue_has_no_class():
    row = events_row(ticker="SAB", event_code="ISS", event_title_vi=np.nan, public_date="2025-01-01", exercise_ratio=0.1)

    snapshot = _only([row, div_row("SAB", 1, published="2025-02-01", ex="2025-03-01", vnd=1000.0)])

    by_code = {e.event_code: e for e in snapshot.events}
    assert by_code["ISS"].issue_class is IssueClass.OTHER and by_code["DIV"].issue_class is None


def test_the_enumeration_names_are_exactly_the_six_later_changes_reuse():
    assert [c.name for c in IssueClass] == ["BONUS", "STOCK_DIVIDEND", "RIGHTS_OFFER", "PRIVATE_PLACEMENT", "EMPLOYEE", "OTHER"]


# --- the oldest date, and the feed states -------------------------------------------------------------

def test_the_oldest_published_date_is_taken_across_all_codes():
    assert _only(sab_rows()).oldest_event_date == date(2017, 5, 15)
    vpb = _only(vpb_rows(), "VPB")
    assert vpb.oldest_event_date == date(2022, 7, 19)  # an issue, older than the oldest dividend (2023-10-20)


def test_a_missing_log_reads_as_never_fetched():
    assert not company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists()

    snapshot = read_events("SAB")

    assert snapshot.status == "never_fetched" and snapshot.events == () and snapshot.oldest_event_date is None
    assert not company_feed_log.COMPANY_FEED_LOG_DB_PATH.exists()  # reading creates nothing


def test_a_log_without_the_ticker_reads_as_never_fetched():
    load_feed({"SAB": sab_rows()})

    assert read_events("ZZZ").status == "never_fetched"


def test_only_failed_fetches_read_as_never_succeeded():
    record_status("SAB", "rate_limited")

    snapshot = read_events("SAB")

    assert snapshot.status == "never_succeeded" and snapshot.last_success_at is None and snapshot.latest_attempt_failed


def test_a_fetched_ticker_carries_the_time_and_a_failed_latest_attempt():
    load_feed({"SAB": sab_rows()}, fetched_at=datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc))
    record_status("SAB", "rate_limited", fetched_at=datetime(2026, 10, 11, 8, 0, tzinfo=timezone.utc))

    snapshot = read_events("SAB")

    assert snapshot.status == "fetched" and snapshot.latest_attempt_failed
    assert snapshot.last_success_at == datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc)
    assert snapshot.latest_attempt_at == datetime(2026, 10, 11, 8, 0, tzinfo=timezone.utc)


def test_an_empty_fetch_is_a_successful_fetch_with_no_events():
    record_status("SAB", "empty")

    snapshot = read_events("SAB")

    assert snapshot.status == "fetched" and snapshot.events == () and not snapshot.latest_attempt_failed


def test_the_log_is_not_modified_by_a_read():
    load_feed({"SAB": sab_rows()})
    path = company_feed_log.COMPANY_FEED_LOG_DB_PATH
    before = hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns

    read_events("SAB")
    read_events("ZZZ")

    assert (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) == before


def test_a_read_that_raises_reads_as_unreadable_not_as_never_fetched(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(feed_source.store, "last_fetch", boom)

    assert read_events("SAB").status == "unreadable"


# --- malformed rows ----------------------------------------------------------------------------------------

def _raw_item(fields, *, title="placeholder", published="2026-05-08"):
    from app.services.company_feed.store import StoredItem

    return StoredItem("SAB", "vci", "events", "i", "h", published, title, fields, "t", "t", False)


def test_a_malformed_row_is_counted_and_the_good_rows_survive(monkeypatch):
    good = _raw_item({"event_code": "DIV", "exright_date": "2026-07-28", "value_per_share": 3000.0}, title="a")
    bad = [
        _raw_item({"event_code": "DIV", "value_per_share": 10**400}), _raw_item(["not", "a", "dict"]), _raw_item(None),
        _raw_item({"event_code": "DIV", "value_per_share": 1e300}), _raw_item({"event_code": "ISS", "exercise_ratio": 1e9}),
        _raw_item({"event_code": "DIV", "exright_date": "9999-12-31"}), _raw_item({"event_code": "DIV"}, published="9999-12-31"),
    ]
    monkeypatch.setattr(feed_source.store, "latest_items", lambda *a, **k: [good, *bad])
    load_feed({"SAB": sab_rows()[:1]})  # a successful fetch row, so the status is "fetched"

    snapshot = read_events("SAB")

    assert snapshot.status == "fetched" and snapshot.events[0].value_per_share == 3000.0
    assert snapshot.unreadable >= 6 and all(e.exercise_ratio is None or e.exercise_ratio <= 10 for e in snapshot.events)
    assert snapshot.oldest_event_date == date(2026, 5, 8)  # the far-future date was refused, not used


def test_an_unparsable_fetch_time_reads_as_unreadable(monkeypatch):
    load_feed({"SAB": sab_rows()[:1]})
    real = feed_source.store.last_fetch
    monkeypatch.setattr(feed_source.store, "last_fetch", lambda *a, **k: dataclasses.replace(real(*a, **k), last_success_at="not a time"))

    assert read_events("SAB").status == "unreadable"


# --- the snapshot command ------------------------------------------------------------------------------

def test_the_snapshot_command_text():
    assert snapshot_command(["SAB"]) == "python backend/scripts/snapshot_company_feed.py --tickers SAB"
    assert snapshot_command(["SAB", "VPB"]).endswith("--tickers SAB,VPB")
    assert snapshot_command(["A; rm x"]).endswith("--tickers 'A; rm x'")  # a copy-pasted command never runs a second one


def test_the_adapter_imports_only_the_store_module_of_the_feed():
    import ast

    tree = ast.parse(open(feed_source.__file__, encoding="utf-8").read())
    imported = [
        (node.module or "", [a.name for a in node.names]) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ] + [(a.name, []) for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names]
    feed_imports = [(m, n) for m, n in imported if "company_feed" in m]

    assert feed_imports == [("app.services.company_feed", ["store"])]
