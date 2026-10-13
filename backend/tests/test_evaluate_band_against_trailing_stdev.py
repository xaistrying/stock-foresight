"""Tests for `backend/scripts/evaluate_band_against_trailing_stdev.py`.

The script lives under `backend/scripts/`, which is not a package, so it is loaded by path (the
precedent in `test_evaluate_band_coverage_by_regime.py`). Everything here is a small pure-function
test on synthetic series or a temporary database: no network and no real database.
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
    "evaluate_band_against_trailing_stdev", BACKEND / "scripts" / "evaluate_band_against_trailing_stdev.py"
)
ebt = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ebt
_spec.loader.exec_module(ebt)


def _window_frame(n_tickers: int = 4, n_rows: int = 1500, seed: int = 9, start: str = "2019-01-01") -> pd.DataFrame:
    """Windows from `build_window_frame` for several synthetic tickers, prepared as the training script does."""
    import train_har_rv as train
    from app.ml.volatility import build_window_frame

    rng = np.random.default_rng(seed)
    dates = pd.Series(pd.bdate_range(start, periods=n_rows).strftime("%Y-%m-%d"))
    parts = []
    for i in range(n_tickers):
        closes = pd.Series(20 * np.exp(np.cumsum(rng.normal(0, 0.015, n_rows))))
        parts.append(build_window_frame(dates, closes).assign(ticker=f"T{i}"))
    return train.prepare(pd.concat(parts, ignore_index=True))


# ---------------------------------------------------------------------------
# constants (task 2.1)
# ---------------------------------------------------------------------------


def test_the_constants_equal_the_specs_values():
    assert ebt.MARGIN == 0.02
    assert ebt.CONFIDENCE == 0.975
    assert ebt.BOOTSTRAP_RESAMPLES == 2000
    assert ebt.SEED == 0
    assert ebt.CALIBRATION_GUARD == 0.05
    assert ebt.MIN_YEARS == 5
    assert ebt.MIN_MONTHS == 60
    assert ebt.YEAR_CONSISTENCY == pytest.approx(2 / 3)
    assert ebt.NOMINAL_COVERAGE == 0.68
    assert ebt.TRAILING_WINDOW == 20
    assert ebt.LITERAL_BAND == 2.5
    assert ebt.COMPARATORS == ("trailing", "constant")


# ---------------------------------------------------------------------------
# the bands (tasks 2.1, 2.2)
# ---------------------------------------------------------------------------


def test_k20_is_the_068_quantile_of_the_ratio_over_the_fit_windows_only():
    frame = _window_frame()
    fit, test = ebt.split_fold(frame, 2023)
    fit, _ = ebt.valid_windows(fit)

    expected = np.quantile(fit["abs_r5_pct"].to_numpy() / (np.sqrt(5) * fit["rv20"].to_numpy() * 100), 0.68)

    assert ebt.fit_trailing_k(fit) == pytest.approx(expected, abs=1e-12)
    changed = fit.copy()  # a test window's outcome is not in `fit`, so changing it cannot move k20
    test_changed = test.assign(abs_r5_pct=test["abs_r5_pct"] * 5)
    assert test_changed["abs_r5_pct"].sum() != test["abs_r5_pct"].sum()
    assert ebt.fit_trailing_k(changed) == ebt.fit_trailing_k(fit)


def test_the_fitted_constant_is_the_068_quantile_of_the_move_over_the_fit_windows_and_the_same_for_every_row():
    frame = _window_frame()
    fit, test = ebt.split_fold(frame, 2023)
    fit, _ = ebt.valid_windows(fit)

    constant = ebt.fit_constant(fit)

    assert constant == pytest.approx(np.quantile(fit["abs_r5_pct"].to_numpy(), 0.68), abs=1e-12)
    widths = ebt.constant_half_width(test, constant)
    assert len(widths) == len(test) and set(widths) == {constant}


def test_the_literal_band_is_2_5_in_every_row():
    frame = _window_frame(n_tickers=1, n_rows=400)

    assert set(ebt.constant_half_width(frame, ebt.LITERAL_BAND)) == {2.5}


def test_the_trailing_half_width_is_k20_times_root_5_times_rv20_in_percent():
    frame = _window_frame(n_tickers=1, n_rows=400)

    widths = ebt.trailing_half_width(frame, 1.3)

    assert widths == pytest.approx(1.3 * np.sqrt(5) * frame["rv20"].to_numpy() * 100, rel=1e-12)


def test_a_window_with_zero_rv20_is_excluded_and_counted():
    frame = _window_frame(n_tickers=1, n_rows=400)
    broken = frame.copy()
    broken.loc[broken.index[[3, 7]], "rv20"] = 0.0
    broken.loc[broken.index[11], "rv20"] = np.nan

    kept, excluded = ebt.valid_windows(broken)

    assert excluded == 3 and len(kept) == len(frame) - 3
    assert (kept["rv20"] > 0).all()


def test_every_band_at_t_ignores_closes_after_t():
    """Features are trailing, so a later close can move only windows whose own history includes it."""
    from app.ml.volatility import build_window_frame

    rng = np.random.default_rng(3)
    dates = pd.Series(pd.bdate_range("2019-01-01", periods=600).strftime("%Y-%m-%d"))
    closes = pd.Series(20 * np.exp(np.cumsum(rng.normal(0, 0.015, 600))))
    later = closes.copy()
    later.iloc[400:] = later.iloc[400:] * 1.5  # every close from position 400 on changes
    a, b = build_window_frame(dates, closes), build_window_frame(dates, later)
    a, b = a[a["pos"] < 400], b[b["pos"] < 400]  # windows that start before the change

    for column in ("rv5", "rv20", "rv60"):  # all three inputs of the HAR band and the trailing band
        assert a[column].to_numpy() == pytest.approx(b[column].to_numpy(), abs=0)
    fit_a, fit_b = ebt.valid_windows(a)[0], ebt.valid_windows(b)[0]
    assert ebt.trailing_half_width(fit_a, 1.2) == pytest.approx(ebt.trailing_half_width(fit_b, 1.2), abs=0)


# ---------------------------------------------------------------------------
# loss, the decision statistic, the bootstrap and the rule (tasks 3.1 to 3.3)
# ---------------------------------------------------------------------------


def test_pinball_loss_on_hand_computed_cases():
    losses = ebt.pinball_loss(np.array([1.0, 2.0, 4.0]), np.array([2.0, 2.0, 2.0]))

    assert losses == pytest.approx([0.32, 0.0, 1.36])


def test_pinball_loss_does_not_overwrite_its_inputs():
    moves, widths = np.full(40_000, 4.0), np.full(40_000, 2.0)  # over the 256 KiB elision size

    ebt.pinball_loss(moves, widths)

    assert (moves == 4.0).all() and (widths == 2.0).all()


def test_d_is_one_minus_the_loss_ratio_positive_when_the_har_band_is_better():
    assert ebt.relative_improvement(np.array([0.97]), np.array([1.00])) == pytest.approx(0.03)


def test_identical_bands_give_d_of_zero_and_an_interval_that_includes_zero():
    loss = np.random.default_rng(0).uniform(0.1, 2.0, 600)
    dates = _month_dates(30, 20)

    result = ebt.paired_interval(dates, loss, loss)

    assert result["d"] == 0.0
    assert result["ci"][0] <= 0.0 <= result["ci"][1]


def _month_dates(months: int, per_month: int, start_year: int = 2019) -> np.ndarray:
    labels = [f"{start_year + m // 12}-{m % 12 + 1:02d}-15" for m in range(months)]
    return np.repeat(np.array(labels, dtype=object), per_month)


def test_a_five_percent_lower_loss_in_every_month_gives_an_interval_excluding_zero_near_005():
    rng = np.random.default_rng(1)
    dates = _month_dates(80, 20)
    other = rng.uniform(0.5, 1.5, len(dates))
    har = np.multiply(other, 0.95) * (1 + rng.normal(0, 0.02, len(dates)))

    result = ebt.paired_interval(dates, har, other)

    assert result["ci"][0] > 0.0
    assert result["d"] == pytest.approx(0.05, abs=0.01)
    assert result["ci"][0] < 0.05 < result["ci"][1]


def test_equal_expected_loss_gives_an_interval_that_includes_zero():
    rng = np.random.default_rng(2)
    dates = _month_dates(80, 20)

    result = ebt.paired_interval(dates, rng.uniform(0.5, 1.5, len(dates)), rng.uniform(0.5, 1.5, len(dates)))

    assert result["ci"][0] < 0.0 < result["ci"][1]


def test_the_same_seed_gives_identical_output():
    rng = np.random.default_rng(3)
    dates = _month_dates(70, 10)
    har, other = rng.uniform(0.5, 1.5, 700), rng.uniform(0.5, 1.5, 700)

    assert ebt.paired_interval(dates, har, other) == ebt.paired_interval(dates, har, other)


def test_the_interval_carries_each_months_pair_of_totals_together():
    rng = np.random.default_rng(4)
    months = 80
    dates = _month_dates(months, 10)
    month_level = np.repeat(rng.uniform(0.2, 3.0, months), 10)  # big month-to-month swings, shared by both bands
    other = month_level
    har = np.multiply(month_level, 0.95)

    paired = ebt.paired_interval(dates, har, other)

    totals_h, totals_x = har.reshape(months, 10).sum(axis=1), other.reshape(months, 10).sum(axis=1)
    picks = np.random.default_rng(ebt.SEED).integers(0, months, size=(500, months))
    other_picks = np.random.default_rng(ebt.SEED + 1).integers(0, months, size=(500, months))
    independent = 1 - totals_h[picks].sum(axis=1) / totals_x[other_picks].sum(axis=1)
    assert paired["half_width"] < 1e-9
    assert (np.percentile(independent, 98.75) - np.percentile(independent, 1.25)) / 2 > 0.01


def test_the_quarter_block_interval_runs_on_the_same_windows():
    rng = np.random.default_rng(5)
    dates = _month_dates(72, 10)
    har, other = rng.uniform(0.5, 1.5, 720), rng.uniform(0.5, 1.5, 720)

    month, quarter = ebt.paired_interval(dates, har, other), ebt.paired_interval(dates, har, other, block="quarter")

    assert month["blocks"] == 72 and quarter["blocks"] == 24
    assert month["d"] == quarter["d"]


def test_the_disagreement_flag_is_raised_only_when_the_classifications_differ():
    assert ebt.block_disagreement(ebt.HAR_BETTER, ebt.INCONCLUSIVE) is True
    assert ebt.block_disagreement(ebt.NOT_BETTER, ebt.NOT_BETTER) is False


def _clustered_case():
    """A 3% effect that is steady inside each quarter but varies a lot between quarters: quarter blocks are wider."""
    rng = np.random.default_rng(8)
    quarters, per_month = 24, 20
    effect = np.repeat(rng.normal(0.04, 0.04, quarters), 3)  # one effect per quarter, repeated for its 3 months
    other = np.ones(quarters * 3 * per_month)
    har = np.multiply(other, 1 - np.repeat(effect, per_month))
    return _month_dates(quarters * 3, per_month), har, other


def test_the_flag_is_raised_on_a_constructed_case():
    dates, har, other = _clustered_case()

    result = ebt.compare_bands(dates, har, other, years=7, positive_years=7, har_coverage=0.68, comparator_coverage=0.68)

    assert result["quarter"]["half_width"] > result["month"]["half_width"]
    assert result["outcome"]["outcome"] != result["quarter_outcome"]["outcome"]
    assert result["disagree"] is True


def _outcome(d, ci, **overrides):
    base = {"years": 7, "months": 80, "positive_years": 6, "har_coverage": 0.68, "comparator_coverage": 0.66}
    return ebt.decide_outcome(d, ci, **(base | overrides))


def test_the_har_band_is_materially_better():
    assert _outcome(0.05, (0.03, 0.07))["outcome"] == "HAR_BETTER"


def test_an_interval_that_includes_the_margin_is_inconclusive():
    result = _outcome(0.03, (0.01, 0.05))

    assert result["outcome"] == "INCONCLUSIVE"
    assert any("margin" in text for text in result["reasons"])


def test_a_win_that_is_one_years_is_inconclusive_naming_the_year_condition():
    result = _outcome(0.04, (0.025, 0.055), positive_years=3)

    assert result["outcome"] == "INCONCLUSIVE"
    assert any("year" in text for text in result["reasons"])


def test_no_better_shown_is_not_better():
    assert _outcome(0.004, (-0.006, 0.014))["outcome"] == "NOT_BETTER"


def test_a_better_comparator_is_not_better_with_a_note():
    result = _outcome(-0.05, (-0.08, -0.03))

    assert result["outcome"] == "NOT_BETTER"
    assert any("comparator is the better band" in text for text in result["notes"])


def test_four_test_years_is_inconclusive_naming_the_number_whatever_d_is():
    result = _outcome(0.05, (0.03, 0.07), years=4)

    assert result["outcome"] == "INCONCLUSIVE"
    assert any("4" in text and "year" in text for text in result["reasons"])


def test_fewer_than_60_months_is_inconclusive():
    assert _outcome(0.05, (0.03, 0.07), months=59)["outcome"] == "INCONCLUSIVE"


def test_a_comparator_coverage_of_060_is_inconclusive_naming_the_calibration_guard():
    result = _outcome(0.05, (0.03, 0.07), comparator_coverage=0.60)

    assert result["outcome"] == "INCONCLUSIVE"
    assert any("calibration guard" in text for text in result["reasons"])


def test_the_har_coverage_off_nominal_is_inconclusive_too():
    assert _outcome(0.05, (0.03, 0.07), har_coverage=0.74)["outcome"] == "INCONCLUSIVE"


@pytest.mark.parametrize("d,ci", [(float("nan"), (0.03, 0.07)), (0.05, (float("nan"), 0.07)), (0.05, (0.03, None))])
def test_a_non_finite_figure_is_inconclusive(d, ci):
    assert _outcome(d, ci)["outcome"] == "INCONCLUSIVE"


def test_a_lower_bound_exactly_at_the_margin_is_a_win_and_two_thirds_of_years_is_enough():
    assert _outcome(0.03, (0.02, 0.04), years=6, positive_years=4)["outcome"] == "HAR_BETTER"
    assert _outcome(0.03, (0.02, 0.04), years=6, positive_years=3)["outcome"] == "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# out-of-time scoring (tasks 4.1, 4.2)
# ---------------------------------------------------------------------------

SMALL = 1000  # the synthetic frames have a few thousand windows, not the 40,000 a real fold needs


def test_each_folds_year_window_count_and_har_coverage_equal_the_training_scripts():
    import train_har_rv as train

    frame = _window_frame()

    windows, folds = ebt.score_folds(frame, min_train_rows=SMALL)
    reference = train.run_validation(frame, min_train_rows=SMALL)["folds"]

    assert len(folds) == len(reference) >= 3
    for ours, theirs in zip(folds, reference):
        assert ours["test_year"] == theirs["test_year"]
        assert ours["n"] == theirs["n"] and ours["excluded"] == 0
        assert ours["coverage"]["har"] == pytest.approx(theirs["coverage"], abs=0)
        assert ours["k"] == pytest.approx(theirs["k"], abs=0)
    assert len(windows) == sum(f["n"] for f in folds)


def test_the_windows_keep_date_ticker_move_widths_and_losses():
    windows, folds = ebt.score_folds(_window_frame(), min_train_rows=SMALL)

    for column in ("date", "ticker", "a", "sigma", "rv20_pct", "w_har", "w_trailing", "w_constant", "w_literal",
                   "loss_har", "loss_trailing", "loss_constant", "loss_literal"):
        assert column in windows.columns
    assert set(windows["w_literal"]) == {2.5}
    fold = folds[0]
    in_year = windows[windows["date"].str[:4] == str(fold["test_year"])]
    assert set(in_year["w_constant"]) == {fold["constant"]}
    assert in_year["loss_har"].to_numpy() == pytest.approx(
        ebt.pinball_loss(in_year["a"].to_numpy(), in_year["w_har"].to_numpy()))


def test_a_window_with_zero_rv20_is_left_out_of_every_band_and_counted_in_its_fold():
    frame = _window_frame()
    last_year = frame["date"].str[:4].max()
    zero = frame.index[(frame["date"].str[:4] == last_year)][:4]
    broken = frame.copy()
    broken.loc[zero, "rv20"] = 0.0

    windows, folds = ebt.score_folds(broken, min_train_rows=SMALL)
    clean_windows, clean_folds = ebt.score_folds(frame, min_train_rows=SMALL)

    assert folds[-1]["excluded"] == 4 and folds[-1]["n"] == clean_folds[-1]["n"] - 4
    assert len(windows) == len(clean_windows) - 4
    assert np.isfinite(windows[["w_har", "w_trailing", "w_constant", "loss_har", "loss_trailing"]].to_numpy()).all()


def test_a_window_whose_outcome_date_is_in_the_next_year_is_a_test_window_of_its_start_year_only():
    frame = _window_frame(start="2016-01-01")
    straddling = frame[(frame["date"].str[:4] == "2019") & (frame["outcome_date"].str[:4] == "2020")]
    assert len(straddling) > 0

    fit_2020, _ = ebt.split_fold(frame, 2020)
    _, test_2019 = ebt.split_fold(frame, 2019)
    windows, folds = ebt.score_folds(frame, min_train_rows=SMALL)

    assert not set(straddling.index) & set(fit_2020.index)
    assert set(straddling.index) <= set(test_2019.index)
    assert 2019 in [f["test_year"] for f in folds]
    assert set(straddling["date"]) <= set(windows["date"])


def test_a_fold_needs_enough_purged_prior_windows():
    windows, folds = ebt.score_folds(_window_frame(), min_train_rows=10**9)

    assert folds == [] and windows.empty


def test_k20_and_the_constant_in_a_fold_come_from_its_purged_fit_windows():
    frame = _window_frame()
    windows, folds = ebt.score_folds(frame, min_train_rows=SMALL)
    fold = folds[1]
    fit, _ = ebt.split_fold(frame, fold["test_year"])

    assert fold["k20"] == pytest.approx(ebt.fit_trailing_k(ebt.valid_windows(fit)[0]), abs=0)
    assert fold["constant"] == pytest.approx(ebt.fit_constant(ebt.valid_windows(fit)[0]), abs=0)


# ---------------------------------------------------------------------------
# descriptive metrics (tasks 4.3, 4.4)
# ---------------------------------------------------------------------------


def _scored(n_tickers: int = 4):
    windows, folds = ebt.score_folds(_window_frame(n_tickers=n_tickers), min_train_rows=SMALL)
    return windows, folds


def test_coverage_by_sigma_quintile_uses_the_pooled_sigma_for_every_band_and_the_trailing_band_by_its_own_rv20():
    windows, _ = _scored()

    table = ebt.quintile_coverage(windows)

    assert [row["quintile"] for row in table["by_sigma"]] == [1, 2, 3, 4, 5]
    assert sum(row["n"] for row in table["by_sigma"]) == len(windows)
    first = windows["sigma"] <= windows["sigma"].quantile(0.2)
    assert table["by_sigma"][0]["har"] == pytest.approx(windows.loc[first, "hit_har"].mean(), abs=2e-3)
    assert set(table["by_sigma"][0]) >= {"har", "trailing", "constant", "literal"}
    assert [row["quintile"] for row in table["trailing_by_rv20"]] == [1, 2, 3, 4, 5]
    assert set(table["trailing_by_rv20"][0]) == {"quintile", "n", "trailing"}


def test_the_oracle_width_is_rescaled_to_exactly_068_coverage_on_the_test_windows():
    rng = np.random.default_rng(6)
    moves, widths = rng.uniform(0.1, 6.0, 5000), rng.uniform(1.0, 3.0, 5000)

    oracle = ebt.oracle_mean_width(moves, widths)

    scale = oracle / widths.mean()
    assert np.mean(moves <= np.multiply(widths, scale)) == pytest.approx(0.68, abs=2e-3)


def test_the_sharpness_table_has_fitted_and_oracle_widths_as_ratios_to_the_har_band():
    windows, _ = _scored()

    table = ebt.sharpness_table(windows)

    assert table["har"]["ratio_fitted"] == 1.0 and table["har"]["ratio_oracle"] == 1.0
    assert table["trailing"]["ratio_fitted"] == pytest.approx(
        windows["w_trailing"].mean() / windows["w_har"].mean())
    assert table["constant"]["oracle_width"] > 0 and table["literal"]["fitted_width"] == 2.5


def test_spearman_matches_a_direct_rank_computation_and_is_undefined_for_a_constant_width():
    width = np.array([3.0, 1.0, 2.0, 5.0, 4.0, 4.0])
    move = np.array([10.0, 30.0, 20.0, 50.0, 40.0, 5.0])
    rank = lambda v: np.array([np.mean([j + 1 for j, w in enumerate(np.sort(v)) if w == x]) for x in v])  # noqa: E731
    expected = np.corrcoef(rank(width), rank(move))[0, 1]

    assert ebt.spearman(width, move) == pytest.approx(expected, abs=1e-12)
    assert ebt.spearman(np.full(6, 2.5), move) is None


def test_each_fold_carries_its_rank_correlations_and_the_constant_one_is_undefined():
    windows, folds = _scored()

    for fold in folds:
        assert fold["spearman"]["har"] is not None and fold["spearman"]["trailing"] is not None
        assert fold["spearman"]["constant"] is None
    first = folds[0]
    test = windows[windows["date"].str[:4] == str(first["test_year"])]
    assert first["spearman"]["har"] == pytest.approx(ebt.spearman(test["w_har"].to_numpy(), test["a"].to_numpy()))
    assert ebt.mean_rank_correlations(folds)["constant"] is None
    assert ebt.mean_rank_correlations(folds)["har"] == pytest.approx(np.mean([f["spearman"]["har"] for f in folds]))


def test_d_by_year_matches_the_pooled_loss_within_each_year():
    windows, folds = _scored()

    table = ebt.by_year_table(windows)

    assert [row["year"] for row in table] == [f["test_year"] for f in folds]
    row = table[0]
    year = windows[windows["date"].str[:4] == str(row["year"])]
    assert row["d_trailing"] == pytest.approx(ebt.relative_improvement(year["loss_har"], year["loss_trailing"]))
    assert row["d_constant"] == pytest.approx(ebt.relative_improvement(year["loss_har"], year["loss_constant"]))
    assert row["n"] == len(year) and 0.0 <= row["coverage"]["har"] <= 1.0


def _ticker_windows() -> pd.DataFrame:
    """Four tickers: SAB and AAA with 300 windows, VPB with 100, VIB absent."""
    rng = np.random.default_rng(12)
    parts = []
    for ticker, n, edge in (("SAB", 300, -0.1), ("AAA", 300, 0.1), ("BBB", 300, 0.1), ("VPB", 100, 0.1)):
        other = rng.uniform(0.5, 1.5, n)
        har = np.multiply(other, 1 - edge)
        hit = rng.uniform(size=n) < 0.7
        parts.append(pd.DataFrame({"ticker": ticker, "date": _month_dates(n // 10, 10)[:n], "loss_har": har,
                                   "loss_trailing": other, "loss_constant": other,
                                   **{f"hit_{b}": hit for b in ("har", "trailing", "constant", "literal")}}))
    return pd.concat(parts, ignore_index=True)


def test_per_ticker_leaves_out_tickers_under_250_windows_and_reports_the_distribution():
    result = ebt.per_ticker(_ticker_windows())

    trailing = result["distribution"]["trailing"]
    assert trailing["tickers"] == 3  # VPB has 100 windows
    assert trailing["share_har_better"] == pytest.approx(2 / 3)
    assert trailing["p10"] <= trailing["median"] <= trailing["p90"]
    assert trailing["equal_weighted_mean"] == pytest.approx(np.mean([-0.1, 0.1, 0.1]), abs=0.03)


def test_the_named_tickers_are_always_printed_and_an_absent_one_is_reported_absent():
    result = ebt.per_ticker(_ticker_windows())

    assert set(result["named"]) == {"SAB", "VPB", "VIB"}
    assert result["named"]["VIB"] == {"present": False}
    assert result["named"]["VPB"]["windows"] == 100  # printed although it is under 250 windows
    assert 0.0 <= result["named"]["SAB"]["coverage"]["har"] <= 1.0


def test_a_named_ticker_pointing_against_the_pooled_result_is_flagged_and_changes_no_outcome():
    windows = _ticker_windows()
    result = ebt.per_ticker(windows)

    assert result["named"]["SAB"]["against_pooled"]["trailing"] is True  # SAB's D is negative, pooled is positive
    assert result["named"]["VPB"]["against_pooled"]["trailing"] is False


def test_the_ticker_equal_weighted_mean_flags_a_sign_that_differs_from_the_pooled_one():
    parts = []
    for ticker, scale, factor in (("BIG", 100.0, 0.90), ("S1", 1.0, 1.05), ("S2", 1.0, 1.05), ("S3", 1.0, 1.05)):
        other = np.full(300, scale)
        hits = {f"hit_{b}": np.ones(300, dtype=bool) for b in ("har", "trailing", "constant", "literal")}
        parts.append(pd.DataFrame({"ticker": ticker, "date": _month_dates(30, 10),
                                   "loss_har": np.multiply(other, factor),
                                   "loss_trailing": other, "loss_constant": other, **hits}))

    result = ebt.per_ticker(pd.concat(parts, ignore_index=True))["distribution"]["trailing"]

    assert result["pooled"] > 0 > result["equal_weighted_mean"]
    assert result["sign_differs"] is True


# ---------------------------------------------------------------------------
# the assembled read-only script and its report (tasks 5.1, 5.2)
# ---------------------------------------------------------------------------

SYMBOLS = ("AAA", "BBB", "CCC", "SAB")


def _make_db(path: Path, symbols=SYMBOLS, n_rows: int = 2000) -> None:
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


@pytest.fixture
def study_db(tmp_path, monkeypatch):
    monkeypatch.setattr(ebt, "MIN_TRAIN_ROWS", 500)  # the synthetic database is far smaller than a real one
    path = tmp_path / "db" / "app.db"
    path.parent.mkdir()
    _make_db(path)
    return path


def test_the_study_leaves_the_database_bytes_unchanged_and_its_connection_cannot_write(study_db, monkeypatch):
    import hashlib
    import sqlite3

    before = hashlib.sha256(study_db.read_bytes()).hexdigest()
    siblings = sorted(p.name for p in study_db.parent.iterdir())
    write_attempts = []
    real_open = ebt.open_readonly

    def spying_open(path):
        conn = real_open(path)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("INSERT INTO ohlcv VALUES ('ZZZ', '2020-01-01', 1, 1, 1, 1, 1)")
        write_attempts.append(conn)
        return conn

    monkeypatch.setattr(ebt, "open_readonly", spying_open)

    report = ebt.run(study_db)

    assert write_attempts, "the script never opened the database through open_readonly"
    assert hashlib.sha256(study_db.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in study_db.parent.iterdir()) == siblings  # no journal, no model file
    assert report["comparisons"]["trailing"]["outcome"]["outcome"] in (ebt.HAR_BETTER, ebt.NOT_BETTER, ebt.INCONCLUSIVE)


def test_no_file_is_created_without_json(study_db, tmp_path, monkeypatch, capsys):
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    before = sorted(p.name for p in tmp_path.rglob("*"))

    ebt.main(["--db", str(study_db)])

    assert sorted(p.name for p in tmp_path.rglob("*")) == before
    assert capsys.readouterr().out


def test_json_is_written_only_when_asked_and_carries_both_outcomes(study_db, tmp_path, capsys):
    import json

    target = tmp_path / "out" / "report.json"

    ebt.main(["--db", str(study_db), "--json", str(target)])

    report = json.loads(target.read_text())
    assert set(report["comparisons"]) == {"trailing", "constant"}
    assert report["comparisons"]["trailing"]["outcome"]["outcome"] in ("HAR_BETTER", "NOT_BETTER", "INCONCLUSIVE")


def test_the_first_output_line_says_study_output_not_shown_to_users_not_advice(study_db, capsys):
    ebt.main(["--db", str(study_db)])

    first = capsys.readouterr().out.splitlines()[0]
    assert "STUDY OUTPUT" in first and "not shown to any user" in first and "not investment advice" in first


def test_the_script_imports_no_vendor_package_itself_and_a_run_makes_no_network_call(study_db, tmp_path):
    """`modelling_universe` pulls vnstock in transitively (behind the guard); the script itself imports none."""
    import ast
    import os
    import subprocess

    script = BACKEND / "scripts" / "evaluate_band_against_trailing_stdev.py"
    imported = set()
    for node in ast.walk(ast.parse(script.read_text())):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            imported.add(node.module.split(".")[0])
    assert not imported & {"vnstock", "vnai", "requests", "httpx", "urllib3", "socket", "urllib"}

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    code = (
        "import importlib.util, pathlib, socket, sys\n"
        "def refuse(*a, **k): raise AssertionError('network call')\n"
        "socket.socket.connect = refuse; socket.getaddrinfo = refuse; socket.create_connection = refuse\n"
        f"spec = importlib.util.spec_from_file_location('ebt', {str(script)!r})\n"
        "m = importlib.util.module_from_spec(spec); sys.modules['ebt'] = m; spec.loader.exec_module(m)\n"
        "m.MIN_TRAIN_ROWS = 500\n"
        f"m.run(pathlib.Path({str(study_db)!r}))\n"
    )
    process_vars = {"PATH": os.getenv("PATH", ""), "HOME": str(sandbox)}
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=300,
                          cwd=sandbox, env=process_vars)

    assert done.returncode == 0, done.stderr
    assert list(sandbox.iterdir()) == []  # the vendor's config-file writers stayed neutralised


def test_the_modelling_universe_is_read_at_run_time(study_db):
    import sqlite3

    full = ebt.run(study_db)
    conn = sqlite3.connect(study_db)
    conn.execute("UPDATE ticker_universe SET fails_liquidity_filter = 1 WHERE symbol = 'CCC'")
    conn.commit()
    conn.close()

    fewer = ebt.run(study_db)

    assert full["universe"]["symbols"] == 4 and fewer["universe"]["symbols"] == 3


def test_a_database_with_no_evaluable_fold_is_refused_with_a_named_error(study_db, monkeypatch):
    monkeypatch.setattr(ebt, "MIN_TRAIN_ROWS", 10**9)

    with pytest.raises(ValueError, match="no evaluated fold"):
        ebt.run(study_db)


@pytest.fixture
def report(study_db):
    return ebt.run(study_db)


def test_the_report_carries_counts_exclusions_months_pooled_coverage_and_the_last_date(report):
    assert report["universe"]["last_date"].startswith("20")
    assert report["counts"]["windows"] == sum(f["n"] for f in report["folds"])
    assert report["counts"]["months"] >= 12 and report["counts"]["excluded_frame"] == 0
    for band in ebt.BANDS:
        assert set(report["pooled"][band]) >= {"coverage", "ci", "mean_width"}
    assert report["reference"]["recorded"] == {"har": 0.431, "log_rv20": 0.424}


def test_the_report_prints_the_two_outcomes_the_consequences_and_the_does_not_show_paragraph(report):
    text = ebt.format_report(report)

    assert text.splitlines()[0] == ebt.HEADER
    assert text.count("OUTCOME against the trailing band:") == 1
    assert text.count("OUTCOME against the fitted constant band:") == 1
    assert any(label in text for label in ("HAR_BETTER", "NOT_BETTER", "INCONCLUSIVE"))
    assert "What this result does not show" in text and "says nothing about direction" in text
    assert "not a guarantee" in text and "does not show whether the weekly brief is useful" in text
    assert "month-block" in text and "quarter-block" in text and "distinct test months" in text


def test_the_report_labels_descriptive_oracle_and_recorded_figures(report):
    text = ebt.format_report(report)

    assert "DESCRIPTIVE" in text and "ORACLE" in text and "uses test outcomes" in text
    assert "undefined" in text  # the constant band's rank correlation
    assert [line for line in text.splitlines() if "0.431" in line and "recorded in an archived design" in line]
    for name in ("SAB", "VPB", "VIB"):
        assert name in text
    assert "not an inference sample" in text
    assert "Confidence" not in text


def test_the_outcome_names_carry_no_instruction_and_no_debate_label(report):
    text = ebt.format_report(report).lower()

    import re

    for word in ("buy", "sell", "hold", "bullish", "bearish", "agreement"):
        assert not re.search(rf"\b{word}\b", text), word


def test_each_outcome_states_its_fixed_consequence_and_the_constant_band_one_names_rule_3():
    for comparator, outcome, phrases in (
        ("trailing", ebt.HAR_BETTER, ("served band is kept", "MODEL_CARD")),
        ("trailing", ebt.NOT_BETTER, ("follow-up change", "not stopped")),
        ("trailing", ebt.INCONCLUSIVE, ("not evidence that the bands are equal", "served band stays")),
        ("constant", ebt.HAR_BETTER, ("per-ticker scaling earns its place",)),
        ("constant", ebt.NOT_BETTER, ("decision for the owner", "Rule 3", "no action is taken")),
        ("constant", ebt.INCONCLUSIVE, ("not evidence that the bands are equal",)),
    ):
        text = ebt.consequence(comparator, outcome)
        assert all(p in text for p in phrases), (comparator, outcome, text)


def test_a_har_better_outcome_says_the_finding_is_about_move_size_not_direction_or_a_guarantee():
    text = ebt.consequence("trailing", ebt.HAR_BETTER)

    assert "size of moves" in text and "not a guarantee" in text


def test_the_check_the_evaluator_note_is_printed_when_the_trailing_band_does_not_beat_the_constant_band(report):
    flagged = report | {"trailing_vs_constant": {"d": -0.01, "check_evaluator": True}}
    clear = report | {"trailing_vs_constant": {"d": 0.05, "check_evaluator": False}}

    assert "check the rv20 handling and the evaluator" in ebt.format_report(flagged)
    assert "check the rv20 handling and the evaluator" not in ebt.format_report(clear)


def test_the_check_flag_follows_the_losses(report):
    expected = report["trailing_vs_constant"]["d"] <= 0
    assert report["trailing_vs_constant"]["check_evaluator"] is expected


def test_the_same_database_gives_identical_figures_twice(study_db):
    assert ebt.run(study_db) == ebt.run(study_db)


def test_folds_over_the_numpy_elision_size_match_the_training_script_and_a_direct_computation():
    """NumPy 2.2.6 on Python 3.14 can overwrite a local array in `scalar * array` above 32,768 elements."""
    import train_har_rv as train

    frame = _window_frame(n_tickers=150, n_rows=900, seed=21)
    folds_ref = train.run_validation(frame, min_train_rows=20_000)["folds"]

    windows, folds = ebt.score_folds(frame, min_train_rows=20_000)

    assert len(folds) == len(folds_ref) >= 1
    assert max(f["n"] for f in folds) > 32_768
    last = folds[-1]
    fit, test = ebt.split_fold(frame, last["test_year"])
    year = windows[windows["date"].str[:4] == str(last["test_year"])]
    ratio = fit["abs_r5_pct"].to_numpy() / (np.sqrt(5) * fit["rv20"].to_numpy() * 100)
    direct_trailing = float(np.mean(test["abs_r5_pct"].to_numpy() <= np.quantile(ratio, 0.68) * np.sqrt(5)
                                    * test["rv20"].to_numpy() * 100))
    assert last["coverage"]["har"] == pytest.approx(folds_ref[-1]["coverage"], abs=0)
    assert last["coverage"]["trailing"] == pytest.approx(direct_trailing, abs=0)
    assert year["w_trailing"].to_numpy() == pytest.approx(
        np.quantile(ratio, 0.68) * np.sqrt(5) * test["rv20"].to_numpy() * 100, rel=1e-12)
