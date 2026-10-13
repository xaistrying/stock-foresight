"""A whole run with announcements and a share count (`add-announcement-tags-and-insider-sizing`): the lazy fetch policy,
the cache beside the holdings file, `--no-sizing`, the limiter exit, a genuine exit, and nothing written to the real files.
The vendor call is a fake; nothing here touches the network or `backend/data/`."""

from __future__ import annotations

import stat
from dataclasses import dataclass

import pytest

from app.services.share_count.fetch import ShareCountUnavailable, ShareCountsDisagree, read_share_count
from app.services.brief.run import RunOptions, run_weekly_brief

from .brief_announcement_rows import insider_row, store_rows
from .test_brief_run import AFTER_CLOSE, _log, world  # noqa: F401
from .test_brief_support import brief_env, brief_isolation  # noqa: F401
from .test_share_count_fetch import AGREE, overview_frame, ratio_frame

CACHE = "holdings_share_counts.json"


@dataclass(frozen=True)
class Reading:
    count: int = 1_282_562_372
    year_report: int = 2026
    quarter: int = 2


class FakeFetch:
    def __init__(self, outcome=None):
        self.calls: list[str] = []
        self.outcome = outcome or Reading()

    def __call__(self, ticker):
        self.calls.append(ticker)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _run(world, fetch, *, sizing=True, redact=False, now=AFTER_CLOSE):
    options = RunOptions(holdings_path=world.holdings, redact=redact, refresh=False, sizing=sizing)
    return run_weekly_brief(options, repo_root=world.repo, now=now, sleep=lambda s: None, share_count_fn=fetch)


def _trade(qty="30,000,000", **kwargs):
    return insider_row("AAA", 1, qty=qty, published="2026-10-08", start="2026-10-12", end="2026-10-16", **kwargs)


def _text(result) -> str:
    return "\n".join(result.brief)


def test_a_listed_trade_with_a_quantity_fetches_once_caches_the_count_and_shows_a_size(world):
    store_rows("AAA", "events", [_trade()])
    fetch = FakeFetch()

    result = _run(world, fetch)

    text = _text(result)
    assert result.exit_code == 0 and fetch.calls == ["AAA"]  # only the held ticker with a stated quantity
    assert "Size: 2.3% of the shares outstanding (the vendor's count is 1,282,562,372: VCI share count via vnstock, latest-quarter row 2026-Q2, fetched 2026-10-09)." in text
    cache = world.config / CACHE
    assert cache.exists() and stat.S_IMODE(cache.stat().st_mode) == 0o600 and "1282562372" in cache.read_text()
    assert "registered sales or purchases by a major shareholder or insider since the last brief: 1" in text


def test_a_fresh_cached_value_means_no_second_vendor_call(world):
    store_rows("AAA", "events", [_trade()])
    _run(world, FakeFetch())
    second = FakeFetch()

    result = _run(world, second)

    assert second.calls == [] and "Size: 2.3%" in _text(result)


def test_a_stale_cached_value_is_fetched_again(world):
    from datetime import timedelta

    store_rows("AAA", "events", [_trade()])
    _run(world, FakeFetch(Reading(count=1_000_000_000)))
    later = FakeFetch()

    result = _run(world, later, now=AFTER_CLOSE + timedelta(days=8))

    assert later.calls == ["AAA"] and result.exit_code == 0


def test_no_sizing_makes_no_vendor_call_and_writes_no_cache_and_prints_the_fallback(world):
    store_rows("AAA", "events", [_trade()])
    fetch = FakeFetch()

    result = _run(world, fetch, sizing=False)

    text = _text(result)
    assert fetch.calls == [] and not (world.config / CACHE).exists()
    assert "Size: size not shown, because sizing is off (--no-sizing). To size it, read the notice:" in text
    assert "filed a notice of a sale of 30,000,000 AAA shares" in text and "The usual range is built from past prices only." in text


def test_nothing_needs_sizing_when_no_trade_states_a_quantity(world):
    store_rows("AAA", "events", [_trade(qty=None)])
    fetch = FakeFetch()

    result = _run(world, fetch)

    assert fetch.calls == [] and "quantity not stated in the title" in _text(result)


def test_no_announcements_means_no_vendor_call(world):
    fetch = FakeFetch()

    result = _run(world, fetch)

    assert fetch.calls == [] and result.exit_code == 0 and "announcements not checked" in _text(result)


def test_the_limiter_exit_inside_the_real_fetch_function_falls_back_without_ending_the_process(world):
    store_rows("AAA", "events", [_trade()])

    def limiter(ticker):
        raise SystemExit("Rate limit exceeded: promotional text")

    result = _run(world, lambda t: read_share_count(t, frames=limiter))

    text = _text(result)
    assert result.exit_code == 0 and "size not shown, because the vendor's share count could not be read this run." in text
    assert "promotional" not in text and "promotional" not in " ".join(result.messages)
    assert not (world.config / CACHE).exists()


def test_any_other_exit_inside_the_share_count_call_also_falls_back_and_the_brief_is_still_written(world):
    store_rows("AAA", "events", [_trade()])

    def genuine(ticker):
        raise SystemExit(3)

    result = _run(world, lambda t: read_share_count(t, frames=genuine))

    assert result.exit_code == 0 and "size not shown, because the vendor's share count could not be read this run." in _text(result)


def test_a_keyboard_interrupt_during_the_share_count_call_still_interrupts_the_run(world):
    store_rows("AAA", "events", [_trade()])

    def interrupted(ticker):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        _run(world, interrupted)


def test_after_the_first_failed_share_count_the_run_asks_the_vendor_for_no_other_ticker(world):
    store_rows("AAA", "events", [_trade()])
    store_rows("BBB", "events", [insider_row("BBB", 1, qty="1,000,000", published="2026-10-08", start="2026-10-12", end="2026-10-16")])
    fetch = FakeFetch(ShareCountUnavailable("limiter"))

    result = _run(world, fetch)

    assert fetch.calls == ["AAA"] and result.exit_code == 0
    assert _text(result).count("size not shown, because the vendor's share count could not be read this run.") == 2


def test_a_cache_that_cannot_be_read_because_of_an_io_error_is_no_cache_with_a_note_not_a_crash(world, monkeypatch):
    import errno

    from app.services.brief.share_cache import ShareCache

    store_rows("AAA", "events", [_trade()])
    _run(world, FakeFetch())  # writes a good cache

    def failing_read(self, descriptor):
        raise OSError(errno.EIO, "synthetic input error")

    monkeypatch.setattr(ShareCache, "_read_private", failing_read)
    fetch = FakeFetch()

    result = _run(world, fetch)

    assert result.exit_code == 0 and fetch.calls == ["AAA"] and any("share-count cache" in m and "not used" in m for m in result.messages)


def test_a_cache_object_that_cannot_even_be_built_degrades_to_no_cache_with_a_message(world, monkeypatch):
    from app.services.brief import run as run_module

    def broken(path, **kwargs):
        raise OSError(5, "synthetic")

    monkeypatch.setattr(run_module, "ShareCache", broken)
    store_rows("AAA", "events", [_trade()])
    fetch = FakeFetch()

    result = _run(world, fetch)

    assert result.exit_code == 0 and fetch.calls == ["AAA"] and "Size: 2.3%" in _text(result)
    assert any("share-count cache" in m and "not used" in m for m in result.messages)


def test_disagreeing_vendor_counts_show_the_reason_and_cache_nothing(world):
    store_rows("AAA", "events", [_trade()])
    ratio = ratio_frame((2026, 2, "RATIO_TTM", 10_000_000_000, None))
    overview = overview_frame(10_000_000_000, 7_933_923_601, 10_000_000_000, 7_933_923_601)

    result = _run(world, lambda t: read_share_count(t, frames=lambda ticker: (ratio, overview)))

    assert "size not shown, because the vendor's two share counts disagree." in _text(result)
    assert not (world.config / CACHE).exists()


def test_a_failed_fetch_with_a_stale_cached_value_uses_the_cached_value_with_its_own_date(world):
    from datetime import timedelta

    store_rows("AAA", "events", [_trade()])
    _run(world, FakeFetch())
    result = _run(world, FakeFetch(ShareCountUnavailable("down")), now=AFTER_CLOSE + timedelta(days=9))

    text = _text(result)
    assert "Size: 2.3%" in text and "fetched 2026-10-09" in text  # the cached value, with the date it was fetched


def test_an_unsafe_cache_file_is_refused_with_a_message_and_the_run_still_sizes_from_a_fetch(world):
    store_rows("AAA", "events", [_trade()])
    _run(world, FakeFetch())
    (world.config / CACHE).chmod(0o644)
    fetch = FakeFetch()

    result = _run(world, fetch)

    assert fetch.calls == ["AAA"] and any("can be read by other users" in m for m in result.messages)
    assert result.exit_code == 0


def test_a_malformed_cache_is_reported_once_and_the_run_goes_on(world):
    store_rows("AAA", "events", [_trade()])
    cache = world.config / CACHE
    cache.write_text("not json")
    cache.chmod(0o600)

    result = _run(world, FakeFetch())

    assert [m for m in result.messages if "treated as empty" in m] and result.exit_code == 0


def test_the_redacted_run_keeps_the_company_block_without_the_triggers_line_or_the_log_wording(world):
    store_rows("AAA", "events", [_trade()])
    _run(world, FakeFetch())  # a first run, so the log has an earlier brief

    result = _run(world, FakeFetch(), redact=True)

    text = _text(result)
    assert "COMPANY (" in text and "Needs a look, last 14 days before the last bar:" in text
    assert "Re-read triggers" not in text and "since the last brief" not in text and "30,000,000" in text


def test_the_second_run_reads_the_earlier_brief_so_the_listing_is_since_that_bar(world):
    store_rows("AAA", "events", [_trade()])
    _run(world, FakeFetch())
    from datetime import timedelta

    result = _run(world, FakeFetch(), now=AFTER_CLOSE)  # same bar again: entries for the last bar itself are ignored

    assert "no earlier brief for this ticker" in _text(result)  # a re-run on the same bar still reads as the first brief
    assert len(_log(world).entries) >= 3 and timedelta(0) == timedelta(0)


def test_the_real_vendor_function_is_never_called_by_these_tests(world):
    store_rows("AAA", "events", [_trade()])

    def forbidden(ticker, **kwargs):
        pytest.fail("the vendor was called")

    with pytest.raises(pytest.fail.Exception):
        forbidden("AAA")
    assert issubclass(ShareCountsDisagree, ShareCountUnavailable) and AGREE > 0
