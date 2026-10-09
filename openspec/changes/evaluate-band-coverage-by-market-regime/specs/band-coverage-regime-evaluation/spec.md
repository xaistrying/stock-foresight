## ADDED Requirements

### Requirement: The study is a read-only script that serves nothing (Rule 1, Rule 4)
The system SHALL provide `backend/scripts/evaluate_band_coverage_by_regime.py`, which measures how often the volatility band contains `|ln(close[t+5]/close[t])|` within each market-regime third (Rule 1: the 5-trading-session outcome, a session being one stored OHLCV row, as built by `build_window_frame`). It SHALL open the database with `mode=ro`, SHALL write no table to `backend/data/app.db` or any other SQLite file, SHALL write no model file, and SHALL NOT modify `har_rv_model.json`. Its only possible writes are the index-history CSV named by `--fetch-index` and the report named by `--json`, each only when that flag is given. Its output SHALL begin with a header line stating that it is study output, that no figure in it is shown to any user (Rule 4) and that it is a technical observation, not investment advice (Rule 6). It SHALL NOT change any API response, UI component, model artifact, band or domain rule.

#### Scenario: Read-only
- **WHEN** the script runs against a database file
- **THEN** the database file's bytes are unchanged afterwards, a write attempted on its connection fails, and no model file exists or is modified

#### Scenario: Writes only what was asked for
- **WHEN** the script runs without `--fetch-index` and without `--json`
- **THEN** it creates no file

#### Scenario: Header states what the output is
- **WHEN** the script prints its report
- **THEN** the first line says the output is study output, is not shown to any user and is not investment advice

#### Scenario: No served surface changes
- **WHEN** the change is applied
- **THEN** no API endpoint, UI component, model artifact or domain rule differs from before, and `GET /tickers/{ticker}/range` returns what it returned before

### Requirement: The kill criterion and pass level are fixed in the spec before any result
The system SHALL decide the study's outcome by code that applies the constants below, which are written here before the script has been run on real data. Changing any of them after a result has been seen SHALL be a new change, not an edit to this one. The constants are new and covered by no domain rule (they are not thresholds on the size of a price move, so Rule 3 does not apply); the 5-point level is a judgement about the size of the by-year coverage gaps (reviewer-reported, not verified) and is the owner's decision 8.

For each half (early: window dates before 2023-01-01; late: from 2023-01-01) the study SHALL compute `gap = coverage(calmest third) - coverage(most volatile third)`, in percentage points, with a 95% month-block bootstrap interval. A half is **evaluable** only if its windows span at least 24 distinct calendar months and the calmest and the most volatile third each have windows in at least 8 distinct calendar months within it. The outcome SHALL be:

- `INCONCLUSIVE` if either half is not evaluable, or if fewer than 99% of the distinct window dates in the walk-forward test years have an index close;
- otherwise `KILL` if either half has `|gap|` under 5 points, or the two halves' gaps have opposite signs;
- otherwise (both halves at least 5 points, same sign) `PASS` if both halves' intervals exclude zero and the year-adjusted gap has the same sign and an interval that excludes zero;
- otherwise `INCONCLUSIVE`, with the failing condition or conditions printed (an interval that includes zero, or a year-adjusted gap not separable from zero).

The year-adjusted gap is the equal-weighted mean over calendar years of each year's `gap`, using only years in which the calmest and the most volatile third each have windows on at least 20 distinct dates, with an interval from a month-block bootstrap stratified by year. It exists so that a gap that only restates the by-year variation does not pass.

#### Scenario: Both halves clear the level
- **WHEN** the early gap is +7.0 points with interval [+2.0, +12.0], the late gap is +6.0 points with interval [+1.0, +11.0] and the year-adjusted gap is +5.5 points with interval [+0.5, +10.5]
- **THEN** the outcome is `PASS`

#### Scenario: One half is below the level
- **WHEN** the early gap is +7.0 points and the late gap is +3.0 points, whatever their intervals
- **THEN** the outcome is `KILL`

#### Scenario: Opposite signs
- **WHEN** the early gap is +6.0 points and the late gap is -6.0 points
- **THEN** the outcome is `KILL`

#### Scenario: Large but not distinguishable from zero
- **WHEN** both gaps are at least 5 points with the same sign and the late interval is [-3.0, +15.0]
- **THEN** the outcome is `INCONCLUSIVE`, naming the late interval as the failing condition, and the report states that this is not evidence that no regime effect exists

#### Scenario: Not separable from the by-year variation
- **WHEN** both halves meet the level with intervals that exclude zero but the year-adjusted interval includes zero
- **THEN** the outcome is `INCONCLUSIVE`, naming the year-adjusted gap

#### Scenario: Too little history in a half
- **WHEN** the early half has windows in only 14 distinct calendar months
- **THEN** the outcome is `INCONCLUSIVE`, naming the early half as not evaluable, whatever the late half shows

#### Scenario: The constants live in code and in this spec
- **WHEN** the script's constants are read
- **THEN** the pass gap is 0.05, the split date is 2023-01-01, the volatility window is 20 sessions, the percentile window is 252 sessions, the interval is 95%, the minimum months are 24 per half and 8 per cell, the minimum dates per year-cell is 20 and the minimum index match is 0.99

### Requirement: Regime is the VN-Index's trailing volatility percentile at t, in thirds
The system SHALL define the regime of a session `t` from the VN-Index closes up to and including `t` only. The index's volatility at `t` is the standard deviation of its last 20 daily log returns. The percentile at `t` is the share of the index's last 252 volatility values (including the one at `t`) that are at or below the value at `t`. A percentile up to one third is the calmest third, above two thirds the most volatile third, and the rest the middle third. A session with fewer than 252 prior volatility values SHALL be excluded from every regime figure and counted in the report, and SHALL NOT be assigned a third. A stock session with no index close on its date SHALL likewise be excluded and counted. The report SHALL also give the same figures for an expanding percentile (all prior volatility values, at least 252) as a sensitivity result that does not enter the outcome.

#### Scenario: No look-ahead
- **WHEN** an index close after date `t` is changed
- **THEN** the regime assigned to `t` and to every earlier date is unchanged

#### Scenario: Warm-up dates are excluded and counted
- **WHEN** an index series has 400 closes
- **THEN** the first 271 sessions get no regime, the remaining ones do, and the report states how many stock windows were excluded for that reason

#### Scenario: A series shorter than the warm-up gives no regime at all
- **WHEN** an index series has 200 closes
- **THEN** no session has a regime and the outcome is `INCONCLUSIVE`

#### Scenario: A stock session without an index close
- **WHEN** a stock window's date has no index close
- **THEN** that window is excluded from every cell and counted in the report

### Requirement: The band under test is the served band, measured out of time
The system SHALL measure coverage of the band `range_k × √5 × sigma_daily_pct(t)` using the expanding walk-forward by calendar year that `train_har_rv.py` defines (HAR coefficients and `range_k` refitted on windows whose outcome date precedes each test year, nominal coverage 0.68, the same minimum training rows), over the modelling universe read from `ticker_universe` at run time (delisted symbols included, as in training). It SHALL report each fold's test year, windows and coverage beside the reviewer-reported by-year range of 0.614 to 0.741, labelled as reviewer-reported and not re-verified when this change was written, so the by-year variation is recomputed and never quoted as a result.

#### Scenario: Folds match the training script
- **WHEN** the same windows are given to the study and to `train_har_rv.run_validation`
- **THEN** each fold's test year, window count and coverage are equal

#### Scenario: Universe membership is read at run time
- **WHEN** a symbol newly fails the liquidity filter in `ticker_universe`
- **THEN** a later run no longer includes it, with no edit to the script

#### Scenario: By-year figures are recomputed
- **WHEN** the report prints the by-year coverage
- **THEN** those figures come from this run's folds, and the reviewer-reported range appears only as a labelled reference

### Requirement: Index history comes from the vendor, its depth is measured, and it is cached outside app.db
The system SHALL obtain VN-Index daily closes through the vendor's Unified UI index path that the Macro agent already uses (`Market().index("VNINDEX").ohlcv`), with an explicit `count` large enough for the whole span, never omitted. The script SHALL call `app.vnstock_guard.install()` before `vnstock` is first imported. It SHALL NOT build the index from the stocks being evaluated. It SHALL deduplicate by date, the later row of a date winning, and SHALL report the first date, last date, session count, calendar gaps over 10 days and whether the vendor logged its history-limit warning. If the first date is later than the earliest date the study needs (271 index sessions before the first walk-forward test date, so that its first session has a regime), the script SHALL repeat the call with progressively earlier `end` dates until the earliest returned date stops moving, and report that it did so. It SHALL NOT write the series to `app.db`: with `--index-csv PATH` it reads a cached CSV of `date,close` and makes no network call; with `--fetch-index PATH` it fetches and writes that CSV; with neither it fetches and keeps the series in memory only. The report SHALL give the series' source, fetch date and the SHA-256 of the CSV when one is used, so a re-run on the same CSV and database reproduces the figures.

#### Scenario: Cached series makes no network call
- **WHEN** the script runs with `--index-csv` pointing at an existing file
- **THEN** no vendor call is made and the report names the file's SHA-256

#### Scenario: Duplicate latest session
- **WHEN** the vendor frame repeats the latest date with two rows
- **THEN** the series has one close for that date, the later row's

#### Scenario: Explicit count
- **WHEN** the vendor is called for a multi-year span
- **THEN** the call passes a `count` of at least the number of sessions in that span

#### Scenario: Vendor history is shallower than needed
- **WHEN** the first returned date is later than the earliest date the study needs
- **THEN** the script walks `end` backwards, stops when the earliest date stops moving, and reports the first date it reached

#### Scenario: Rate limit
- **WHEN** the vendor's rate limiter ends the call (a `SystemExit` that `_is_rate_limit_exit` recognises, or a rate-limit exception)
- **THEN** the script writes no partial series, reports the rate limit and exits non-zero, and any other `SystemExit` is not swallowed

### Requirement: Results are split early and late and reported with counts, effective sample and cluster-robust intervals
The system SHALL report, for each half and each regime third, the number of windows, distinct dates, distinct calendar months and regime episodes (maximal runs of consecutive index sessions in the same third), the window-weighted coverage, and the mean and standard deviation across dates of the per-date coverage. Every interval SHALL be a 95% percentile interval from a calendar-month block bootstrap with a fixed seed, resampling whole months so that all windows of a date move together; draws with an empty cell SHALL be dropped and their share reported. The report SHALL state each interval's half-width, so a result that fails because its interval is wide is distinguishable from one that fails because its gap is small, and SHALL give a quarter-block interval beside each month-block interval, flagging any disagreement about whether zero is excluded; the flag does not change the outcome. A `KILL` whose interval for `|gap|` reaches 5 points SHALL be printed with a note that the level is not met and that this is not evidence of no effect.

#### Scenario: Cells carry their effective sample
- **WHEN** the report prints a cell
- **THEN** it shows windows, dates, months and episodes next to the coverage, so 200,000 windows are not read as 200,000 independent observations

#### Scenario: Fixed seed
- **WHEN** the script is run twice on the same database and index CSV
- **THEN** every figure, including the intervals, is identical

#### Scenario: A strong constructed effect
- **WHEN** hits are constructed so the calm third is covered 10 points more often than the volatile third in every month
- **THEN** the month-block interval for the gap excludes zero

#### Scenario: No effect
- **WHEN** hits are drawn with the same probability in every third
- **THEN** the month-block interval for the gap includes zero

### Requirement: A plain outcome is reported whichever way it falls
The system SHALL print the outcome (`PASS`, `KILL` or `INCONCLUSIVE`) with its reasons, and SHALL state a negative or inconclusive result as plainly as a positive one. A `PASS` SHALL be reported as evidence that a later change may design a regime-aware reading, and the report SHALL name what that change would need (a by-regime coverage disclosure is a second reliability figure and needs Rule 4 sign-off) rather than imply the finding is ready to serve. The study SHALL NOT be re-parameterised, re-split or re-windowed after a result to reach a different outcome.

#### Scenario: A negative result is printed, not omitted
- **WHEN** the outcome is `KILL`
- **THEN** the report prints `KILL` with the two gaps and their intervals

#### Scenario: A pass names its prerequisites
- **WHEN** the outcome is `PASS`
- **THEN** the report states that nothing is served and that any user-facing use needs its own change and Rule 4 sign-off
