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


# ---------------------------------------------------------------------------
# regime: trailing percentile of the index's 20-session volatility, in thirds (tasks 2.1, 2.2)
# ---------------------------------------------------------------------------


def _closes(n: int, seed: int = 1, vol: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-10-11", periods=n).strftime("%Y-%m-%d")
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0, vol, n))), index=dates)


def test_changing_an_index_close_after_t_leaves_the_regime_at_t_and_earlier_unchanged():
    closes = _closes(600)
    changed = closes.copy()
    changed.iloc[401:] = changed.iloc[401:] * 3.0  # a jump on session 401, nothing before it differs

    before, after = ebr.regime_labels(closes), ebr.regime_labels(changed)

    assert before.iloc[:401].equals(after.iloc[:401])
    assert after.iloc[401] == ebr.VOLATILE  # the jump is visible on its own session


def test_400_closes_give_129_sessions_with_a_regime_and_the_first_271_have_none():
    labels = ebr.regime_labels(_closes(400))

    assert len(labels) == 400
    assert labels.iloc[:271].isna().all()
    assert labels.iloc[271:].notna().all()
    assert labels.notna().sum() == 129


def test_200_closes_give_no_regime_at_all():
    labels = ebr.regime_labels(_closes(200))

    assert len(labels) == 200
    assert labels.isna().all()


def test_the_index_volatility_is_the_std_of_the_last_20_daily_log_returns():
    closes = _closes(60)
    expected = np.log(closes / closes.shift(1)).rolling(20).std()

    sigma = ebr.index_volatility(closes)

    assert sigma.iloc[:20].isna().all()  # 20 returns need 21 closes
    pd.testing.assert_series_equal(sigma, expected, check_names=False)


def _window_ending_at_rank(rank: int) -> pd.Series:
    """252 volatility values 1..252 whose last one has exactly `rank` values at or below it."""
    values = [v for v in range(1, 253) if v != rank] + [rank]
    return pd.Series(np.array(values, float), index=pd.bdate_range("2020-01-01", periods=252).strftime("%Y-%m-%d"))


@pytest.mark.parametrize(
    "rank, expected",
    [(1, "calm"), (84, "calm"), (85, "middle"), (168, "middle"), (169, "volatile"), (252, "volatile")],
)
def test_thirds_split_at_one_third_and_two_thirds_of_the_percentile(rank, expected):
    percentile = ebr.trailing_percentile(_window_ending_at_rank(rank))

    assert percentile.iloc[-1] == pytest.approx(rank / 252)
    assert ebr.label_thirds(percentile).iloc[-1] == expected


def test_the_percentile_counts_ties_as_at_or_below():
    flat = pd.Series(np.ones(252), index=pd.bdate_range("2020-01-01", periods=252).strftime("%Y-%m-%d"))

    assert ebr.trailing_percentile(flat).iloc[-1] == 1.0


def test_the_percentile_has_no_value_before_252_volatility_values():
    percentile = ebr.trailing_percentile(_window_ending_at_rank(100).iloc[:251])

    assert percentile.isna().all()


def test_the_expanding_variant_uses_every_prior_value_but_needs_at_least_252():
    values = np.array([1000.0] * 60 + list(range(1, 241)))  # 300 values, the last is 240
    sigma = pd.Series(values, index=pd.bdate_range("2020-01-01", periods=300).strftime("%Y-%m-%d"))

    trailing, expanding = ebr.trailing_percentile(sigma), ebr.expanding_percentile(sigma)

    assert expanding.iloc[:251].isna().all() and expanding.iloc[251:].notna().all()
    assert expanding.iloc[251] == trailing.iloc[251]  # the same 252 values
    assert expanding.iloc[-1] == pytest.approx(240 / 300)  # all 300 prior values
    assert trailing.iloc[-1] == pytest.approx(240 / 252)  # the last 252 only (12 of the 1000s have left)


def test_a_stock_window_whose_date_has_no_index_close_is_excluded_and_counted():
    labels = pd.Series({"2020-01-02": "calm", "2020-01-03": "volatile", "2020-01-06": np.nan})
    windows = pd.DataFrame({
        "date": ["2020-01-02", "2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"],
        "hit": [True, False, True, True, False],
    })

    kept, exclusions = ebr.attach_regime(windows, labels)

    assert list(kept["regime"]) == ["calm", "calm", "volatile"]
    assert exclusions["windows"] == 5
    assert exclusions["no_index_close"] == 1  # 2020-01-07 has no index close
    assert exclusions["warm_up"] == 1  # 2020-01-06 has a close but no regime yet
    assert exclusions["with_regime"] == 3
    assert exclusions["index_match"] == pytest.approx(3 / 4)  # 3 of the 4 distinct dates have an index close


# ---------------------------------------------------------------------------
# the outcome rule: one test per spec scenario (tasks 2.3, 2.4)
# ---------------------------------------------------------------------------


def _half(gap, lo, hi, months=36, calm_months=20, volatile_months=20):
    return {"gap": gap, "ci": (lo, hi), "months": months, "calm_months": calm_months,
            "volatile_months": volatile_months}


def _year_adjusted(gap, lo, hi):
    return {"gap": gap, "ci": (lo, hi)}


def _decide(early, late, year_adjusted=None, index_match=1.0):
    return ebr.decide_outcome(early, late, year_adjusted, index_match)


def test_both_halves_clear_the_level_and_the_year_adjusted_gap_agrees_is_a_pass():
    result = _decide(
        _half(0.07, 0.02, 0.12), _half(0.06, 0.01, 0.11), _year_adjusted(0.055, 0.005, 0.105)
    )

    assert result["outcome"] == "PASS"
    assert result["reasons"] == []


def test_one_half_below_the_level_is_a_kill_whatever_the_intervals():
    result = _decide(_half(0.07, 0.02, 0.12), _half(0.03, -0.05, 0.11), _year_adjusted(0.05, 0.01, 0.09))

    assert result["outcome"] == "KILL"


def test_opposite_signs_are_a_kill():
    result = _decide(_half(0.06, 0.01, 0.11), _half(-0.06, -0.11, -0.01), _year_adjusted(0.0, -0.05, 0.05))

    assert result["outcome"] == "KILL"
    assert any("opposite" in reason for reason in result["reasons"])


def test_a_large_gap_whose_interval_includes_zero_is_inconclusive_and_says_it_is_not_evidence_of_no_effect():
    result = _decide(_half(0.07, 0.02, 0.12), _half(0.06, -0.03, 0.15), _year_adjusted(0.065, 0.01, 0.12))

    assert result["outcome"] == "INCONCLUSIVE"
    assert any("late interval" in reason for reason in result["reasons"])
    assert any("not evidence" in note for note in result["notes"])


def test_a_gap_not_separable_from_the_by_year_variation_is_inconclusive():
    result = _decide(_half(0.07, 0.02, 0.12), _half(0.06, 0.01, 0.11), _year_adjusted(0.05, -0.02, 0.12))

    assert result["outcome"] == "INCONCLUSIVE"
    assert any("year-adjusted" in reason for reason in result["reasons"])


def test_no_year_with_both_thirds_populated_leaves_the_year_adjusted_gap_unavailable():
    result = _decide(_half(0.07, 0.02, 0.12), _half(0.06, 0.01, 0.11), None)

    assert result["outcome"] == "INCONCLUSIVE"
    assert any("year-adjusted" in reason for reason in result["reasons"])


def test_a_year_adjusted_gap_of_the_opposite_sign_is_inconclusive():
    result = _decide(_half(0.07, 0.02, 0.12), _half(0.06, 0.01, 0.11), _year_adjusted(-0.06, -0.11, -0.01))

    assert result["outcome"] == "INCONCLUSIVE"
    assert any("year-adjusted" in reason and "sign" in reason for reason in result["reasons"])


def test_a_half_with_14_months_is_not_evaluable_whatever_the_late_half_shows():
    early = _half(0.07, 0.02, 0.12, months=14)
    late = _half(0.0, -0.04, 0.04)  # would be a KILL if it were reached

    result = _decide(early, late, _year_adjusted(0.05, 0.01, 0.09))

    assert result["outcome"] == "INCONCLUSIVE"
    assert any("early half is not evaluable" in reason for reason in result["reasons"])


def test_a_third_with_too_few_months_makes_the_half_not_evaluable():
    early = _half(0.07, 0.02, 0.12, volatile_months=7)

    result = _decide(early, _half(0.06, 0.01, 0.11), _year_adjusted(0.05, 0.01, 0.09))

    assert result["outcome"] == "INCONCLUSIVE"
    assert any("early half is not evaluable" in reason for reason in result["reasons"])


def test_a_half_with_no_windows_is_not_evaluable():
    nothing = {"gap": None, "ci": (None, None), "months": 0, "calm_months": 0, "volatile_months": 0}

    result = _decide(nothing, nothing, None)

    assert result["outcome"] == "INCONCLUSIVE"


def test_an_index_match_below_99_percent_is_inconclusive():
    result = _decide(
        _half(0.07, 0.02, 0.12), _half(0.06, 0.01, 0.11), _year_adjusted(0.055, 0.005, 0.105), index_match=0.98
    )

    assert result["outcome"] == "INCONCLUSIVE"
    assert any("index close" in reason for reason in result["reasons"])


def test_a_gap_of_exactly_five_points_meets_the_level():
    result = _decide(_half(0.05, 0.01, 0.09), _half(0.05, 0.01, 0.09), _year_adjusted(0.05, 0.01, 0.09))

    assert result["outcome"] == "PASS"


def test_a_kill_whose_interval_reaches_the_level_says_it_is_not_evidence_of_no_effect():
    result = _decide(_half(0.07, 0.02, 0.12), _half(0.03, -0.01, 0.07), _year_adjusted(0.05, 0.01, 0.09))

    assert result["outcome"] == "KILL"
    assert any("not evidence" in note for note in result["notes"])


def test_the_constants_equal_the_specs_values():
    assert ebr.PASS_GAP == 0.05
    assert ebr.SPLIT_DATE == "2023-01-01"
    assert ebr.VOL_WINDOW == 20
    assert ebr.PERCENTILE_WINDOW == 252
    assert ebr.CONFIDENCE == 0.95
    assert ebr.MIN_MONTHS_PER_HALF == 24
    assert ebr.MIN_MONTHS_PER_CELL == 8
    assert ebr.MIN_DATES_PER_YEAR_CELL == 20
    assert ebr.MIN_INDEX_MATCH == 0.99
    assert (ebr.BOOTSTRAP_RESAMPLES, ebr.SEED) == (2000, 0)


# ---------------------------------------------------------------------------
# gaps, intervals and cell statistics (tasks 2.5, 2.6)
# ---------------------------------------------------------------------------

DATES_PER_MONTH = 10
REGIME_BY_DATE_IN_MONTH = [ebr.CALM] * 3 + [ebr.MIDDLE] * 4 + [ebr.VOLATILE] * 3  # one regime per date


def _cells(p_calm, p_volatile, months=30, start="2020-01", n=300, seed=0, p_middle=0.68):
    """Per-date, per-regime hit counts: every date has one regime, as an index date does."""
    rng = np.random.default_rng(seed)
    probability = {ebr.CALM: p_calm, ebr.MIDDLE: p_middle, ebr.VOLATILE: p_volatile}
    rows = []
    for period in pd.period_range(start, periods=months, freq="M"):
        for day, regime in enumerate(REGIME_BY_DATE_IN_MONTH, 1):
            rows.append((f"{period}-{day:02d}", regime, int(rng.binomial(n, probability[regime])), n))
    return pd.DataFrame(rows, columns=["date", "regime", "hits", "n"])


def test_a_ten_point_effect_in_every_month_gives_an_interval_that_excludes_zero():
    result = ebr.gap_interval(_cells(0.75, 0.65))

    assert result["gap"] == pytest.approx(0.10, abs=0.01)
    assert result["ci"][0] > 0
    assert result["half_width"] == pytest.approx((result["ci"][1] - result["ci"][0]) / 2)


def test_equal_probabilities_give_an_interval_that_includes_zero():
    result = ebr.gap_interval(_cells(0.68, 0.68, seed=0))

    assert result["ci"][0] < 0 < result["ci"][1]


def test_the_same_seed_gives_identical_intervals():
    cells = _cells(0.72, 0.66, seed=5)

    assert ebr.gap_interval(cells) == ebr.gap_interval(cells)
    assert ebr.year_adjusted_gap(cells) == ebr.year_adjusted_gap(cells)


def test_draws_with_an_empty_cell_are_dropped_and_their_share_is_reported():
    cells = _cells(0.75, 0.65, months=6)
    last_month = cells["date"].str[:7] == cells["date"].str[:7].max()
    only_in_one_month = ~((cells["regime"] == ebr.VOLATILE) & ~last_month)  # volatile windows only in the last month

    result = ebr.gap_interval(cells[only_in_one_month])

    assert 0.1 < result["dropped_share"] < 0.9  # about 1 - (5/6)**6 of the draws miss that month
    assert np.isfinite(result["ci"]).all()


def test_a_sample_without_one_of_the_two_thirds_has_no_gap():
    calm_only = _cells(0.75, 0.65)[lambda c: c["regime"] == ebr.CALM]

    result = ebr.gap_interval(calm_only)

    assert result["gap"] is None
    assert result["ci"] == (None, None)


def test_the_quarter_block_interval_runs_on_the_same_cells():
    cells = _cells(0.75, 0.65)

    month, quarter = ebr.gap_interval(cells, block="month"), ebr.gap_interval(cells, block="quarter")

    assert quarter["gap"] == month["gap"]  # the same point estimate
    assert quarter["blocks"] < month["blocks"]
    assert quarter["ci"][0] > 0


@pytest.mark.parametrize(
    "month_ci, quarter_ci, flagged",
    [((0.01, 0.09), (-0.02, 0.10), True), ((-0.02, 0.10), (0.01, 0.09), True), ((0.01, 0.09), (0.02, 0.08), False),
     ((-0.05, 0.05), (-0.06, 0.04), False)],
)
def test_interval_disagreement_about_whether_zero_is_excluded_is_flagged(month_ci, quarter_ci, flagged):
    assert ebr.interval_disagreement(month_ci, quarter_ci) is flagged


def test_the_disagreement_flag_is_raised_on_a_constructed_sample():
    # Eight quarters with a different gap each: months are many small blocks, quarters are few large ones,
    # so the quarter-block interval is wider and can include zero where the month-block one does not.
    quarter_gap = [0.20, -0.06, 0.16, -0.06, 0.14, -0.04, 0.18, -0.04]
    rows = []
    for index, gap in enumerate(quarter_gap):
        for month in range(3):
            period = pd.Period("2020-01", "M") + 3 * index + month
            for day, regime in enumerate(REGIME_BY_DATE_IN_MONTH, 1):
                rate = {ebr.CALM: 0.68 + gap / 2, ebr.MIDDLE: 0.68, ebr.VOLATILE: 0.68 - gap / 2}[regime]
                rows.append((f"{period}-{day:02d}", regime, int(round(rate * 1000)), 1000))
    cells = pd.DataFrame(rows, columns=["date", "regime", "hits", "n"])

    month, quarter = ebr.gap_interval(cells, block="month"), ebr.gap_interval(cells, block="quarter")

    assert ebr.interval_disagreement(month["ci"], quarter["ci"]) is True


def test_the_year_adjusted_gap_is_the_equal_weighted_mean_of_each_years_gap():
    cells = pd.concat([_cells(0.75, 0.65, months=24, start="2020-01", seed=1),
                       _cells(0.73, 0.67, months=12, start="2022-01", seed=2)], ignore_index=True)

    result = ebr.year_adjusted_gap(cells)

    assert result["years"] == [2020, 2021, 2022]
    assert result["gap"] == pytest.approx((0.10 + 0.10 + 0.06) / 3, abs=0.012)
    assert result["ci"][0] > 0


def test_a_year_where_a_third_has_windows_on_fewer_than_20_dates_does_not_enter_the_year_adjusted_gap():
    full = _cells(0.75, 0.65, months=12, start="2020-01")
    short = _cells(0.50, 0.90, months=2, start="2021-01")  # 6 calm and 6 volatile dates in 2021: under 20 each

    result = ebr.year_adjusted_gap(pd.concat([full, short], ignore_index=True))

    assert result["years"] == [2020]
    assert result["gap"] == pytest.approx(0.10, abs=0.02)


def test_no_qualifying_year_gives_no_year_adjusted_gap():
    assert ebr.year_adjusted_gap(_cells(0.75, 0.65, months=2)) is None


def test_the_year_adjusted_interval_includes_zero_when_two_years_have_opposite_gaps():
    cells = pd.concat([_cells(0.75, 0.65, months=12, start="2020-01", seed=1),
                       _cells(0.65, 0.75, months=12, start="2021-01", seed=2)], ignore_index=True)

    result = ebr.year_adjusted_gap(cells)

    assert abs(result["gap"]) < 0.01
    assert result["ci"][0] < 0 < result["ci"][1]


def test_cell_statistics_carry_windows_dates_months_episodes_coverage_and_per_date_spread():
    cells = pd.DataFrame({
        "date": ["2020-01-02", "2020-01-03", "2020-01-06", "2020-02-03"],
        "regime": ["calm", "calm", "volatile", "calm"],
        "hits": [80, 60, 50, 90],
        "n": [100, 100, 100, 100],
    })
    labels = pd.Series({"2020-01-02": "calm", "2020-01-03": "calm", "2020-01-06": "volatile", "2020-02-03": "calm"})

    stats = ebr.cell_stats(cells, labels)

    calm = stats["calm"]
    assert (calm["windows"], calm["dates"], calm["months"], calm["episodes"]) == (300, 3, 2, 2)
    assert calm["coverage"] == pytest.approx(230 / 300)
    assert calm["date_mean"] == pytest.approx(np.mean([0.8, 0.6, 0.9]))
    assert calm["date_sd"] == pytest.approx(np.std([0.8, 0.6, 0.9], ddof=1))
    assert stats["volatile"]["episodes"] == 1
    assert stats["middle"]["windows"] == 0


def test_episodes_are_maximal_runs_of_consecutive_sessions_in_one_third():
    labels = pd.Series(["calm", "calm", "volatile", "volatile", "volatile", "calm", "middle"],
                       index=pd.bdate_range("2020-01-02", periods=7).strftime("%Y-%m-%d"))

    assert ebr.episode_counts(labels) == {"calm": 2, "middle": 1, "volatile": 1}


# ---------------------------------------------------------------------------
# the band under test, out of time (tasks 3.1, 3.2)
# ---------------------------------------------------------------------------


def _window_frame(n_tickers: int = 4, n_rows: int = 1500) -> pd.DataFrame:
    """Windows from `build_window_frame` for several synthetic tickers, prepared as the training script does."""
    import train_har_rv as train
    from app.ml.volatility import build_window_frame

    rng = np.random.default_rng(9)
    dates = pd.Series(pd.bdate_range("2019-01-01", periods=n_rows).strftime("%Y-%m-%d"))
    parts = []
    for i in range(n_tickers):
        closes = pd.Series(20 * np.exp(np.cumsum(rng.normal(0, 0.015, n_rows))))
        parts.append(build_window_frame(dates, closes).assign(ticker=f"T{i}"))
    return train.prepare(pd.concat(parts, ignore_index=True))


def test_each_folds_year_window_count_and_coverage_equal_the_training_scripts():
    import train_har_rv as train

    frame = _window_frame()

    windows, folds = ebr.out_of_time_windows(frame, min_train_rows=1000)
    reference = train.run_validation(frame, min_train_rows=1000)["folds"]

    assert len(folds) == len(reference) >= 3
    for ours, theirs in zip(folds, reference):
        assert ours["test_year"] == theirs["test_year"]
        assert ours["n"] == theirs["n"]
        assert ours["coverage"] == pytest.approx(theirs["coverage"], abs=0)
        assert ours["k"] == pytest.approx(theirs["k"], abs=0)
    assert len(windows) == sum(f["n"] for f in folds)


def test_the_windows_keep_each_test_windows_date_and_hit():
    frame = _window_frame()

    windows, folds = ebr.out_of_time_windows(frame, min_train_rows=1000)

    assert list(windows.columns) == ["date", "hit"]
    assert windows["hit"].dtype == bool
    by_year = windows.groupby(windows["date"].str[:4])["hit"].agg(["size", "mean"])
    for fold in folds:
        assert by_year.loc[str(fold["test_year"]), "size"] == fold["n"]
        assert by_year.loc[str(fold["test_year"]), "mean"] == pytest.approx(fold["coverage"], abs=0)


def test_a_fold_needs_enough_purged_prior_windows():
    frame = _window_frame()

    windows, folds = ebr.out_of_time_windows(frame, min_train_rows=10**9)

    assert folds == [] and windows.empty
    assert list(windows.columns) == ["date", "hit"]


def test_the_by_year_table_is_recomputed_and_the_reviewers_range_is_only_a_labelled_reference():
    folds = [{"test_year": 2020, "n": 1000, "coverage": 0.6411, "k": 1.2},
             {"test_year": 2021, "n": 2000, "coverage": 0.7288, "k": 1.2}]

    text = ebr.format_by_year(folds)

    assert "2020" in text and "64.1%" in text and "72.9%" in text and "1,000" in text
    assert "0.6411" not in text  # Rule 2 spirit: percentages, never raw fractions
    reference = [line for line in text.splitlines() if "61.4%" in line]
    assert len(reference) == 1
    assert "reviewer-reported" in reference[0] and "not re-verified" in reference[0] and "74.1%" in reference[0]
    assert ebr.REVIEWER_REPORTED_BY_YEAR == (0.614, 0.741)


# ---------------------------------------------------------------------------
# the assembled read-only script: database, CSV cache, report (tasks 4.1, 4.2)
# ---------------------------------------------------------------------------

SYMBOLS = ("AAA", "BBB", "CCC", "DDD")


def _make_db(path: Path, symbols=SYMBOLS, n_rows: int = 1500) -> None:
    import sqlite3

    from app.db.schema import CREATE_OHLCV_TABLE, CREATE_TICKER_UNIVERSE_TABLE

    rng = np.random.default_rng(5)
    dates = pd.bdate_range("2019-01-01", periods=n_rows).strftime("%Y-%m-%d")
    conn = sqlite3.connect(path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    for symbol in symbols:
        closes = 20 * np.exp(np.cumsum(rng.normal(0, 0.015, n_rows)))
        conn.executemany(
            "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, 1000)",
            [(symbol, d, c, c, c, c) for d, c in zip(dates, closes)],
        )
        conn.execute(
            "INSERT INTO ticker_universe (symbol, listing_status, fails_liquidity_filter, "
            "below_minimum_history, ingestion_state, updated_at) VALUES (?, 'listed', 0, 0, 'ok', 'x')",
            (symbol,),
        )
    conn.commit()
    conn.close()


def _index_series() -> pd.Series:
    """Index closes on the same business-day calendar as the synthetic stocks, starting a year earlier."""
    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2018-01-01", periods=2000).strftime("%Y-%m-%d")
    return pd.Series(1000 * np.exp(np.cumsum(rng.normal(0, 0.01, 2000))), index=dates)


@pytest.fixture
def small_folds(monkeypatch):
    """The synthetic database has a few thousand windows, not the 40,000 a real fold needs."""
    monkeypatch.setattr(ebr, "MIN_TRAIN_ROWS", 1000)


@pytest.fixture
def study_db(tmp_path, small_folds):
    path = tmp_path / "db" / "app.db"
    path.parent.mkdir()
    _make_db(path)
    return path


def _no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("the study made a vendor call")

    monkeypatch.setattr(ebr, "fetch_index_history", refuse)
    monkeypatch.setattr(ebr, "_index_handle", refuse)


def test_the_study_leaves_the_database_bytes_unchanged_and_its_connection_cannot_write(study_db, monkeypatch):
    import hashlib
    import sqlite3

    before = hashlib.sha256(study_db.read_bytes()).hexdigest()
    siblings = sorted(p.name for p in study_db.parent.iterdir())
    write_attempts = []
    real_open = ebr.open_readonly

    def spying_open(path):
        conn = real_open(path)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("INSERT INTO ohlcv VALUES ('ZZZ', '2020-01-01', 1, 1, 1, 1, 1)")
        write_attempts.append(conn)
        return conn

    monkeypatch.setattr(ebr, "open_readonly", spying_open)

    report = ebr.run(study_db, _index_series())

    assert write_attempts, "the script never opened the database through open_readonly"
    assert hashlib.sha256(study_db.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in study_db.parent.iterdir()) == siblings  # no journal, no model file
    assert report["outcome"]["outcome"] in ("PASS", "KILL", "INCONCLUSIVE")


def test_no_file_is_created_without_fetch_index_or_json(study_db, tmp_path, monkeypatch, capsys):
    csv = tmp_path / "cache.csv"
    ebr.write_index_csv(csv, _index_series())
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    cache_before = sorted(p.name for p in tmp_path.iterdir())
    _no_network(monkeypatch)

    ebr.main(["--db", str(study_db), "--index-csv", str(csv)])

    assert list(workdir.iterdir()) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == cache_before


def test_the_first_output_line_says_study_output_not_shown_to_users_not_advice(study_db, tmp_path, monkeypatch, capsys):
    csv = tmp_path / "cache.csv"
    ebr.write_index_csv(csv, _index_series())
    _no_network(monkeypatch)

    ebr.main(["--db", str(study_db), "--index-csv", str(csv)])

    first = capsys.readouterr().out.splitlines()[0].lower()
    assert first.startswith("study output")
    assert "not shown to any user" in first and "not investment advice" in first


def test_a_cached_csv_makes_no_network_call_and_the_report_names_its_sha256(study_db, tmp_path, monkeypatch, capsys):
    import hashlib

    csv = tmp_path / "cache.csv"
    ebr.write_index_csv(csv, _index_series())
    _no_network(monkeypatch)  # any vendor call raises

    ebr.main(["--db", str(study_db), "--index-csv", str(csv)])

    assert hashlib.sha256(csv.read_bytes()).hexdigest() in capsys.readouterr().out


def test_fetch_index_writes_a_date_close_csv_that_reads_back_the_same_series(study_db, tmp_path, monkeypatch, capsys):
    import hashlib

    series = _index_series()
    history = ebr.IndexHistory(series, [{"end": "x", "count": 1, "rows": len(series), "first": series.index[0],
                                         "last": series.index[-1]}], False, ())
    monkeypatch.setattr(ebr, "fetch_index_history", lambda *a, **k: history)
    csv = tmp_path / "cache" / "vnindex_closes.csv"

    ebr.main(["--db", str(study_db), "--fetch-index", str(csv)])

    assert csv.read_text().splitlines()[0] == "date,close"
    pd.testing.assert_series_equal(ebr.read_index_csv(csv), series, check_names=False)
    assert hashlib.sha256(csv.read_bytes()).hexdigest() in capsys.readouterr().out


def test_a_rate_limit_while_fetching_exits_non_zero_and_writes_no_csv(study_db, tmp_path, monkeypatch):
    def limited(*_args, **_kwargs):
        raise ebr.IndexRateLimited("Rate limit exceeded")

    monkeypatch.setattr(ebr, "fetch_index_history", limited)
    csv = tmp_path / "cache" / "vnindex_closes.csv"

    with pytest.raises(SystemExit) as exit_info:
        ebr.main(["--db", str(study_db), "--fetch-index", str(csv)])

    assert exit_info.value.code not in (0, None)
    assert not csv.exists() and not csv.parent.exists()


def test_json_is_written_only_when_asked_and_carries_the_outcome(study_db, tmp_path, monkeypatch):
    import json

    csv, out = tmp_path / "cache.csv", tmp_path / "out" / "report.json"
    ebr.write_index_csv(csv, _index_series())
    _no_network(monkeypatch)

    ebr.main(["--db", str(study_db), "--index-csv", str(csv), "--json", str(out)])

    report = json.loads(out.read_text())
    assert report["outcome"]["outcome"] in ("PASS", "KILL", "INCONCLUSIVE")
    assert report["header"].lower().startswith("study output")
    assert report["index"]["sha256"]


def test_the_modelling_universe_is_read_at_run_time(study_db):
    import sqlite3

    first = ebr.run(study_db, _index_series())
    conn = sqlite3.connect(study_db)
    conn.execute("UPDATE ticker_universe SET fails_liquidity_filter = 1 WHERE symbol = 'DDD'")
    conn.commit()
    conn.close()

    second = ebr.run(study_db, _index_series())

    assert first["universe"]["symbols"] == 4
    assert second["universe"]["symbols"] == 3  # no code edit


def test_the_report_prints_counts_exclusions_intervals_and_the_outcome(study_db):
    text = ebr.format_report(ebr.run(study_db, _index_series()))

    for expected in ("windows", "episodes", "no index close", "warm-up", "month-block", "quarter-block",
                     "half-width", "year-adjusted", "expanding", "OUTCOME:", "reviewer-reported"):
        assert expected in text, expected
    assert text.splitlines()[0].lower().startswith("study output")


def test_the_outcome_uses_no_debate_verdict_label_and_no_instruction(study_db):
    text = ebr.format_report(ebr.run(study_db, _index_series())).lower()

    for word in ("buy", "sell", "hold ", "accumulate", "reduce"):
        assert word not in text


def test_a_series_shorter_than_the_warm_up_gives_inconclusive(study_db):
    report = ebr.run(study_db, _index_series().iloc[:200])

    assert report["outcome"]["outcome"] == "INCONCLUSIVE"
    assert report["regime"]["exclusions"]["with_regime"] == 0
