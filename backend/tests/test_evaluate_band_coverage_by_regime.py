"""Tests for `backend/scripts/evaluate_band_coverage_by_regime.py`.

The script lives under `backend/scripts/`, which is not a package, so it is loaded by path (the
precedent in `test_evaluate_fibonacci_levels.py`). Everything here is a small pure-function test on
synthetic series: no network (the vendor handle is a stub) and no real database.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND / "scripts"))
_spec = importlib.util.spec_from_file_location(
    "evaluate_band_coverage_by_regime", BACKEND / "scripts" / "evaluate_band_coverage_by_regime.py"
)
ebr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ebr  # dataclasses looks the module up by name
_spec.loader.exec_module(ebr)


# ---------------------------------------------------------------------------
# index fetch helper, with a stubbed vendor handle (tasks 1.1, 1.2)
# ---------------------------------------------------------------------------


class StubHandle:
    """Stands in for `Market().index("VNINDEX")`: records every call and answers from a canned frame."""

    def __init__(self, frame=None, raises=None):
        self.frame, self.raises, self.calls = frame, raises, []

    def ohlcv(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.frame


class ShallowVendor:
    """A vendor holding daily rows from `first` to 2026-10-08 that never returns more than `cap` rows
    ending at `end`, and never more than `count`: what the silent history limits look like."""

    def __init__(self, first="2015-01-01", cap=1500):
        self.times = pd.bdate_range(first, "2026-10-08").strftime("%Y-%m-%d")
        self.cap, self.calls = cap, []

    def ohlcv(self, *, start, end, count, **_):
        self.calls.append({"start": start, "end": end, "count": count})
        inside = [t for t in self.times if start <= t <= end]
        kept = inside[-min(count, self.cap):] if inside else []
        return pd.DataFrame({"time": kept, "close": np.linspace(100.0, 200.0, len(kept))})


def _frame(times, closes):
    return pd.DataFrame({"time": times, "close": closes})


def _no_sleep(_seconds):
    return None


def test_a_duplicated_latest_date_keeps_one_close_the_later_rows():
    frame = _frame(["2026-10-06", "2026-10-07", "2026-10-07"], [100.0, 101.0, 102.0])

    closes = ebr.fetch_index_closes("2026-10-01", "2026-10-08", handle=StubHandle(frame))

    assert list(closes.index) == ["2026-10-06", "2026-10-07"]
    assert closes["2026-10-07"] == 102.0


def test_the_call_passes_an_explicit_count_covering_every_session_in_the_span():
    handle = StubHandle(_frame(["2024-01-02"], [100.0]))

    ebr.fetch_index_closes("2016-01-01", "2026-10-08", handle=handle)

    (call,) = handle.calls
    assert call["count"] >= len(pd.bdate_range("2016-01-01", "2026-10-08"))
    assert (call["start"], call["end"]) == ("2016-01-01", "2026-10-08")


def test_a_frame_without_a_time_column_raises():
    handle = StubHandle(pd.DataFrame({"date": ["2026-10-07"], "close": [100.0]}))

    with pytest.raises(KeyError, match="time column missing"):
        ebr.fetch_index_closes("2026-10-01", "2026-10-08", handle=handle)


def test_an_empty_frame_is_an_error_not_an_empty_series():
    with pytest.raises(ValueError, match="no rows"):
        ebr.fetch_index_closes("2026-10-01", "2026-10-08", handle=StubHandle(pd.DataFrame()))


def test_vnais_rate_limit_exit_gives_no_series_and_a_named_error():
    handle = StubHandle(raises=SystemExit("Rate limit exceeded. 20/min Process terminated."))

    with pytest.raises(ebr.IndexRateLimited):
        ebr.fetch_index_closes("2026-10-01", "2026-10-08", handle=handle)


def test_any_other_system_exit_is_not_swallowed():
    handle = StubHandle(raises=SystemExit("shutting down"))

    with pytest.raises(SystemExit, match="shutting down"):
        ebr.fetch_index_closes("2026-10-01", "2026-10-08", handle=handle)


def test_a_rate_limit_exception_is_reported_the_same_way():
    from vnstock.core.exceptions import RateLimitError

    handle = StubHandle(raises=RateLimitError("too many requests"))

    with pytest.raises(ebr.IndexRateLimited):
        ebr.fetch_index_closes("2026-10-01", "2026-10-08", handle=handle)


def test_the_source_is_passed_only_when_one_is_pinned():
    handle = StubHandle(_frame(["2024-01-02"], [100.0]))

    ebr.fetch_index_closes("2024-01-01", "2024-01-31", handle=handle)
    ebr.fetch_index_closes("2024-01-01", "2024-01-31", handle=handle, source="vci")

    assert "source" not in handle.calls[0]
    assert handle.calls[1]["source"] == "vci"


# --- history shallower than needed: walk `end` backwards ---


def test_a_shallow_first_call_walks_end_backwards_until_the_earliest_date_stops_moving():
    vendor = ShallowVendor(first="2015-01-01", cap=1500)
    sleeps = []

    history = ebr.fetch_index_history(
        "2016-01-01", "2026-10-08", need_start="2018-12-31", handle=vendor, sleep=sleeps.append
    )

    assert len(vendor.calls) >= 2
    assert vendor.calls[1]["end"] < vendor.calls[0]["end"]  # each call starts further back
    assert history.closes.index[0] <= "2018-12-31"
    assert history.closes.index.is_unique and history.closes.index.is_monotonic_increasing
    assert len(sleeps) == len(vendor.calls) - 1
    assert all(seconds >= ebr.FETCH_PACE_SECONDS for seconds in sleeps)
    assert [c["first"] for c in history.calls] == sorted((c["first"] for c in history.calls), reverse=True)


def test_the_walk_stops_when_the_earliest_date_does_not_move():
    frame = _frame(["2020-01-02", "2020-01-03"], [100.0, 101.0])  # the vendor ignores `end`
    handle = StubHandle(frame)

    history = ebr.fetch_index_history(
        "2016-01-01", "2026-10-08", need_start="2018-12-31", handle=handle, sleep=_no_sleep
    )

    assert len(handle.calls) == 2  # the first, and one walk that found nothing earlier
    assert history.closes.index[0] == "2020-01-02"


def test_no_walk_when_the_first_call_already_reaches_the_needed_date():
    vendor = ShallowVendor(first="2015-01-01", cap=4000)

    history = ebr.fetch_index_history(
        "2016-01-01", "2026-10-08", need_start="2018-12-31", handle=vendor, sleep=_no_sleep
    )

    assert len(vendor.calls) == 1
    assert len(history.calls) == 1


def test_a_rate_limit_during_the_walk_returns_no_partial_series():
    class RateLimitedOnSecondCall(ShallowVendor):
        def ohlcv(self, **kwargs):
            if self.calls:
                raise SystemExit("Rate limit exceeded. Process terminated.")
            return super().ohlcv(**kwargs)

    with pytest.raises(ebr.IndexRateLimited):
        ebr.fetch_index_history(
            "2016-01-01", "2026-10-08", need_start="2018-12-31", handle=RateLimitedOnSecondCall(cap=1500),
            sleep=_no_sleep,
        )


def test_the_vendors_history_limit_warning_is_reported():
    import logging

    class WarningVendor(StubHandle):
        def ohlcv(self, **kwargs):
            logging.getLogger("vnstock.test").warning("Community edition: OHLCV data (1D) limited to 8 years.")
            return super().ohlcv(**kwargs)

    history = ebr.fetch_index_history(
        "2016-01-01", "2026-10-08", need_start="2019-12-31",
        handle=WarningVendor(_frame(["2018-10-09", "2018-10-10"], [100.0, 101.0])), sleep=_no_sleep,
    )

    assert history.history_limit_warning is True


def test_the_depth_summary_reports_first_last_sessions_and_calendar_gaps_over_ten_days():
    closes = pd.Series([1.0, 2.0, 3.0, 4.0], index=["2020-01-02", "2020-01-03", "2020-01-20", "2020-01-21"])

    depth = ebr.index_depth(closes)

    assert (depth["first_date"], depth["last_date"], depth["sessions"]) == ("2020-01-02", "2020-01-21", 4)
    assert depth["gaps_over_10_days"] == [("2020-01-03", "2020-01-20", 17)]


# --- the CLI's depth-only mode ---


def test_depth_only_prints_the_depth_and_writes_no_file(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    vendor = ShallowVendor(first="2015-01-01", cap=4000)
    monkeypatch.setattr(ebr, "_index_handle", lambda: vendor)
    monkeypatch.setattr(ebr.time, "sleep", _no_sleep)

    ebr.main(["--depth-only"])

    out = capsys.readouterr().out
    assert out.splitlines()[0].lower().startswith("study output")
    assert "first date" in out and "sessions" in out
    assert list(tmp_path.iterdir()) == []


def test_depth_only_exits_non_zero_on_a_rate_limit(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ebr, "_index_handle", lambda: StubHandle(raises=SystemExit("Rate limit exceeded.")))

    with pytest.raises(SystemExit) as exit_info:
        ebr.main(["--depth-only"])

    assert exit_info.value.code not in (0, None)
    assert list(tmp_path.iterdir()) == []
