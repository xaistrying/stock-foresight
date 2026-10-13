# band-baseline-comparison Specification

## Purpose
A read-only, pre-registered comparison of the served HAR-RV five-session range against a trailing 20-session band and a constant band over the same out-of-time windows, with the decision rule and its consequences fixed before the first run. The study never changes the served band, the model artifact or the brief.
## Requirements
### Requirement: The comparison is a read-only script that serves nothing (Rule 1, Rule 4)
The system SHALL provide `backend/scripts/evaluate_band_against_trailing_stdev.py`, which scores the served HAR-RV band, a trailing 20-session-stdev band and a constant band against `|ln(close[t+5]/close[t])|` (Rule 1: the 5-trading-session outcome, a session being one stored OHLCV row, as built by `build_window_frame`). It SHALL open the database with `mode=ro`, SHALL write no table to `backend/data/app.db` or any other SQLite file, SHALL write no model file and SHALL NOT modify `har_rv_model.json`. It SHALL make no network call and import no vendor package. Its only possible write is the report named by `--json`, and only when that flag is given. Its output SHALL begin with a header line stating that it is study output, that no figure in it is shown to any user (Rule 4) and that it is a technical observation, not investment advice (Rule 6). It SHALL NOT change any API response, UI component, model artifact, band or domain rule.

#### Scenario: Read-only
- **WHEN** the script runs against a database file
- **THEN** the database file's bytes are unchanged afterwards, a write attempted on its connection fails, and no model file exists or is modified

#### Scenario: Writes only what was asked for
- **WHEN** the script runs without `--json`
- **THEN** it creates no file

#### Scenario: No network
- **WHEN** the script is imported and run
- **THEN** no module of the `vnstock` package is imported and no network call is made

#### Scenario: Header states what the output is
- **WHEN** the script prints its report
- **THEN** the first line says the output is study output, is not shown to any user and is not investment advice

#### Scenario: No served surface changes
- **WHEN** the change is applied
- **THEN** no API endpoint, UI component, model artifact or domain rule differs from before, and `GET /tickers/{ticker}/range` returns what it returned before

### Requirement: The three bands, and only these comparators, are fixed
The system SHALL score exactly these bands, each as a half-width in percent of `|ln(close[t+5]/close[t])| × 100`. The **HAR band** is `range_k × √5 × sigma_daily_pct(t)` as fitted by `train_har_rv.fit_fold` on each fold's fit windows, so that it is the served band. The **trailing band** is `k20 × √5 × rv20(t) × 100`, where `rv20(t)` is the standard deviation of the last 20 daily log returns up to and including `t`, and `k20` is, per fold, the empirical 0.68-quantile of `|r5| × 100 / (√5 × rv20 × 100)` over that fold's fit windows. The **fitted constant band** is, per fold, the empirical 0.68-quantile of `|r5| × 100` over that fold's fit windows. The **literal constant band** is a half-width of 2.5 in the same units. The nominal coverage of every fitted band SHALL be `RANGE_COVERAGE`, 0.68. The 20-session window SHALL NOT be varied, and no other comparator (an exponentially weighted band, `rv5`, `rv60`, a refitted HAR) SHALL be scored in this change. All bands SHALL be scored on the same windows: a window whose `rv20` is not positive and finite SHALL be excluded from the trailing and constant fits and from scoring for all bands, and the number excluded SHALL be reported.

#### Scenario: The trailing multiplier is fitted on the fit windows only
- **WHEN** `k20` is fitted for a fold
- **THEN** it equals the 0.68-quantile of the ratio over that fold's fit windows alone, and a change to a test window's outcome leaves it unchanged

#### Scenario: The fitted constant is the unscaled quantile
- **WHEN** the fitted constant band is fitted for a fold
- **THEN** its half-width equals the 0.68-quantile of `|r5| × 100` over that fold's fit windows, the same for every ticker and date in the fold

#### Scenario: The literal constant is reported but is not a decision comparator
- **WHEN** the report is printed
- **THEN** the literal 2.5 band's coverage and mean width appear, labelled descriptive, and the decision rule is not applied to it

#### Scenario: Identical windows for every band
- **WHEN** a test window has `rv20` of zero
- **THEN** it is excluded for all bands, counted in the report, and the three bands are scored on the same remaining windows

#### Scenario: No other comparator
- **WHEN** the script's comparators are listed
- **THEN** they are the HAR band, the trailing band and the two constant bands, and the trailing window is 20 sessions

### Requirement: The bands are scored out of time with the training script's folds and no look-ahead (Rule 1)
The system SHALL score the bands with the expanding walk-forward by calendar year that `train_har_rv.py` defines: the fit windows of a test year are those whose OUTCOME date precedes the year (the 5-session purge), the test windows are those whose start date is in the year, a fold needs `MIN_TRAIN_ROWS` fit windows, and the universe is read from `ticker_universe` through `modelling_universe()` at run time (delisted symbols included, as in training). The folds SHALL be obtained by importing `load_frame`, `split_fold`, `fit_fold`, `RANGE_COVERAGE` and `MIN_TRAIN_ROWS` from `train_har_rv.py`, not re-implemented. Every band at `t` SHALL use closes up to and including `t` and parameters fitted on windows whose outcome date precedes the test year. The 5-session outcome-date purge is the only embargo applied.

#### Scenario: Folds match the training script
- **WHEN** the same windows, with no window excluded for a zero `rv20`, are given to the study and to `train_har_rv.run_validation`
- **THEN** each fold's test year, window count and the HAR band's coverage are equal

#### Scenario: No look-ahead
- **WHEN** a close after date `t` is changed
- **THEN** each band's half-width at `t` and at every earlier date is unchanged

#### Scenario: Outcome-date purge
- **WHEN** a window's outcome date falls in a test year while its start date is in the previous year
- **THEN** it is not in that test year's fit windows, and it is a test window of the previous year

#### Scenario: Universe membership is read at run time
- **WHEN** a symbol newly fails the liquidity filter in `ticker_universe`
- **THEN** a later run no longer includes it, with no edit to the script

### Requirement: The decision statistic is the pooled relative improvement in quantile loss at 0.68
The system SHALL compute, for a band with half-width `w` and a window with `a = |r5| × 100`, the pinball loss at τ = 0.68: `τ(a − w)` when `a ≥ w` and `(1 − τ)(w − a)` when `a < w`. The decision statistic `D` for a comparator `X` SHALL be `1 − L_HAR / L_X`, where `L` is the mean loss over the pooled out-of-time windows of all evaluated folds (window-weighted), so that a positive `D` means the HAR band scored better. Its interval SHALL be the paired calendar-month block bootstrap of the next requirement.

#### Scenario: Loss on hand-computed cases
- **WHEN** a half-width of 2.0 is scored against moves of 1.0, 2.0 and 4.0
- **THEN** the losses are 0.32, 0.0 and 1.36 (a miss costs 0.68 per point beyond the band, a wide band 0.32 per point inside it)

#### Scenario: The sign convention
- **WHEN** the HAR band's mean loss is 0.97 and the comparator's is 1.00
- **THEN** `D` is +0.03

#### Scenario: Equal bands
- **WHEN** two bands have identical half-widths in every window
- **THEN** `D` is 0 and its interval includes 0

### Requirement: The decision rule and constants are fixed in the spec before any result
The system SHALL decide the outcome for each of two comparators, the trailing band and the fitted constant band, by code that applies the constants below, which are written here before the script has been run on real data. Changing any of them after a result has been seen SHALL be a new change, not an edit to this one. They are new and covered by no domain rule; none is a threshold on the size of a price move, so Rule 3 does not apply to them. The margin `M` of 0.02 was accepted by the owner on 2026-10-12 and is frozen before the first run.

The constants are: margin `M = 0.02`; 2,000 resamples with seed 0; interval level 97.5% per comparison (percentiles 1.25 and 98.75; two confirmatory comparisons, so about 95% for the pair); calibration guard 0.05; at least 5 evaluated test years and at least 60 distinct calendar test months; year consistency two thirds; and the coverage nominal 0.68. With `[lo, hi]` the interval of `D`, the outcome SHALL be:

- `INCONCLUSIVE` if fewer than 5 test years or 60 distinct test months were evaluated, or the HAR band's or the comparator's pooled out-of-time coverage is further than 0.05 from 0.68, or a figure is not finite;
- otherwise `HAR_BETTER` if `lo ≥ M` and `D` is positive in at least two thirds of the evaluated test years;
- otherwise `INCONCLUSIVE` if `lo ≥ M` but fewer than two thirds of the years are positive, naming the year condition;
- otherwise `NOT_BETTER` if `hi < M`, with a note when `hi < −M` that the comparator is the better band;
- otherwise `INCONCLUSIVE` (the interval includes the margin: a material benefit is neither shown nor excluded).

Only these two comparisons SHALL carry an outcome. Every other figure the report prints SHALL be labelled descriptive and SHALL NOT change an outcome.

#### Scenario: The HAR band is materially better
- **WHEN** `D` is +0.05 with interval [+0.03, +0.07], both coverages are within 0.05 of 0.68, and `D` is positive in 6 of 7 years
- **THEN** the outcome is `HAR_BETTER`

#### Scenario: Better by a point estimate above the margin but not shown
- **WHEN** `D` is +0.03 with interval [+0.01, +0.05]
- **THEN** the outcome is `INCONCLUSIVE`, because the interval includes the margin

#### Scenario: A win that is one year's
- **WHEN** `D` is +0.04 with interval [+0.025, +0.055] and `D` is positive in 3 of 7 years
- **THEN** the outcome is `INCONCLUSIVE`, naming the year condition

#### Scenario: No better, shown
- **WHEN** `D` is +0.004 with interval [-0.006, +0.014]
- **THEN** the outcome is `NOT_BETTER`

#### Scenario: Comparator better
- **WHEN** `D` is -0.05 with interval [-0.08, -0.03]
- **THEN** the outcome is `NOT_BETTER` with a note that the comparator is the better band

#### Scenario: Too little history
- **WHEN** the evaluated folds cover 4 test years
- **THEN** the outcome is `INCONCLUSIVE`, naming the number of years, whatever `D` is

#### Scenario: A band off nominal
- **WHEN** the comparator's pooled out-of-time coverage is 0.60
- **THEN** the outcome is `INCONCLUSIVE`, naming the calibration guard, whatever `D` is

#### Scenario: The constants live in code and in this spec
- **WHEN** the script's constants are read
- **THEN** the margin is 0.02, the interval level is 0.975, the resamples are 2,000, the seed is 0, the calibration guard is 0.05, the minimum folds are 5, the minimum months are 60, the year consistency is two thirds, the nominal coverage is 0.68 and the trailing window is 20

### Requirement: Intervals are paired, calendar-month block bootstraps, with the effective sample reported
The system SHALL compute the interval of `D` by resampling calendar months (`date[:7]` blocks) with replacement over the pooled out-of-time windows, carrying each month's total loss for the HAR band and for the comparator together, so that every draw recomputes `D` on the same months for both bands. It SHALL use a fixed seed, so two runs on the same database give identical figures. It SHALL report the interval's half-width, the number of distinct test months and, beside each month-block interval, a quarter-block interval with a flag when the two disagree about the outcome; the flag SHALL NOT change the outcome. Pooled coverage of each band SHALL be reported with a month-block interval of the same form.

#### Scenario: A strong constructed effect
- **WHEN** the HAR band's loss is 5% lower than the comparator's in every month
- **THEN** the interval of `D` excludes zero and is centred near +0.05

#### Scenario: No effect
- **WHEN** both bands have the same expected loss in every month
- **THEN** the interval of `D` includes zero

#### Scenario: Fixed seed
- **WHEN** the script is run twice on the same database
- **THEN** every figure, including the intervals, is identical

#### Scenario: The effective sample is not the window count
- **WHEN** the report prints a pooled figure
- **THEN** it shows the window count and the number of distinct test months side by side

### Requirement: The descriptive metrics are reported with their caveats and decide nothing
The system SHALL report, labelled descriptive: pooled out-of-time coverage and mean half-width of each band, by calendar test year and pooled; coverage of each band by sigma quintile, the quintiles being those of the served model's `sigma` over the pooled out-of-time windows, and the trailing band's coverage by its own `rv20` quintile; the mean half-width of each band as fitted and rescaled to exactly 0.68 coverage on the test windows, the latter labelled oracle (it uses test outcomes) and each as a ratio to the HAR band's; the Spearman rank correlation of band width with `|r5|` per fold and its mean over folds, with the correlation of the HAR forecast and of `log(rv20)` with log realised volatility from `train_har_rv.run_validation` printed as context beside the recorded 0.431 and 0.424, labelled as recorded in an archived design; `D` per calendar test year; and `D` per ticker with at least 250 out-of-time windows (median, tenth and ninetieth percentile, share of tickers where the HAR band is better, and the ticker-equal-weighted mean of `D` beside the pooled one, flagged when their signs differ). SAB, VPB and VIB SHALL be printed individually with their window counts, each band's coverage and `D`, with a note that three tickers are not an inference sample; a result on them that points against the pooled result SHALL be flagged and SHALL NOT change an outcome.

#### Scenario: Oracle widths are labelled
- **WHEN** the report prints a width rescaled to 0.68 coverage on the test windows
- **THEN** it is labelled oracle and descriptive, and is not used in any outcome

#### Scenario: Constant band has no rank correlation
- **WHEN** the report prints rank correlations
- **THEN** the constant band's entry says the correlation is undefined because its width does not vary

#### Scenario: Recorded figures are references, not results
- **WHEN** the report prints a figure recorded in an archived design (0.431, 0.424, a by-year coverage range)
- **THEN** it appears only as a labelled reference beside the figure recomputed in this run

#### Scenario: A named ticker is absent
- **WHEN** SAB, VPB or VIB has no out-of-time windows in the modelling universe
- **THEN** the report says so for that ticker and does not drop the line silently

#### Scenario: Per-ticker result against the pooled one
- **WHEN** the pooled outcome is `HAR_BETTER` and `D` for SAB is negative
- **THEN** the report flags the disagreement and the pooled outcome is unchanged

### Requirement: A plain outcome with its fixed consequence is reported whichever way it falls (Rule 3, Rule 4, Rule 6)
The system SHALL print each comparator's outcome with its reasons, and SHALL state a negative or inconclusive result as plainly as a positive one. The report SHALL state what each outcome leads to, fixed in advance:

- against the trailing band, `HAR_BETTER` means the served band is kept and the comparison is recorded in `docs/MODEL_CARD.md`; `NOT_BETTER` means a follow-up change proposes swapping the served band for the trailing-stdev band, not that the weekly brief is stopped and not an action taken by this change; `INCONCLUSIVE` means the served band stays and nothing is swapped on this evidence;
- against the fitted constant band, `HAR_BETTER` means per-ticker scaling earns its place; `NOT_BETTER` means per-ticker scaling is not earning its place and the brief's range claim needs rethinking, which SHALL be printed as a flagged decision for the owner and never as an action, with the note that a product range at a fixed number would put a fixed threshold on the size of a price move and needs the owner's sign-off on Rule 3 first; `INCONCLUSIVE` as above.

The report SHALL also state what the result does not show: that a trailing standard deviation reproducing volatility clustering is expected; that neither band says anything about direction; that nothing is shown about any stock or week; that the finding is about this history (one market, the modelling universe, a few test years, few independent episodes); and that it is not a finding about the brief's usefulness. If the trailing band does not beat the fitted constant band, the report SHALL print a note to check the evaluator before interpreting. The study SHALL NOT be re-parameterised, re-split, re-windowed or given another comparator after a result to reach a different outcome.

#### Scenario: A negative result is printed, not omitted
- **WHEN** the outcome against the trailing band is `NOT_BETTER`
- **THEN** the report prints `NOT_BETTER` with `D`, its interval and the follow-up it leads to, and says the brief is not killed by it

#### Scenario: Constant-band result is a flagged decision
- **WHEN** the outcome against the fitted constant band is `NOT_BETTER`
- **THEN** the report prints it as a decision for the owner, names Rule 3, and takes no action

#### Scenario: Inconclusive is not equality
- **WHEN** an outcome is `INCONCLUSIVE`
- **THEN** the report says it is not evidence that the bands are equal and that the served band stays

#### Scenario: A pass does not claim direction or a guarantee
- **WHEN** the outcome is `HAR_BETTER`
- **THEN** the report states that the finding is about the size of moves on this history, says nothing about direction and is not a guarantee of coverage

#### Scenario: Implausible ordering triggers a check
- **WHEN** the trailing band is not better than the fitted constant band
- **THEN** the report prints a note to check the `rv20` handling and the evaluator before interpreting either result

