"""Gathering the announcement facts for one ticker (`add-announcement-tags-and-insider-sizing`): the previous brief's last bar
from the issued log, the lazy share-count policy, and the fences. The adapter read and the vendor fetch are injected."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.services.brief.company_facts import MODE_NOT_NEEDED, gather_company_facts, previous_last_bar
from app.services.brief.feed_source import AnnouncementRead
from app.services.brief.share_cache import ShareCache, ShareCount
from app.services.brief.sizing import MODE_DISAGREE, MODE_OFF, MODE_OK, MODE_UNAVAILABLE

from .brief_announcement_rows import d, health, make_trade_item
from .test_brief_support import brief_isolation, make_facts, make_issued_entry, make_log  # noqa: F401

NOW = datetime(2026, 10, 12, 5, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Reading:
    count: int = 1_000_000_000
    year_report: int = 2026
    quarter: int = 2


def _read(*items):
    return lambda ticker: AnnouncementRead(tuple(items), health(), health())


def _gather(items, *, sizing=True, cache=None, fetch=None, log=None):
    return gather_company_facts(
        "AAA", make_facts("AAA"), log or make_log(), NOW, sizing=sizing, cache=cache, fetch_fn=fetch, read_fn=_read(*items),
    )


def test_the_previous_last_bar_is_the_latest_earlier_bar_for_the_ticker():
    log = make_log(make_issued_entry("AAA", as_of="2026-09-25"), make_issued_entry("AAA", as_of="2026-10-02"), make_issued_entry("BBB", as_of="2026-10-08"))

    assert previous_last_bar(log, "AAA", "2026-10-09") == d("2026-10-02")
    assert previous_last_bar(log, "CCC", "2026-10-09") is None


def test_an_entry_for_the_last_bar_itself_is_ignored_so_a_rerun_reads_what_an_earlier_week_said():
    log = make_log(make_issued_entry("AAA", as_of="2026-10-02"), make_issued_entry("AAA", as_of="2026-10-09"))

    assert previous_last_bar(log, "AAA", "2026-10-09") == d("2026-10-02")


def test_the_run_date_is_the_vietnam_date():
    late_utc = datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)  # 03:00 on the 12th in Vietnam

    facts = gather_company_facts("AAA", make_facts("AAA"), make_log(), late_utc, sizing=False, read_fn=_read())

    assert facts.run_date == d("2026-10-12")


def test_sizing_off_never_calls_the_fetch_function():
    calls = []

    facts = _gather([make_trade_item("AAA")], sizing=False, fetch=lambda t: calls.append(t))

    assert facts.sizing.mode == MODE_OFF and calls == []


def test_no_trade_with_a_stated_quantity_means_the_vendor_is_not_asked():
    calls = []

    facts = _gather([make_trade_item("AAA", qty=None)], fetch=lambda t: calls.append(t))

    assert facts.sizing.mode == MODE_NOT_NEEDED and calls == []


def test_an_old_trade_that_is_not_listed_does_not_trigger_a_fetch():
    calls = []
    old = make_trade_item("AAA", published="2026-08-01", start="2026-08-02", end="2026-08-30")

    _gather([old], fetch=lambda t: calls.append(t), log=make_log(make_issued_entry("AAA", as_of="2026-10-02")))

    assert calls == []


def test_a_fetch_is_cached_with_the_run_time(tmp_path):
    cache = ShareCache(_dir(tmp_path))

    facts = _gather([make_trade_item("AAA")], cache=cache, fetch=lambda t: Reading())

    assert facts.sizing.mode == MODE_OK and facts.sizing.count.fetched_at == NOW and cache.get("AAA").count == 1_000_000_000


def test_a_failure_with_nothing_cached_is_unavailable_and_a_disagreement_is_marked():
    def broken(ticker):
        raise RuntimeError("x")

    class Disagree(Exception):
        disagree = True

    def disagree(ticker):
        raise Disagree()

    assert _gather([make_trade_item("AAA")], fetch=broken).sizing.mode == MODE_UNAVAILABLE
    assert _gather([make_trade_item("AAA")], fetch=disagree).sizing.mode == MODE_DISAGREE
    assert _gather([make_trade_item("AAA")], fetch=None).sizing.mode == MODE_UNAVAILABLE


def test_any_system_exit_inside_the_fetch_is_an_unavailable_count_and_a_keyboard_interrupt_is_not():
    def exits(ticker):
        raise SystemExit(3)

    def interrupted(ticker):
        raise KeyboardInterrupt()

    assert _gather([make_trade_item("AAA")], fetch=exits).sizing.mode == MODE_UNAVAILABLE
    with pytest.raises(KeyboardInterrupt):
        _gather([make_trade_item("AAA")], fetch=interrupted)


def test_a_disagreement_is_never_cached(tmp_path):
    cache = ShareCache(_dir(tmp_path))

    class Disagree(Exception):
        disagree = True

    def disagree(ticker):
        raise Disagree()

    _gather([make_trade_item("AAA")], cache=cache, fetch=disagree)

    assert cache.get("AAA") is None and not cache.path.exists()


def test_a_fresh_cache_hit_skips_the_fetch(tmp_path):
    cache = ShareCache(_dir(tmp_path))
    cache.put("AAA", ShareCount(5, 2026, 2, NOW.replace(day=9)))
    calls = []

    facts = _gather([make_trade_item("AAA")], cache=cache, fetch=lambda t: calls.append(t))

    assert calls == [] and facts.sizing.count.count == 5


def test_the_checked_property_means_at_least_one_kind_was_fetched_successfully():
    from app.services.brief.company_facts import CompanyFacts
    from app.services.brief.sizing import SizingInput

    def facts(news, events):
        return CompanyFacts(AnnouncementRead((), health(news), health(events)), d("2026-10-12"), None, SizingInput(MODE_OFF))

    assert facts("fetched", "never_fetched").checked and facts("never_fetched", "fetched").checked
    assert not facts("never_fetched", "never_succeeded").checked and not facts("unreadable", "unreadable").checked


def _dir(tmp_path):
    directory = tmp_path / "cfg"
    directory.mkdir(mode=0o700, exist_ok=True)
    return directory / "holdings_share_counts.json"


# --- review fixes (2026-10-12) ------------------------------------------------------------------------------------------

def test_a_disagreement_is_not_masked_by_an_older_cached_value(tmp_path):
    cache = ShareCache(_dir(tmp_path))
    cache.put("AAA", ShareCount(5, 2026, 1, NOW.replace(day=1)))  # stale: 11 days old

    class Disagree(Exception):
        disagree = True

    def disagree(ticker):
        raise Disagree()

    facts = _gather([make_trade_item("AAA")], cache=cache, fetch=disagree)

    assert facts.sizing.mode == MODE_DISAGREE and facts.sizing.count is None


def test_an_ordinary_failure_still_falls_back_to_the_stale_cached_value_with_its_date(tmp_path):
    cache = ShareCache(_dir(tmp_path))
    cache.put("AAA", ShareCount(5, 2026, 1, NOW.replace(day=1)))

    def broken(ticker):
        raise RuntimeError("x")

    facts = _gather([make_trade_item("AAA")], cache=cache, fetch=broken)

    assert facts.sizing.mode == MODE_OK and facts.sizing.count.fetched_at == NOW.replace(day=1)


def test_a_cached_value_stamped_in_the_future_is_never_used_even_as_a_fallback(tmp_path):
    cache = ShareCache(_dir(tmp_path))
    cache.put("AAA", ShareCount(5, 2026, 1, datetime(2999, 1, 1, tzinfo=timezone.utc)))

    def broken(ticker):
        raise RuntimeError("x")

    assert _gather([make_trade_item("AAA")], cache=cache, fetch=broken).sizing.mode == MODE_UNAVAILABLE
    assert _gather([make_trade_item("AAA")], cache=cache, fetch=None).sizing.mode == MODE_UNAVAILABLE


def test_a_log_entry_with_an_impossible_date_is_skipped_not_fatal():
    log = make_log(make_issued_entry("AAA", as_of="2026-13-45"), make_issued_entry("AAA", as_of="2026-10-02"))

    assert previous_last_bar(log, "AAA", "2026-10-09") == d("2026-10-02")
    assert previous_last_bar(make_log(make_issued_entry("AAA", as_of="2026-13-45")), "AAA", "2026-10-09") is None


# --- review fix (2026-10-12): the redacted copy must size what it lists ---------------------------------------------------

def _old_trade():
    """Published 2026-09-26 with an ended window: inside the 14-day lookback of the redacted copy, but not new after an earlier
    brief on 2026-10-05 and not open, so only the lookback lists it."""
    return make_trade_item("AAA", published="2026-09-26", start="2026-09-01", end="2026-09-30")


def test_the_share_count_is_resolved_when_only_the_redacted_lookback_lists_a_trade_with_a_quantity():
    calls = []

    def fetch(ticker):
        calls.append(ticker)
        return Reading()

    log = make_log(make_issued_entry("AAA", as_of="2026-10-05"))

    facts = _gather([_old_trade()], fetch=fetch, log=log)

    assert calls == ["AAA"] and facts.sizing.mode == MODE_OK


def test_the_redacted_size_line_is_the_same_with_and_without_an_earlier_brief():
    from app.services.brief.compose import TickerReport, build_brief
    from .test_brief_support import ict, make_holding

    def redacted(log):
        facts = make_facts("AAA")
        company = gather_company_facts("AAA", facts, log, NOW, sizing=True, fetch_fn=lambda t: Reading(), read_fn=_read(_old_trade()))
        import dataclasses
        lines = build_brief((TickerReport(make_holding("AAA"), dataclasses.replace(facts, company=company)),), redact=True, now=ict("2026-10-09 16:30"))
        return [l for l in lines if l.lstrip().startswith("Size:")]

    first_brief = redacted(make_log())
    later_brief = redacted(make_log(make_issued_entry("AAA", as_of="2026-10-05")))

    assert first_brief == later_brief and first_brief and "could not be read" not in first_brief[0]


# --- review fix (2026-10-12): after the first failure the run makes no further vendor call -------------------------------------

def test_after_the_first_failure_no_further_share_count_call_is_made_in_the_run():
    from app.services.brief.company_facts import stop_after_failure

    calls = []

    def flaky(ticker):
        calls.append(ticker)
        raise RuntimeError("limiter")

    guarded = stop_after_failure(flaky)

    assert _gather([make_trade_item("AAA")], fetch=guarded).sizing.mode == MODE_UNAVAILABLE
    assert _gather([make_trade_item("AAA")], fetch=guarded).sizing.mode == MODE_UNAVAILABLE
    assert calls == ["AAA"]  # the second ticker never reached the vendor


def test_a_success_keeps_the_gate_open_and_a_disagreement_does_not_close_it():
    from app.services.brief.company_facts import stop_after_failure

    class Disagree(Exception):
        disagree = True

    outcomes = [Disagree(), Reading(), RuntimeError("x"), Reading()]
    calls = []

    def scripted(ticker):
        calls.append(ticker)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    guarded = stop_after_failure(scripted)
    modes = [_gather([make_trade_item("AAA")], fetch=guarded).sizing.mode for _ in range(4)]

    assert modes == [MODE_DISAGREE, MODE_OK, MODE_UNAVAILABLE, MODE_UNAVAILABLE] and len(calls) == 3


def test_a_stop_gate_also_stops_after_a_system_exit():
    from app.services.brief.company_facts import stop_after_failure

    calls = []

    def exits(ticker):
        calls.append(ticker)
        raise SystemExit(1)

    guarded = stop_after_failure(exits)
    _gather([make_trade_item("AAA")], fetch=guarded)
    _gather([make_trade_item("AAA")], fetch=guarded)

    assert calls == ["AAA"]


def test_a_future_stamped_cache_entry_is_reported_not_silently_ignored(tmp_path):
    cache = ShareCache(_dir(tmp_path))
    cache.put("AAA", ShareCount(5, 2026, 1, datetime(2999, 1, 1, tzinfo=timezone.utc)))

    _gather([make_trade_item("AAA")], cache=cache, fetch=None)

    assert any("stamped in the future" in note for note in cache.notes)
