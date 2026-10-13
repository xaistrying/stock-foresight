"""Is the served HAR-RV band better than a trailing 20-session-stdev band, or than a constant band?

STUDY OUTPUT, not shown to any user. READ-ONLY over `backend/data/app.db` (mode=ro): it writes no
table and no model file, makes no network call and imports no vendor package. Its only possible
write is the report named by `--json`.

The question (openspec change evaluate-band-against-trailing-stdev, design.md; row E1 of the
weekly-brief discussion): the served band is `range_k x sqrt(5) x sigma_daily_pct(t)`. Scored out of
time against the realised 5-session move |ln(close[t+5]/close[t])| with the pinball loss at 0.68, is
it materially better than (a) `k20 x sqrt(5) x rv20(t)`, with its own multiplier fitted on the same
folds, and (b) a constant band fitted to the same nominal coverage? The folds are the expanding
walk-forward by calendar year of `train_har_rv.py` (imported, not re-implemented). The outcome per
comparator is HAR_BETTER, NOT_BETTER or INCONCLUSIVE by the rule in the spec, applied by code below.

Rules honoured unchanged. Rule 1: the outcome is `build_window_frame`'s 5-session r5 (a session is
one stored OHLCV row). Rule 2: every printed rate is a percentage. Rule 3: the trailing band is
volatility-relative; the constant bands are reference comparators in a developer printout and
classify no move for any user. Rule 4: no reliability figure reaches an API, the UI or an export,
and none is called Confidence. Rules 5 and 6: no verdict, Agreement or model text is produced, and
the output is a technical observation, not investment advice.

Run from the project root:
    python backend/scripts/evaluate_band_against_trailing_stdev.py [--db PATH] [--json OUT.json]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # backend/, for `app`
sys.path.insert(0, str(HERE))  # scripts/, for the sibling `train_har_rv`

from app.db.connection import DB_PATH, open_readonly  # noqa: E402
from app.ml.volatility import FEATURE_NAMES, scaled_band, sigma_pct  # noqa: E402
from app.services.ticker_universe import modelling_universe  # noqa: E402
from train_har_rv import (  # noqa: E402
    MIN_TRAIN_ROWS,
    RANGE_COVERAGE,
    fit_fold,
    load_frame,
    run_validation,
    split_fold,
)

# ---------------------------------------------------------------------------
# The criterion. These constants are NEW, PROVISIONAL and covered by no domain rule: none is a
# threshold on the size of a price move (Rule 3 is not engaged). They are fixed in
# specs/band-baseline-comparison/spec.md and here BEFORE any real run; changing one after a result
# has been seen is a new change, not an edit.
# ---------------------------------------------------------------------------
MARGIN = 0.02  # M: the smallest relative loss reduction that counts as material (owner, 2026-10-12)
CONFIDENCE = 0.975  # per comparison, month-block percentile interval (two comparisons, about 95% for the pair)
BOOTSTRAP_RESAMPLES = 2000
SEED = 0
CALIBRATION_GUARD = 0.05  # pooled out-of-time coverage further than this from nominal makes it INCONCLUSIVE
MIN_YEARS = 5  # evaluated test years
MIN_MONTHS = 60  # distinct calendar test months
YEAR_CONSISTENCY = 2 / 3  # share of test years in which D must be positive
NOMINAL_COVERAGE = RANGE_COVERAGE  # 0.68
TRAILING_WINDOW = 20  # sessions behind rv20, the window frame's own column; never varied
LITERAL_BAND = 2.5  # half-width of the literal constant band, in |r5| x 100 units; descriptive only
# Descriptive-only settings (no outcome depends on them).
DESCRIPTIVE_CONFIDENCE = 0.95
MIN_TICKER_WINDOWS = 250
NAMED_TICKERS = ("SAB", "VPB", "VIB")
QUINTILES = 5
RECORDED_CORRELATIONS = (0.431, 0.424)  # archived calibrate-volatility-range design; a reference, not a result
HAR_BETTER, NOT_BETTER, INCONCLUSIVE = "HAR_BETTER", "NOT_BETTER", "INCONCLUSIVE"
COMPARATORS = ("trailing", "constant")  # the two confirmatory comparisons; the literal band is descriptive

HEADER = (
    "STUDY OUTPUT, not shown to any user (Rule 4); a technical observation, not investment advice (Rule 6)."
)


# ---------------------------------------------------------------------------
# The bands (design Decisions 2 and 3). Every half-width is in percent of |r5| x 100.
# ---------------------------------------------------------------------------
def valid_windows(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Windows with a positive, finite rv20, and how many were left out (they are out for every band)."""
    rv20 = frame["rv20"].to_numpy(dtype=float)
    keep = np.isfinite(rv20) & (rv20 > 0)
    return frame[keep], int((~keep).sum())


def trailing_half_width(frame: pd.DataFrame, k20: float) -> np.ndarray:
    """k20 x sqrt(5) x rv20(t) x 100: rv20 is the std of the last 20 daily log returns up to and including t."""
    return scaled_band(np.multiply(frame["rv20"].to_numpy(dtype=float), 100.0), k20)


def fit_trailing_k(fit: pd.DataFrame, coverage: float = NOMINAL_COVERAGE) -> float:
    """The `coverage`-quantile of |r5| x 100 / (sqrt(5) x rv20 x 100) over `fit` (the served band's own estimator)."""
    return float(np.quantile(np.divide(fit["abs_r5_pct"].to_numpy(), trailing_half_width(fit, 1.0)), coverage))


def fit_constant(fit: pd.DataFrame, coverage: float = NOMINAL_COVERAGE) -> float:
    """The `coverage`-quantile of |r5| x 100 over `fit`: the unscaled version of the same estimator."""
    return float(np.quantile(fit["abs_r5_pct"].to_numpy(), coverage))


def constant_half_width(frame: pd.DataFrame, half_width: float) -> np.ndarray:
    return np.full(len(frame), float(half_width))


# ---------------------------------------------------------------------------
# Loss, the decision statistic and the paired block bootstrap (design Decisions 4 and 6)
# ---------------------------------------------------------------------------
def pinball_loss(moves: np.ndarray, half_widths: np.ndarray, tau: float = NOMINAL_COVERAGE) -> np.ndarray:
    """tau (a - w) when a >= w, else (1 - tau)(w - a), with a = |r5| x 100 and w the half-width (points)."""
    gap = np.subtract(moves, half_widths)
    return np.where(gap >= 0, np.multiply(gap, tau), np.multiply(np.negative(gap), 1 - tau))


def relative_improvement(loss_har: np.ndarray, loss_other: np.ndarray) -> float:
    """D = 1 - L_HAR / L_X over the pooled windows; positive means the HAR band scored better."""
    return float(1 - np.mean(loss_har) / np.mean(loss_other))


def _block_key(dates, block: str) -> pd.Series:
    keys = pd.Series(np.asarray(dates, dtype=object))
    if block == "month":
        return keys.str[:7]
    if block == "quarter":
        return keys.str[:4] + "Q" + ((keys.str[5:7].astype(int) - 1) // 3 + 1).astype(str)
    raise ValueError(f"unknown block {block!r}")


def _block_totals(dates, *values: np.ndarray, block: str = "month") -> list[np.ndarray]:
    """Each array's sum per calendar block (month or quarter), over every block that has a window."""
    codes, blocks = pd.factorize(_block_key(dates, block), sort=True)
    return [np.bincount(codes, weights=np.asarray(v, dtype=float), minlength=len(blocks)) for v in values]


def _ratio_draws(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Sum(num) / sum(den) over blocks resampled with replacement, the same blocks for both arrays."""
    picks = np.random.default_rng(SEED).integers(0, len(numerator), size=(BOOTSTRAP_RESAMPLES, len(numerator)))
    return np.divide(numerator[picks].sum(axis=1), denominator[picks].sum(axis=1))


def _percentile_ci(draws: np.ndarray, level: float) -> tuple[float, float] | tuple[None, None]:
    draws = draws[np.isfinite(draws)]
    if len(draws) == 0:
        return (None, None)
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(draws, [tail, 100 - tail])
    return float(low), float(high)


def _interval(point: float, draws: np.ndarray, blocks: int, level: float) -> dict:
    ci = _percentile_ci(draws, level)
    return {
        "d": point, "ci": ci, "blocks": blocks, "level": level,
        "half_width": None if ci[0] is None else (ci[1] - ci[0]) / 2,
    }


def paired_interval(dates, loss_har, loss_other, block: str = "month", level: float = CONFIDENCE) -> dict:
    """D with a percentile interval from resampling whole blocks, each block's pair of totals moving together."""
    har, other = _block_totals(dates, loss_har, loss_other, block=block)
    point = float(1 - har.sum() / other.sum())
    return _interval(point, 1 - _ratio_draws(har, other), len(har), level)


def coverage_interval(dates, hit, block: str = "month", level: float = DESCRIPTIVE_CONFIDENCE) -> dict:
    """Pooled coverage (field `d` is the share) with the same month-block form; descriptive only."""
    hits, counts = _block_totals(dates, np.asarray(hit, dtype=float), np.ones(len(hit)), block=block)
    return _interval(float(hits.sum() / counts.sum()), _ratio_draws(hits, counts), len(hits), level)


def block_disagreement(month_outcome: str, quarter_outcome: str) -> bool:
    """Whether the month-block and quarter-block intervals classify differently (printed; changes no outcome)."""
    return month_outcome != quarter_outcome


# ---------------------------------------------------------------------------
# The decision rule (spec: "The decision rule and constants are fixed in the spec before any result")
# ---------------------------------------------------------------------------
def _finite(*values) -> bool:
    return all(v is not None and math.isfinite(v) for v in values)


def decide_outcome(
    d: float, ci: tuple, *, years: int, months: int, positive_years: int,
    har_coverage: float, comparator_coverage: float,
) -> dict:
    """HAR_BETTER, NOT_BETTER or INCONCLUSIVE for one comparator, with reasons and notes."""
    reasons: list[str] = []
    if years < MIN_YEARS:
        reasons.append(f"only {years} evaluated test years (at least {MIN_YEARS} are needed)")
    if months < MIN_MONTHS:
        reasons.append(f"only {months} distinct test months (at least {MIN_MONTHS} are needed)")
    if not _finite(har_coverage, comparator_coverage):
        reasons.append("a pooled coverage is not finite")
    else:
        for name, coverage in (("HAR band", har_coverage), ("comparator", comparator_coverage)):
            if abs(coverage - NOMINAL_COVERAGE) > CALIBRATION_GUARD:
                reasons.append(
                    f"calibration guard: the {name} pooled out-of-time coverage {coverage * 100:.1f}% is "
                    f"further than {CALIBRATION_GUARD * 100:.0f} points from {NOMINAL_COVERAGE * 100:.0f}%"
                )
    if not _finite(d, *ci):
        reasons.append("a figure is not finite")
    if reasons:
        return {"outcome": INCONCLUSIVE, "reasons": reasons, "notes": []}

    low, high = ci
    consistent = positive_years >= YEAR_CONSISTENCY * years - 1e-9
    if low >= MARGIN:
        if consistent:
            return {"outcome": HAR_BETTER, "reasons": [
                f"the interval's lower end {low * 100:+.1f}% is at or above the margin {MARGIN * 100:.0f}%, "
                f"and D is positive in {positive_years} of {years} test years"], "notes": []}
        return {"outcome": INCONCLUSIVE, "reasons": [
            f"the interval's lower end is at or above the margin, but D is positive in only {positive_years} "
            f"of {years} test years (year condition: at least two thirds)"], "notes": []}
    if high < MARGIN:
        notes = []
        if high < -MARGIN:
            notes.append("the comparator is the better band: the whole interval is below the negative margin")
        return {"outcome": NOT_BETTER, "reasons": [
            f"the interval's upper end {high * 100:+.1f}% is below the margin {MARGIN * 100:.0f}%: a benefit "
            "as large as the margin is ruled out at this level"], "notes": notes}
    return {"outcome": INCONCLUSIVE, "reasons": [
        f"the interval includes the margin {MARGIN * 100:.0f}%: a material benefit is neither shown nor excluded"],
        "notes": []}


def compare_bands(
    dates, loss_har, loss_other, *, years: int, positive_years: int, har_coverage: float, comparator_coverage: float
) -> dict:
    """D, both block intervals, the outcome (month blocks decide) and the quarter-block cross-check."""
    month = paired_interval(dates, loss_har, loss_other)
    quarter = paired_interval(dates, loss_har, loss_other, block="quarter")
    common = {"years": years, "positive_years": positive_years, "har_coverage": har_coverage,
              "comparator_coverage": comparator_coverage}
    months = int(_block_key(dates, "month").nunique())
    outcome = decide_outcome(month["d"], month["ci"], months=months, **common)
    quarter_outcome = decide_outcome(quarter["d"], quarter["ci"], months=months, **common)
    return {
        "d": month["d"], "month": month, "quarter": quarter, "months": months,
        "outcome": outcome, "quarter_outcome": quarter_outcome,
        "disagree": block_disagreement(outcome["outcome"], quarter_outcome["outcome"]),
    }


# ---------------------------------------------------------------------------
# Out-of-time scoring with the training script's folds (design Decision 3)
# ---------------------------------------------------------------------------
BANDS = ("har", "trailing", "constant", "literal")
BAND_COLUMNS = {band: f"w_{band}" for band in BANDS}


def spearman(width: np.ndarray, move: np.ndarray) -> float | None:
    """Rank correlation of band width with the realised move; None when the width does not vary."""
    width_rank, move_rank = pd.Series(width).rank().to_numpy(), pd.Series(move).rank().to_numpy()
    if np.ptp(width_rank) == 0 or np.ptp(move_rank) == 0:
        return None
    return float(np.corrcoef(width_rank, move_rank)[0, 1])


def _fold_windows(test: pd.DataFrame, widths: dict[str, np.ndarray]) -> pd.DataFrame:
    moves = test["abs_r5_pct"].to_numpy(dtype=float)
    columns = {
        "date": test["date"].to_numpy(), "ticker": test["ticker"].to_numpy(), "a": moves,
        "rv20_pct": np.multiply(test["rv20"].to_numpy(dtype=float), 100.0),
    }
    for band, width in widths.items():
        columns[BAND_COLUMNS[band]] = width
        columns[f"hit_{band}"] = moves <= width
        columns[f"loss_{band}"] = pinball_loss(moves, width)
    return pd.DataFrame(columns)


def score_folds(
    frame: pd.DataFrame, min_train_rows: int | None = None, coverage: float = NOMINAL_COVERAGE
) -> tuple[pd.DataFrame, list[dict]]:
    """Every out-of-time test window with its four half-widths, hits and losses, and one summary per fold.

    The folds are `train_har_rv.run_validation`'s: expanding by calendar year, the HAR coefficients and
    `range_k` fitted by `fit_fold` on windows whose OUTCOME date precedes the test year. `k20` and the fitted
    constant are fitted on the same fit windows with a positive rv20; windows without one are left out of
    scoring for every band.
    """
    min_train_rows = MIN_TRAIN_ROWS if min_train_rows is None else min_train_rows  # read at call time
    pieces, folds = [], []
    for year in sorted(int(y) for y in frame["date"].str[:4].unique()):
        fit, test = split_fold(frame, year)
        if len(fit) < min_train_rows or test.empty:
            continue
        intercept, coef, range_k = fit_fold(fit, coverage)
        fit_valid, _ = valid_windows(fit)
        test_valid, excluded = valid_windows(test)
        if fit_valid.empty or test_valid.empty:
            continue
        k20, constant = fit_trailing_k(fit_valid, coverage), fit_constant(fit_valid, coverage)
        sigma = sigma_pct(test_valid[list(FEATURE_NAMES)].to_numpy(), intercept, coef)
        widths = {
            "har": scaled_band(sigma, range_k),
            "trailing": trailing_half_width(test_valid, k20),
            "constant": constant_half_width(test_valid, constant),
            "literal": constant_half_width(test_valid, LITERAL_BAND),
        }
        piece = _fold_windows(test_valid, widths).assign(sigma=sigma)
        pieces.append(piece)
        folds.append({
            "test_year": year, "n": int(len(test_valid)), "excluded": excluded, "k": range_k, "k20": k20,
            "constant": constant, "coverage": {band: float(piece[f"hit_{band}"].mean()) for band in BANDS},
            "spearman": {band: spearman(widths[band], piece["a"].to_numpy()) for band in BANDS[:3]},
        })
    if not pieces:
        return pd.DataFrame(columns=["date", "ticker", "a", "sigma", "rv20_pct"]), []
    return pd.concat(pieces, ignore_index=True), folds


# ---------------------------------------------------------------------------
# Descriptive metrics: none of these enters an outcome (design Decision 7)
# ---------------------------------------------------------------------------
def mean_rank_correlations(folds: list[dict]) -> dict[str, float | None]:
    """Mean over folds, as `run_validation` averages its correlations; None where a fold has none."""
    result = {}
    for band in BANDS[:3]:
        values = [fold["spearman"][band] for fold in folds]
        result[band] = None if not values or any(v is None for v in values) else float(np.mean(values))
    return result


def quintile_coverage(windows: pd.DataFrame) -> dict:
    """Coverage by quintile of the served model's sigma (all bands), and of rv20 (the trailing band)."""
    def table(column: str, bands: tuple[str, ...]) -> list[dict]:
        quintile = pd.qcut(windows[column], QUINTILES, labels=False, duplicates="drop").to_numpy()
        hits = windows[[f"hit_{band}" for band in bands]].assign(_q=quintile).groupby("_q")
        rates, counts = hits.mean(), hits.size()
        return [
            {"quintile": int(q) + 1, "n": int(counts.loc[q]),
             **{band: float(rates.loc[q, f"hit_{band}"]) for band in bands}}
            for q in rates.index
        ]

    return {"by_sigma": table("sigma", BANDS), "trailing_by_rv20": table("rv20_pct", ("trailing",))}


def oracle_mean_width(moves: np.ndarray, widths: np.ndarray, coverage: float = NOMINAL_COVERAGE) -> float:
    """Mean width after one rescale so the test windows' coverage is exactly `coverage`. Uses test outcomes."""
    scale = float(np.quantile(np.divide(moves, widths), coverage))
    return float(np.mean(widths) * scale)


def sharpness_table(windows: pd.DataFrame) -> dict[str, dict]:
    """Mean half-width as fitted and oracle-rescaled to 68% coverage, each also as a ratio to the HAR band's."""
    moves = windows["a"].to_numpy()
    fitted = {band: float(windows[BAND_COLUMNS[band]].mean()) for band in BANDS}
    oracle = {band: oracle_mean_width(moves, windows[BAND_COLUMNS[band]].to_numpy()) for band in BANDS}
    return {
        band: {
            "fitted_width": fitted[band], "ratio_fitted": fitted[band] / fitted["har"],
            "oracle_width": oracle[band], "ratio_oracle": oracle[band] / oracle["har"],
        }
        for band in BANDS
    }


def _d(frame: pd.DataFrame, comparator: str) -> float:
    return relative_improvement(frame["loss_har"].to_numpy(), frame[f"loss_{comparator}"].to_numpy())


def by_year_table(windows: pd.DataFrame) -> list[dict]:
    """Per calendar test year: windows, each band's coverage and D against both comparators."""
    rows = []
    for year, frame in windows.groupby(windows["date"].str[:4]):
        rows.append({
            "year": int(year), "n": int(len(frame)),
            "coverage": {band: float(frame[f"hit_{band}"].mean()) for band in BANDS},
            "d_trailing": _d(frame, "trailing"), "d_constant": _d(frame, "constant"),
        })
    return rows


def per_ticker(windows: pd.DataFrame) -> dict:
    """D per ticker (those with enough windows) and the three named tickers; descriptive, anecdote not inference."""
    pooled = {c: _d(windows, c) for c in COMPARATORS}
    by_ticker = {ticker: frame for ticker, frame in windows.groupby("ticker") if len(frame) >= MIN_TICKER_WINDOWS}
    distribution = {}
    for comparator in COMPARATORS:
        values = np.array([_d(frame, comparator) for frame in by_ticker.values()])
        if len(values) == 0:
            distribution[comparator] = {"tickers": 0, "pooled": pooled[comparator]}
            continue
        p10, median, p90 = np.percentile(values, [10, 50, 90])
        mean = float(values.mean())
        distribution[comparator] = {
            "tickers": int(len(values)), "median": float(median), "p10": float(p10), "p90": float(p90),
            "share_har_better": float((values > 0).mean()), "equal_weighted_mean": mean,
            "pooled": pooled[comparator], "sign_differs": bool(np.sign(mean) != np.sign(pooled[comparator])),
        }
    named = {}
    for ticker in NAMED_TICKERS:
        frame = windows[windows["ticker"] == ticker]
        if frame.empty:
            named[ticker] = {"present": False}
            continue
        d = {c: _d(frame, c) for c in COMPARATORS}
        named[ticker] = {
            "present": True, "windows": int(len(frame)),
            "coverage": {band: float(frame[f"hit_{band}"].mean()) for band in BANDS},
            "d": d, "against_pooled": {c: bool(np.sign(d[c]) != np.sign(pooled[c])) for c in COMPARATORS},
        }
    return {"distribution": distribution, "named": named}


# ---------------------------------------------------------------------------
# Assembling the read-only study
# ---------------------------------------------------------------------------
def _none_if_nan(value):
    return None if value is None or not math.isfinite(value) else float(value)


def load_study(db_path: Path, min_train_rows: int | None = None) -> dict:
    """Read the modelling universe and its windows (mode=ro), then score the bands out of time."""
    conn = open_readonly(db_path)
    try:
        symbols = modelling_universe(conn=conn)  # read at run time: a symbol that newly fails a filter drops out
        frame = load_frame(conn, symbols) if symbols else pd.DataFrame()
        last_date = conn.execute("SELECT MAX(date) FROM ohlcv").fetchone()[0]
    finally:
        conn.close()
    if frame.empty:
        raise ValueError("no windows in the modelling universe")
    min_train_rows = MIN_TRAIN_ROWS if min_train_rows is None else min_train_rows  # read at call time
    windows, folds = score_folds(frame, min_train_rows)
    if not folds:
        raise ValueError(f"no evaluated fold: no test year has {min_train_rows:,} purged fit windows")
    with np.errstate(all="ignore"):  # a zero rv20 makes log(rv20) infinite in the training script's baseline
        validation = run_validation(frame, min_train_rows=min_train_rows)
    return {
        "windows": windows, "folds": folds, "validation": validation,
        "universe": {"symbols": len(symbols), "tickers_with_windows": int(frame["ticker"].nunique()),
                     "windows": int(len(frame)), "last_date": last_date},
        "excluded_frame": valid_windows(frame)[1],
    }


def _comparison(windows: pd.DataFrame, comparator: str, by_year: list[dict], pooled: dict) -> dict:
    positive = sum(1 for row in by_year if row[f"d_{comparator}"] > 0)
    result = compare_bands(
        windows["date"], windows["loss_har"], windows[f"loss_{comparator}"], years=len(by_year),
        positive_years=positive, har_coverage=pooled["har"]["coverage"],
        comparator_coverage=pooled[comparator]["coverage"],
    )
    return result | {"positive_years": positive, "years": len(by_year)}


def evaluate(study: dict) -> dict:
    """The full report for the scored windows; the two comparisons are the only ones that carry an outcome."""
    windows, folds = study["windows"], study["folds"]
    by_year = by_year_table(windows)
    pooled = {
        band: {
            "coverage": float(windows[f"hit_{band}"].mean()),
            "ci": coverage_interval(windows["date"], windows[f"hit_{band}"])["ci"],
            "mean_width": float(windows[BAND_COLUMNS[band]].mean()),
        }
        for band in BANDS
    }
    trailing_vs_constant = 1 - windows["loss_trailing"].mean() / windows["loss_constant"].mean()
    validation = study["validation"]
    return {
        "header": HEADER,
        "universe": study["universe"],
        "counts": {
            "windows": int(len(windows)), "months": int(windows["date"].str[:7].nunique()), "years": len(folds),
            "excluded_test": sum(f["excluded"] for f in folds), "excluded_frame": study["excluded_frame"],
        },
        "folds": folds, "by_year": by_year, "pooled": pooled,
        "quintiles": quintile_coverage(windows), "sharpness": sharpness_table(windows),
        "rank_correlation": mean_rank_correlations(folds), "per_ticker": per_ticker(windows),
        "comparisons": {c: _comparison(windows, c, by_year, pooled) for c in COMPARATORS},
        "trailing_vs_constant": {"d": float(trailing_vs_constant), "check_evaluator": bool(trailing_vs_constant <= 0)},
        "reference": {
            "recorded": {"har": RECORDED_CORRELATIONS[0], "log_rv20": RECORDED_CORRELATIONS[1]},
            "har_corr": _none_if_nan(validation.get("oot_corr")),
            "log_rv20_corr": _none_if_nan(validation.get("baseline_log_rv20_corr")),
            "pooled_coverage": _none_if_nan(validation.get("pooled_coverage")),
        },
    }


def run(db_path: Path, *, min_train_rows: int | None = None) -> dict:
    return evaluate(load_study(db_path, min_train_rows))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
BAND_LABELS = {
    "har": "HAR band (served)", "trailing": "trailing 20-session band", "constant": "fitted constant band",
    "literal": "literal constant band (2.5)",
}
CONSEQUENCES = {
    ("trailing", HAR_BETTER): (
        "the served band is kept and the comparison is recorded in docs/MODEL_CARD.md as measured on this "
        "history. The finding is about the size of moves, says nothing about direction and is not a guarantee "
        "of coverage."),
    ("trailing", NOT_BETTER): (
        "the HAR band's extra machinery is not earned on this history. A follow-up change may propose swapping "
        "the served band for the trailing-stdev band (own multiplier, own gates, a re-measured coverage figure "
        "for the brief's wording). It is not applied by this study and needs the owner's go-ahead; the weekly "
        "brief is not stopped by it."),
    ("constant", HAR_BETTER): (
        "per-ticker scaling earns its place. The finding is about the size of moves, says nothing about "
        "direction and is not a guarantee of coverage."),
    ("constant", NOT_BETTER): (
        "per-ticker scaling is not earning its place on this history and the brief's range claim needs "
        "rethinking. This is a decision for the owner and no action is taken. A product range at a fixed number "
        "would put a fixed threshold on the size of a price move, which Rule 3 forbids, so following this up needs "
        "the owner's sign-off on Rule 3 first. Whether the brief prints a range at all is the owner's call."),
}
INCONCLUSIVE_TEXT = (
    "this is not evidence that the bands are equal: a material benefit is neither shown nor excluded (or a "
    "precondition failed). The served band stays and nothing is swapped on this evidence."
)
DOES_NOT_SHOW = (
    "What this result does not show:",
    "  - Not that volatility clustering is unreal: a trailing standard deviation reproducing it is expected, "
    "and it is the HAR's own main input. The study asks only whether the regression on top adds band quality.",
    "  - Nothing about direction: both bands are symmetric around zero and score only the size of the move. "
    "The study says nothing about direction.",
    "  - Nothing about any stock or week, and not that a band of either kind will contain next week's move: coverage is "
    "a long-run share measured on this history, not a guarantee.",
    "  - Nothing beyond this data: one market, the liquid modelling universe selected with full-history filters, "
    "a few test years and few independent market episodes, and the same history that informed the HAR design.",
    "  - It does not show whether the weekly brief is useful (v1 kill criterion 1) and is not a verdict on the "
    "whole model.",
)


def consequence(comparator: str, outcome: str) -> str:
    """What each outcome leads to, fixed in advance (design Decision 8)."""
    if outcome == INCONCLUSIVE:
        return INCONCLUSIVE_TEXT
    return CONSEQUENCES[(comparator, outcome)]


def _pct(value: float | None, signed: bool = False, digits: int = 1) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value * 100:+.{digits}f}%" if signed else f"{value * 100:.{digits}f}%"


def _ci(ci: tuple, signed: bool = False) -> str:
    return "n/a" if ci[0] is None else f"[{_pct(ci[0], signed)}, {_pct(ci[1], signed)}]"


def _num(value: float | None) -> str:
    return "undefined" if value is None else f"{value:.3f}"


def _head_lines(report: dict) -> list[str]:
    u, c, ref = report["universe"], report["counts"], report["reference"]
    return [
        report["header"],
        f"Universe: {u['symbols']} symbols from modelling_universe(), {u['tickers_with_windows']} with windows; "
        f"database last date {u['last_date']}. Frame windows {u['windows']:,}.",
        f"Out-of-time windows scored: {c['windows']:,} in {c['years']} test years and {c['months']} distinct test months "
        "(the months, not the windows, are the effective sample: windows overlap and tickers move together).",
        f"Windows left out for a zero or non-finite rv20: {c['excluded_test']:,} test windows "
        f"({c['excluded_frame']:,} in the whole frame); they are left out for every band.",
        f"Context from train_har_rv.run_validation, recomputed in this run (DESCRIPTIVE): mean per-fold correlation "
        f"with log realised volatility, HAR {_num(ref['har_corr'])}, log(rv20) {_num(ref['log_rv20_corr'])}; "
        f"reference only, recorded in an archived design: {ref['recorded']['har']} and {ref['recorded']['log_rv20']}. "
        "Not a result of this study and not what it decides on.",
    ]


def _by_year_lines(report: dict) -> list[str]:
    lines = ["", "By test year (DESCRIPTIVE; coverage of each band, nominal 68%; D = HAR improvement in pinball loss):"]
    lines.append("  year  windows   HAR    trailing  constant  literal   D vs trailing  D vs constant")
    for row in report["by_year"]:
        cov = row["coverage"]
        lines.append(
            f"  {row['year']}  {row['n']:>8,}  {_pct(cov['har']):>6} {_pct(cov['trailing']):>8} {_pct(cov['constant']):>9} "
            f"{_pct(cov['literal']):>8}  {_pct(row['d_trailing'], True):>13}  {_pct(row['d_constant'], True):>13}")
    return lines


def _pooled_lines(report: dict) -> list[str]:
    c = report["counts"]
    lines = ["", f"Pooled out-of-time (DESCRIPTIVE; windows {c['windows']:,}, distinct test months {c['months']}; "
             "month-block 95% interval for coverage; width is the mean half-width in % of |r5| x 100):"]
    for band in BANDS:
        p = report["pooled"][band]
        lines.append(f"  {BAND_LABELS[band]:<30} coverage {_pct(p['coverage'])} {_ci(p['ci'])}  "
                     f"mean width {p['mean_width']:.2f}")
    lines.append("  The literal 2.5 band is not calibrated to 68% and does not enter any outcome.")
    return lines


def _quintile_lines(report: dict) -> list[str]:
    q = report["quintiles"]
    lines = ["", "Coverage by quintile of the served model's sigma over all pooled windows (DESCRIPTIVE):"]
    lines.append("  quintile  windows   HAR    trailing  constant  literal")
    for row in q["by_sigma"]:
        lines.append(f"  {row['quintile']:>8}  {row['n']:>8,}  {_pct(row['har']):>6} {_pct(row['trailing']):>8} "
                     f"{_pct(row['constant']):>9} {_pct(row['literal']):>8}")
    lines.append("Trailing band's coverage by quintile of its own rv20 (DESCRIPTIVE): " + ", ".join(
        f"Q{row['quintile']} {_pct(row['trailing'])}" for row in q["trailing_by_rv20"]))
    return lines


def _sharpness_lines(report: dict) -> list[str]:
    lines = ["", "Sharpness (DESCRIPTIVE). Fitted: mean half-width as fitted. ORACLE: the width rescaled by one factor "
             "so the test windows' coverage is exactly 68%; it uses test outcomes and is not deployable:"]
    for band in BANDS:
        s = report["sharpness"][band]
        lines.append(f"  {BAND_LABELS[band]:<30} fitted {s['fitted_width']:.2f} (x{s['ratio_fitted']:.2f} of HAR)   "
                     f"oracle {s['oracle_width']:.2f} (x{s['ratio_oracle']:.2f} of HAR)")
    return lines


def _rank_lines(report: dict) -> list[str]:
    r = report["rank_correlation"]
    lines = ["", "Spearman rank correlation of band width with the realised |r5|, mean over folds (DESCRIPTIVE; a rank "
             "check that ignores calibration):"]
    for band in ("har", "trailing"):
        lines.append(f"  {BAND_LABELS[band]:<30} {_num(r[band])}")
    lines.append("  fitted constant band: undefined, its width does not vary")
    return lines


def _ticker_lines(report: dict) -> list[str]:
    lines = ["", f"Per ticker (DESCRIPTIVE; tickers with at least {MIN_TICKER_WINDOWS} windows):"]
    for comparator in COMPARATORS:
        d = report["per_ticker"]["distribution"][comparator]
        if d["tickers"] == 0:
            lines.append(f"  D vs {comparator}: no ticker has enough windows")
            continue
        flag = "  FLAG: ticker-equal-weighted and pooled D have different signs" if d["sign_differs"] else ""
        lines.append(
            f"  D vs {comparator}: {d['tickers']} tickers, median {_pct(d['median'], True)}, p10 {_pct(d['p10'], True)}, "
            f"p90 {_pct(d['p90'], True)}, HAR better in {_pct(d['share_har_better'], digits=0)}; equal-weighted mean "
            f"{_pct(d['equal_weighted_mean'], True)} beside pooled {_pct(d['pooled'], True)}{flag}")
    lines.append("  Named tickers (three tickers and a few hundred overlapping windows each are anecdote, "
                 "not an inference sample; a result against the pooled one is flagged and changes no outcome):")
    for ticker, n in report["per_ticker"]["named"].items():
        if not n["present"]:
            lines.append(f"    {ticker}: absent, no out-of-time windows in the modelling universe")
            continue
        cov = n["coverage"]
        flags = [c for c in COMPARATORS if n["against_pooled"][c]]
        note = f"  FLAG: points against the pooled result vs {', '.join(flags)}" if flags else ""
        lines.append(f"    {ticker}: windows {n['windows']:,}, coverage HAR {_pct(cov['har'])} "
                     f"trailing {_pct(cov['trailing'])} "
                     f"constant {_pct(cov['constant'])}; D vs trailing {_pct(n['d']['trailing'], True)}, "
                     f"vs constant {_pct(n['d']['constant'], True)}{note}")
    return lines


def _comparison_lines(report: dict) -> list[str]:
    names = {"trailing": "trailing band", "constant": "fitted constant band"}
    lines = ["", f"DECISION: two confirmatory comparisons at {CONFIDENCE * 100:.1f}% each (about 95% for the pair), "
             f"margin {MARGIN * 100:.0f}%, {BOOTSTRAP_RESAMPLES:,} paired resamples, seed {SEED}, fixed in the spec "
             "before any run. Everything else above is descriptive."]
    for comparator in COMPARATORS:
        r = report["comparisons"][comparator]
        month, quarter, outcome = r["month"], r["quarter"], r["outcome"]
        lines += [
            "",
            f"D, the HAR band's improvement in pinball loss at 0.68 over the {names[comparator]}: "
            f"{_pct(r['d'], True, 2)}",
            f"  month-block interval {_ci(month['ci'], True)}, half-width {_pct(month['half_width'], digits=2)}, "
            f"{month['blocks']} blocks (distinct test months {r['months']})",
            f"  quarter-block interval {_ci(quarter['ci'], True)}, half-width {_pct(quarter['half_width'], digits=2)}, "
            f"{quarter['blocks']} blocks; quarter-block classification {r['quarter_outcome']['outcome']}"
            + ("  FLAG: month-block and quarter-block intervals classify differently; the month-block one decides"
               if r["disagree"] else ""),
            f"  D positive in {r['positive_years']} of {r['years']} test years",
            f"OUTCOME against the {names[comparator]}: {outcome['outcome']}",
        ]
        lines += [f"  reason: {text}" for text in outcome["reasons"]] + [f"  note: {text}" for text in outcome["notes"]]
        lines.append(f"  leads to: {consequence(comparator, outcome['outcome'])}")
    if report["trailing_vs_constant"]["check_evaluator"]:
        d_tc = _pct(report["trailing_vs_constant"]["d"], True, 2)
        lines += ["", f"NOTE: the trailing band is not better than the fitted constant band (D {d_tc}). "
                  "That is implausible for a volatility-clustering market: check the rv20 handling and the evaluator "
                  "before interpreting either result."]
    return lines


def format_report(report: dict) -> str:
    lines = _head_lines(report) + _by_year_lines(report) + _pooled_lines(report) + _quintile_lines(report)
    lines += _sharpness_lines(report) + _rank_lines(report) + _ticker_lines(report) + _comparison_lines(report)
    return "\n".join(lines + [""] + list(DOES_NOT_SHOW))


def _json_safe(value):
    """Plain JSON: numpy scalars to Python, tuples to lists, NaN to null."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    return None if isinstance(value, float) and not np.isfinite(value) else value


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", type=Path, default=DB_PATH, help="SQLite file, opened read-only")
    parser.add_argument("--json", type=Path, dest="json_path", help="also write the report figures here")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    try:
        report = run(args.db)
    except ValueError as error:
        sys.exit(f"ERROR: {error}")
    print(format_report(report))
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(_json_safe(report), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
