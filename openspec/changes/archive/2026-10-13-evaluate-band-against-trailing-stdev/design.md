## Context

The served band is `range_k × √5 × sigma_daily_pct(t)`: a HAR-RV forecast of the next five sessions' daily volatility (OLS of `ln(realised_std)` on `rv5`, `rv20`, `rv60`), scaled by one global multiplier fitted out of time so that the band holds `|ln(close[t+5]/close[t])|` about 68% of the time (`volatility-range` spec, Rule 1). `rv20` is one of its three inputs, so a trailing-stdev band is the HAR band with the other two features and the regression removed. What the HAR adds over that is exactly what this study asks about.

What the repo already records (none re-run for this change; all are motivation, not results):

- `openspec/changes/archive/2026-10-07-calibrate-volatility-range/design.md` and the independent review in `docs/DISCUSSION_purpose_and_weekly_brief.md`: out-of-time correlation of the HAR forecast with log realised volatility 0.431 against 0.424 for plain `log(rv20)` (0.432 against 0.423 on the 2024 test set); the first walk-forward run was refused by the baseline gate (pooled 0.4500 against 0.4533). That is a correlation of a volatility forecast, not a measure of a band scored against `|outcome_t|`, and a 0.007 correlation gap does not map to a fixed gap in band quality. So this study measures the band's own score.
- The same discussion's persona-run proxy numbers (twelve tickers, `20-session stdev × √5`, k = 1.0 and 1.19; "unreplicated, proxy band, not the production band"). They show that someone has already used the trailing band as a stand-in for the served one. They are not used by this design.
- `openspec/changes/archive/2026-10-11-evaluate-band-coverage-by-market-regime/design.md` (its "Result"): the served band's out-of-time coverage, recomputed from `train_har_rv.py`'s folds, was about 61% in test years 2020 to 2022 and 70% to 74% in 2023 to 2026 against a nominal 68%. This matters here because it means no band calibrated on the past will have equal coverage out of time, which shapes Decision 4. It is a recorded figure from that run, not a result of this change.
- `docs/DISCUSSION_purpose_and_weekly_brief.md`, "Smallest v1 and kill criteria" (2) and the status record row E1: the question and the owner's two named comparators. Retraining spread (per-year fold `k` 1.186 to 1.260; served 1.1927) and the finding that a later ex-date rescaling leaves a band percentage unchanged are from the N1/N2 shaping session; they do not enter this study, which scores `r5` in return space on stored closes.

Facts checked in the repo on 2026-10-12 (read-only):

- `backend/scripts/train_har_rv.py` holds what the study needs and stays unedited: `load_frame`, `split_fold` (fit windows keep only `outcome_date < f"{year}-01-01"`, the 5-session purge), `fit_fold` (HAR coefficients and `range_k`), `RANGE_COVERAGE = 0.68`, `MIN_TRAIN_ROWS = 40_000`, `_month_block_interval`. `run_validation` returns per-fold `corr` and `baseline_corr` and pooled out-of-time figures.
- `build_window_frame` already carries `rv20` (the std of the last 20 daily log returns up to and including `t`, `ddof=1`) and `r5` for every window, so the trailing band needs no new estimator and no new data.
- `backend/scripts/evaluate_band_coverage_by_regime.py` (902 lines) is the template for structure, month-block bootstrap, header line, JSON output and read-only opening. It is not imported (it carries the vendor fetch code this study does not need); its helpers that are reusable in shape are re-written small here, with tests.
- `rv20` can be zero (20 identical closes), which makes `|r5| / rv20` infinite. The universe filters exclude stale-close and illiquid names, so this should be rare; the study excludes and counts such windows (Decision 3).

## Goals / Non-Goals

**Goals:**

- Answer one question with a rule fixed before any figure exists: over the modelling universe and the same walk-forward test years, is the served HAR-RV band materially better than a trailing 20-session-stdev band, and than a constant band, at the same nominal coverage?
- Fix, before the run, what each outcome leads to, so a result cannot be read to suit a preference.
- Say plainly how much a pooled figure over overlapping windows, one market and about seven test years can and cannot settle.
- Stay read-only, re-runnable and free of any network call.

**Non-Goals:**

- Swapping the band, retiring `train_har_rv.py`, editing `volatility.py`, the artifact or any served output.
- Other comparators or tuning of the 20-session window.
- Any claim about direction, about a specific stock, or about whether the brief is useful.
- A second reliability figure for users (Rule 4).

## Decisions

### 1. A new script and a new capability, not an edit to `evaluate_vol_range.py` or `volatility-range`

`evaluate_vol_range.py` has its own spec requirement and answers a different question (the served band's coverage by year and sigma quintile). A separate script and capability leave that requirement stable and keep a possibly-negative study out of shipped specs, as the regime study did. Alternative rejected: add a comparison section to `evaluate_vol_range.py`, which would modify a shipped script and a requirement for a study whose answer may be "no change".

### 2. Two comparators, fixed in advance (new; covered by no domain rule except as noted)

**(a) Trailing 20-session-stdev band.** Half-width `k20 × √5 × rv20(t) × 100` percent, where `rv20(t)` is the window frame's own column (closes up to `t` only) and `k20` is, per fold, the empirical 0.68-quantile of `|r5| × 100 / (√5 × rv20 × 100)` over that fold's fit windows. That is `fit_range_k` applied to a different sigma, so it uses the same quantile estimator, the same fit windows and the same nominal coverage as the served band. This is the fairness condition: the trailing band is not handicapped by an uncalibrated multiplier (the persona-run proxy used `k = 1.0` and `1.19`).

**(b) Constant band.** Two forms, both reported:

- *Literal*: half-width 2.5, in the units the served band is scored in (`|r5| × 100`, so percent of the log ratio; the difference from a simple percentage at this size is under 0.04 points and is stated, not corrected). Its coverage is whatever it is, with no calibration. It answers the owner's named comparator and shows how far from 0.68 a rule-of-thumb number lands. It does **not** enter the decision, because a band with a different coverage cannot be compared on sharpness at equal coverage.
- *Fitted*: per fold, the half-width is the empirical 0.68-quantile of `|r5| × 100` over that fold's fit windows (the unscaled version of the same estimator). This is the "constant range" that is a fair opponent: if per-ticker scaling is worth anything it must beat the best constant. It is the one that enters the decision.

Rule 3: the trailing band is volatility-relative. Both constant forms are fixed numbers, but they are reference comparators in a developer printout and classify no move for any user. Rule 3 is not engaged by measuring them; it would be by adopting one (Decision 8).

**Fixed.** No third comparator (EWMA, `rv5`, `rv60`, a refitted HAR, a different window) is added, and the 20-session window is not searched. Each added comparator is another chance to find a difference; the study has exactly two confirmatory comparisons (Decision 5).

Alternatives rejected: a trailing band with `k = 1` or the production `k` (hands the HAR the win through miscalibration or tests a number that is not fitted on the same folds); a 60-session band (a different question); the literal ±2.5% only (not comparable at equal coverage).

### 3. Same windows, same folds, same purge, no look-ahead

The folds are `train_har_rv`'s, imported rather than re-implemented: expanding walk-forward by calendar year, fit windows keep only `outcome_date` before the test year (the 5-session purge), test windows are those whose start date `t` is in the test year, a fold needs `MIN_TRAIN_ROWS` purged fit windows, the universe is `modelling_universe()` read at run time (delisted symbols included, as in training). For each fold, in this order: the HAR coefficients and `range_k` are fitted by `fit_fold` on the fit windows exactly as the served model is (so the HAR band under test is the served one); `k20` and the fitted constant are fitted on the same fit windows restricted to `rv20 > 0` and finite; then all three bands are scored on the test windows.

Windows with `rv20` not positive and finite are excluded from the trailing and constant fits and from scoring for **all three** bands, so the three bands are scored on identical windows; their number is printed. The HAR fit itself is unchanged so that the HAR band equals the served one. A test asserts that on a synthetic frame without such windows the study's per-fold test year, window count and HAR coverage equal `train_har_rv.run_validation`'s.

No look-ahead: every band at `t` uses closes up to and including `t` (`rv5`, `rv20`, `rv60`) and parameters fitted on windows whose outcome date precedes the test year. The one later close read for a window is its outcome close at `t+5`. A test changes closes after `t` and asserts that each band's width at `t` is unchanged. Purge and embargo are the existing scheme's; no further embargo is added because features are trailing and the fit/test boundary is by outcome date, so overlap between a fit window's outcome and a test window's features cannot occur.

### 4. The primary metric is quantile (pinball) loss at 0.68, not width and not correlation

The owner's wording is "interval sharpness = mean band width at equal coverage". Width at equal coverage is the right idea, but out of time the coverage is not equal and cannot be made so honestly: calibrated to 0.68 on the past, each band's coverage drifts by year (about 61% to 74% for the served band, per the regime study's recorded result), and a band that under-covers is narrower. Comparing widths then rewards the band that fails more. The pinball loss at τ = 0.68 is the proper scoring rule for the 0.68-quantile of `|r5|`, which is exactly what each band claims to be. For a half-width `w` and `a = |r5| × 100`, the loss is `τ(a − w)` when `a ≥ w` and `(1 − τ)(w − a)` when `a < w`, summed or averaged over windows, in percentage points. It charges for width and for misses in one number, so equal coverage does not have to be imposed.

The decision statistic is the pooled relative improvement `D = 1 − L_HAR / L_X` of the HAR band over comparator `X` (positive means the HAR band is better), where `L` is the mean loss over the same pooled out-of-time windows. Pooling is window-weighted, as the artifact's pooled coverage is.

The owner's named metrics are all reported, as descriptive figures that do not decide anything (Decision 7), including mean width as fitted and mean width after rescaling each band to exactly 0.68 coverage on the test windows (an oracle figure that uses test outcomes, marked as such: it shows width at equal coverage literally, and cannot be used to forecast).

Alternatives rejected: width alone (see above); coverage alone (a band wide enough covers anything); the correlation of the forecast with log realised volatility (the recorded 0.431 against 0.424: a statistic of the volatility forecast, not of the band the investor sees; it is printed as context from `run_validation`, not decided on); a Winkler or interval score with another α (not the quantity the band claims).

### 5. The rule: margin, interval, corrections, and three outcomes per comparator (new; covered by no domain rule)

Constants, fixed here before any run (changing one after a result is a new change): margin `M = 0.02` (a 2% relative reduction in loss); 2,000 month-block resamples, seed 0; interval level 97.5% per comparison (percentiles 1.25 and 98.75); calibration guard 0.05; minimum 5 evaluated test years and 60 distinct test months; year consistency two thirds.

For each comparator `X` (trailing band; fitted constant band), with the interval `[lo, hi]` of `D` from the paired month-block bootstrap (Decision 6):

- **`INCONCLUSIVE`** if any precondition fails: fewer than 5 evaluated test years or 60 distinct test months; the HAR band's or `X`'s pooled out-of-time coverage is further than 0.05 from 0.68 (the existing `train_har_rv` pooled gate, applied to both so a loss gap is not a calibration gap); or a non-finite figure.
- Otherwise **`HAR_BETTER`** if `lo ≥ M` and `D > 0` in at least two thirds of the evaluated test years (the pooled win is not one year's); if `lo ≥ M` but the year condition fails, **`INCONCLUSIVE`** naming it.
- Otherwise **`NOT_BETTER`** if `hi < M` (a benefit as large as the margin is ruled out at this level; this includes the case where the comparator is better, which is noted when `hi < −M`).
- Otherwise **`INCONCLUSIVE`** (the interval straddles the margin: a material benefit is neither shown nor excluded).

Why this shape: it compares the whole interval to the margin, so "better", "no better" and "can't tell" are three different findings and a wide interval cannot be mistaken for either of the others. It puts the burden on the HAR band, as the owner's criterion does ("no better than"), but `NOT_BETTER` also has to be earned by an interval that excludes the margin, so a noisy study cannot kill the band by default. `M = 0.02` is a judgement: it is about the smallest improvement for which the HAR's extra machinery (a training script, an artifact, three coefficients and four gates) is arguably worth keeping over one multiplier on a trailing standard deviation. It is not derived from the recorded correlation gap, which is on a different statistic. The owner accepted it on 2026-10-12 (Owner decisions, item 1); it is frozen before the run, and the report prints the interval so a different margin can be read off afterwards without being applied.

Multiple-comparison care: the two comparisons are the only confirmatory tests, so each interval is 97.5% (Bonferroni, about 95% for the pair). Everything else printed (quintiles, widths, rank correlation, per year, per ticker, the literal ±2.5%) is descriptive, carries no decision and is labelled so. The report states the number of comparisons.

### 6. Dependence: calendar-month blocks, paired, with a quarter-block disclosure

Windows overlap (consecutive `t` share four of five return days) and tickers move together on the same days (the recorded per-date coverage sd is about 0.24), so a window or date bootstrap would be far too narrow. The interval is a percentile interval from a calendar-month block bootstrap, as `train_har_rv._month_block_interval` and the regime study do: whole months are resampled with replacement, all windows of a month move together, and the **pair** `(Σ L_HAR, Σ L_X)` is carried per month so that `D` is recomputed on the same resampled months for both bands (a paired difference, not two independent intervals). The report prints the half-width, the month count and, beside it, a quarter-block interval; if the two disagree about the classification the report flags it. The decision uses the month-block interval (the precedent; a quarter-block interval has about a third as many blocks), and the flag is for the owner's reading, not a second rule. Months are not independent either; volatile stretches last months, so the report also prints the number of distinct test months as the effective sample, not the window count.

### 7. Descriptive metrics, each with its own caveat (none enters the rule)

- **Pooled coverage** of each band with a month-block interval (the existing form), by calendar test year, and the by-year table of `D`.
- **Coverage by sigma quintile**: windows are cut into quintiles of the served model's `sigma` over all pooled out-of-time windows (the artifact's own definition) and every band's coverage is printed in each, so the three bands are compared on one ruler. The trailing band's coverage by its own `rv20` quintile is printed as well. Recorded for the served band: about 0.66 to 0.70 (archived design; not re-verified until this run).
- **Sharpness**: mean half-width as fitted, and the oracle width at exactly 0.68 test coverage, per band, and each as a ratio to the HAR band's. Oracle widths use test outcomes and are not a deployable quantity.
- **Rank correlation**: Spearman correlation of band width with the realised absolute move `|r5|`, per fold and as the mean over folds (each fold has its own fit, as `run_validation` averages per fold). Width ranks equal sigma ranks for the HAR and trailing bands, so this is a rank-only check on the volatility forecast that ignores calibration; for the constant band it is undefined and printed as such. It mixes cross-sectional differences (volatile names move more, which any volatility measure sees) with time variation, which is why it is not the decision statistic. The `run_validation` correlations with log realised volatility are printed beside it for continuity with the recorded 0.431 against 0.424.
- **Per ticker**: `D` per ticker with at least 250 out-of-time windows (distribution: median, tenth and ninetieth percentile, share of tickers where the HAR band is better), and the ticker-equal-weighted mean of `D` beside the pooled one, flagged if their signs differ. SAB, VPB and VIB (the names the owner holds, per the weekly-brief discussion) are printed individually with window counts, each band's coverage and `D`. Three tickers and a few hundred overlapping windows each are anecdote, not inference (the discussion's own proxy run put the standard error at about 3.7 points of coverage per ticker); a result on them that points against the pooled result is flagged and never changes the outcome.

### 8. What each outcome leads to, fixed in advance

Against the **trailing band** (the owner's kill criterion, second half):

1. `HAR_BETTER`: keep the served band. Task: record the comparison in `docs/MODEL_CARD.md`, as measured (figures, interval, the date, the data window) and not as a guarantee.
2. `NOT_BETTER`: the HAR band's extra complexity is not earned on this history. The consequence is a **follow-up change** proposing to swap the served band for the trailing-stdev band, with its own multiplier, its own validation gates and a re-measured coverage figure (the brief's "about 2 in 3" wording must keep matching the nominal coverage, Rule 4). It does **not** kill the weekly brief and it is not applied by this change; the swap needs the owner's go-ahead.
3. `INCONCLUSIVE`: the shipped band stays; nothing is swapped on this evidence; the report says it is not evidence that the two are equal. A re-run with more history is a new change, and the rule is not re-parameterised.

Against the **fitted constant band**:

1. `HAR_BETTER`: per-ticker scaling earns its place. Record it in the same MODEL_CARD paragraph.
2. `NOT_BETTER`: per-ticker scaling is not earning its place, and the brief's range claim needs rethinking. This is a **flagged decision for the owner**, never an automatic action, and the flag includes Rule 3: a product range at a fixed number would put a fixed threshold on the size of a price move, which Rule 3 forbids, so following this outcome up needs the owner's sign-off on Rule 3 first (stop and ask). It also bears on whether the brief should print a range at all, which is the owner's call, not the study's.
3. `INCONCLUSIVE`: as above.

Two cross-checks keep the evaluator honest and are not rules: if the **trailing** band is not better than the fitted constant band (a plain comparison of their `D` printed in the report) the study has found something implausible for a volatility-clustering market, and the first move is to look for a defect in the code (for instance the `rv20` handling), not to interpret it; and a literal ±2.5% coverage far from 0.68 is expected and is the reason it is descriptive.

**What the result does not show** (printed in the report and recorded with the result):

- Not that the trailing band "is" the HAR band or that volatility clustering is unreal. A trailing standard deviation reproducing volatility clustering is expected, and it is the HAR's own main input; the study asks only whether the regression on top adds a measurable amount of band quality.
- Nothing about direction. Both bands are symmetric around zero and score only the size of the move. No directional edge is measured or implied (Rule 6).
- Nothing about any stock or week, and not that a band of either kind will hold next week; coverage is a long-run share measured on history.
- Nothing beyond this data: one market, 208 liquid modelling-universe tickers selected with full-history filters (a caveat the artifact's own coverage figure shares), about seven test years, few independent market episodes, and the same history that informed the choice of the HAR design. A `NOT_BETTER` or `HAR_BETTER` is a finding about this history.
- Not whether the weekly brief is useful (v1 kill criterion 1), and not a verdict on the whole model: C1 and C2 are gated by the 4-week check, of which this study is one input.

### 9. Reporting, rules and tests

Stdout: a header line (study output, not shown to any user (Rule 4), a technical observation and not investment advice (Rule 6)); the universe, the window counts, the number of excluded `rv20 <= 0` windows and the `run_validation` context line; the by-year table (coverage of each band, `D`); the pooled table; the quintile table; the sharpness table; the rank-correlation table; the per-ticker summary and the three named tickers; the two comparisons with `D`, interval, half-width, quarter-block interval and flag; the outcome per comparator with reasons; the "does not show" paragraph. `--json PATH` writes the same figures. Nothing reaches an API, the UI or an export, so Rule 4 is honoured by construction. Rule 5 is satisfied by the labels in the printout (descriptive versus decision, oracle versus fitted, recorded versus recomputed). The outcome names are about bands and are not a `debate-synthesiser` label.

`backend/tests/test_evaluate_band_against_trailing_stdev.py`, in the style of the regime study's tests: small pure-function tests on synthetic frames, no real database and no network. They cover, tests first: the three bands' widths and `k` fitting (the trailing multiplier is the 0.68-quantile of the ratio on fit windows only; the fitted constant likewise); the pinball loss on hand-computed cases; the pooled `D`; the paired bootstrap on constructed effects (a known 5% loss advantage in every month gives an interval excluding zero and the margin; no difference gives an interval around zero; the same seed gives identical output); the rule table for every scenario in the spec; fold equality with `train_har_rv.run_validation` for the HAR band; no look-ahead; the exclusion of `rv20 <= 0` windows; the Spearman figures against a direct rank computation; read-only behaviour on a temporary database and no file unless `--json` is given; and that the constants equal the spec's values. Only this file is run for the change; the whole suite is not run because pytest's lifespan touches the real database (recorded in the project's memory notes).

### 10. Pre-registration and single-run discipline

Before the first run on real data, the SHA-256 of the spec file and of the script's constants block are recorded in this file under "Frozen before the first run", as the regime study did. The script is run once on the real database. No constant, comparator, window or fold is changed after a result. A re-run is allowed only for a defect, shown by a failing test written first, with the criterion unchanged, and both runs are recorded; a changed parameter is a new change.

## Risks / Trade-offs

- **The margin is a judgement.** → It is printed with the interval so the owner can see how the outcome would read at another margin, and the owner accepted it on 2026-10-12 (Owner decisions, item 1). It is never changed after the run.
- **Few independent episodes; an `INCONCLUSIVE` is likely if the true gap is near the margin.** → The report prints months, half-width and the quarter-block interval. The level is not lowered to avoid it, and `INCONCLUSIVE` is stated as plainly as the other two.
- **Overlapping windows and pooled tickers inflate apparent precision.** → Month-block bootstrap, paired; distinct months reported as the effective sample.
- **The HAR band has four fitted numbers and the comparators one or none; an in-fold comparison would flatter the HAR.** → All fits are on the fit windows only and all scoring is out of time, so the extra parameters are paid for in the score.
- **Pinball loss is dominated by high-volatility windows.** → A pooled mean over pooled windows, as the artifact's pooled figures are; the by-quintile coverage and per-ticker `D` show whether the HAR's win or loss is concentrated there.
- **A single global `k` per band, and a coverage that drifts by year.** → Applied to all bands alike; the guard excludes a band that is badly off nominal; the by-year `D` and the two-thirds condition keep one year from deciding.
- **Selection by the universe filters (liquidity and history filters use full history).** → Shared with the artifact's own coverage figure; not corrected here; named in "does not show".
- **A `NOT_BETTER` against the constant band could be read as "drop the range".** → The spec and the report state it is a flagged decision for the owner with a Rule 3 note, and not an action.
- **A fresh read of the data can differ from the recorded figures** (the database grows; the regime study's run was on 2026-10-10). → The study recomputes everything it uses and quotes the recorded figures only as labelled references.
- **Importing a sibling script couples two scripts.** → The fold-equality test fails if they drift.

## Migration Plan

No deployment and no data migration; two new files. Roll back by deleting the script and its test. On archive the delta spec becomes `openspec/specs/band-baseline-comparison/spec.md`; run `openspec validate` first. The recorded result goes into this file under a "Result" heading after the single run. Follow-ups are separate changes and are not planned here.

## Owner decisions 2026-10-12

The owner approved the defaults proposed in this design. These close the open questions that stood here; none changes a constant or a requirement as written in the spec.

1. **Margin.** `M = 0.02` is accepted. It is pre-registered and frozen before the run: it is not changed after any result, and the report prints the interval so another margin can be read off without being applied.
2. **Which constant decides.** The fitted per-fold constant band decides. The literal +/-2.5% band stays descriptive and does not enter the rule.
3. **MODEL_CARD.** The `docs/MODEL_CARD.md` paragraph is written for every outcome (`HAR_BETTER`, `NOT_BETTER` and `INCONCLUSIVE`), not only `HAR_BETTER`.
4. **Dependence.** Calendar-month blocks decide, as the precedent does. Quarter blocks are printed beside them and flagged if they disagree about the classification; the flag does not change the outcome. The outer-envelope variant is not adopted.
5. **After `NOT_BETTER` against the constant band.** The result is only flagged for the owner, with the Rule 3 note. No action follows automatically, and what the owner then does is decided when it arises.
6. **Timing.** E1 is independent of N1 and can run at any time. It changes nothing served, so it does not have to wait for the brief.

## Open Questions

None. Questions 1 to 6 of the first draft are closed by the owner decisions above.

## Frozen before the first run

Task 6.1, 2026-10-12 (07:36 UTC), recorded before the script has been run against the real database. Nothing has been run on real data: the script and its 64 tests have only been run on synthetic series and a synthetic temporary database. (One date-only read, `SELECT MAX(date) FROM ohlcv`, was made on the real file with `mode=ro` to know its last date; it computes no figure of the study.) Nothing below may change after a result: a changed constant or spec is a new change.

- `specs/band-baseline-comparison/spec.md`: SHA-256 `caf7253f55170d153369266cc3effc0f536fe8fbf84ea3491e57be3378be5df6`.
- The script's constants block, lines 53 to 77 of `backend/scripts/evaluate_band_against_trailing_stdev.py` (the criterion banner through `COMPARATORS`): SHA-256 `818eda84f8a98e434dca2ef6f49a7d585f22cf4a53ca879c754ab7617027c76d`. Reproduce with `sed -n '53,77p' backend/scripts/evaluate_band_against_trailing_stdev.py | sha256sum`.
- The script as run: git blob `60712cc8b15a51eba2ad53713cd1231e8cea6672` (`git hash-object backend/scripts/evaluate_band_against_trailing_stdev.py`); its test file's blob is `24fd0998954ffdbbd5467cbb152c3cda6def72b9`. Neither is committed (the owner has not asked for a commit).
- The constants then: margin 0.02, interval 97.5% per comparison with 2,000 resamples and seed 0, calibration guard 0.05, at least 5 test years and 60 distinct test months, year consistency two thirds, nominal coverage 0.68, trailing window 20, literal band 2.5.
- The owner's decisions of 2026-10-12 are in the "Owner decisions 2026-10-12" section above (margin 0.02; the fitted constant decides; a MODEL_CARD paragraph for every outcome; month blocks decide with quarter blocks flagged; flag-only after `NOT_BETTER` against the constant; independent of N1).

## Result

Task 6.2, 2026-10-12. One run, no re-run, no parameter, comparator, window or fold changed after seeing the outcome: `backend/.venv/bin/python -I backend/scripts/evaluate_band_against_trailing_stdev.py --json <scratch path>`, with `HOME` and the working directory redirected to a throwaway directory. It opened `backend/data/app.db` with `mode=ro`, made no network call and no vendor call, and wrote nothing but the `--json` report in the scratch directory (the throwaway directory held only that report and the captured output afterwards, so the vendor's config-file writers stayed neutralised). The script was the blob `60712cc8b15a51eba2ad53713cd1231e8cea6672` recorded above; the spec's SHA-256 was unchanged. The database's last date was 2026-10-12. The universe was 208 symbols (all with windows), 385,940 windows in the frame, 334,341 out-of-time windows in 7 test years (2020 to 2026) and 82 distinct test months; 0 windows were left out for a zero or non-finite `rv20`.

**Outcome against the trailing 20-session band: NOT_BETTER.** Verbatim outcome lines:

> `OUTCOME against the trailing band: NOT_BETTER`
> `  reason: the interval's upper end +1.7% is below the margin 2%: a benefit as large as the margin is ruled out at this level`

**Outcome against the fitted constant band: HAR_BETTER.** Verbatim outcome lines:

> `OUTCOME against the fitted constant band: HAR_BETTER`
> `  reason: the interval's lower end +7.0% is at or above the margin 2%, and D is positive in 7 of 7 test years`

In plain words. Against the trailing band, `D` is +0.61% (the HAR band's pooled pinball loss at 0.68 is 0.61% lower) with a month-block 97.5% interval of [-0.4%, +1.7%] (half-width 1.05 points, 82 months) and a quarter-block interval of [-0.6%, +1.7%] (half-width 1.17 points, 28 quarters); both classify `NOT_BETTER`, so there is no disagreement flag. A benefit as large as the 2% margin is ruled out at this level. The interval also includes zero, so the study does not show that the HAR band is better at all, and it does not show that the trailing band is better either (the interval's lower end is only -0.4%). `D` is positive in 4 of 7 test years (negative, between -0.1% and -1.7%, in 2020 to 2022; +1.7% to +2.7% in 2023 to 2026). Against the fitted constant band, `D` is +9.01% with a month-block interval of [+7.0%, +11.1%] (half-width 2.06 points) and a quarter-block interval of [+6.5%, +11.3%] (half-width 2.38 points); both classify `HAR_BETTER`, and `D` is positive in all 7 test years. The cross-check that the trailing band should beat the fitted constant band held (no evaluator-check note was printed). Both pooled coverages are within the 0.05 guard of 0.68 (HAR 67.6%, trailing 67.9%, fitted constant 66.1%).

**What this result does not show.** A `NOT_BETTER` against the trailing band is not a finding that the trailing band is better or that the HAR regression adds nothing: it says a gain as large as the 2% margin is not supported on this history. It is not a finding that volatility clustering is unreal (the trailing standard deviation is the HAR's own main input). Nothing here concerns direction: both bands are symmetric around zero and score only the size of the move. Nothing is shown about any stock or week, and the coverage figures are long-run shares measured on this history, not a guarantee of future coverage. The finding is about this data only: one market, the liquid modelling universe selected with full-history filters, about seven test years and few independent market episodes, and the same history that informed the HAR design. It says nothing about whether the weekly brief is useful.

Figures from this run (copied from the script's printout; every figure below is this run's, none is quoted from the proposal):

```
Universe: 208 symbols from modelling_universe(), 208 with windows; database last date 2026-10-12. Frame windows 385,940.
Out-of-time windows scored: 334,341 in 7 test years and 82 distinct test months (the months, not the windows, are the effective sample: windows overlap and tickers move together).
Windows left out for a zero or non-finite rv20: 0 test windows (0 in the whole frame); they are left out for every band.
Context from train_har_rv.run_validation, recomputed in this run (DESCRIPTIVE): mean per-fold correlation with log realised volatility, HAR 0.417, log(rv20) 0.413; reference only, recorded in an archived design: 0.431 and 0.424. Not a result of this study and not what it decides on.

By test year (DESCRIPTIVE; coverage of each band, nominal 68%; D = HAR improvement in pinball loss):
  year  windows   HAR    trailing  constant  literal   D vs trailing  D vs constant
  2020    48,123   61.4%    63.9%     52.9%    42.7%          -0.3%          +9.6%
  2021    49,671   61.3%    65.1%     54.0%    36.6%          -0.1%          +8.7%
  2022    50,789   61.9%    62.8%     51.2%    30.8%          -1.7%         +11.9%
  2023    50,791   72.9%    72.6%     75.4%    46.6%          +1.7%          +6.4%
  2024    51,098   74.1%    70.9%     82.2%    56.1%          +2.1%         +12.7%
  2025    51,071   72.0%    71.0%     74.8%    51.4%          +2.7%          +4.6%
  2026    32,798   70.1%    69.4%     73.8%    50.5%          +2.5%          +6.4%

Pooled out-of-time (DESCRIPTIVE; windows 334,341, distinct test months 82; month-block 95% interval for coverage; width is the mean half-width in % of |r5| x 100):
  HAR band (served)              coverage 67.6% [65.3%, 69.8%]  mean width 4.97
  trailing 20-session band       coverage 67.9% [65.8%, 70.0%]  mean width 5.20
  fitted constant band           coverage 66.1% [62.7%, 69.5%]  mean width 4.60
  literal constant band (2.5)    coverage 44.7% [42.2%, 47.3%]  mean width 2.50
  The literal 2.5 band is not calibrated to 68% and does not enter any outcome.

Coverage by quintile of the served model's sigma over all pooled windows (DESCRIPTIVE):
  quintile  windows   HAR    trailing  constant  literal
         1    66,869   69.5%    60.9%     82.3%    63.3%
         2    66,868   67.5%    67.4%     75.6%    52.4%
         3    66,868   66.1%    69.8%     67.9%    44.3%
         4    66,868   66.1%    70.8%     58.9%    36.6%
         5    66,868   68.9%    70.8%     45.8%    27.0%
Trailing band's coverage by quintile of its own rv20 (DESCRIPTIVE): Q1 59.4%, Q2 66.6%, Q3 69.8%, Q4 71.3%, Q5 72.6%

Sharpness (DESCRIPTIVE). Fitted: mean half-width as fitted. ORACLE: the width rescaled by one factor so the test windows' coverage is exactly 68%; it uses test outcomes and is not deployable:
  HAR band (served)              fitted 4.97 (x1.00 of HAR)   oracle 5.02 (x1.00 of HAR)
  trailing 20-session band       fitted 5.20 (x1.05 of HAR)   oracle 5.21 (x1.04 of HAR)
  fitted constant band           fitted 4.60 (x0.93 of HAR)   oracle 4.87 (x0.97 of HAR)
  literal constant band (2.5)    fitted 2.50 (x0.50 of HAR)   oracle 4.80 (x0.96 of HAR)

Spearman rank correlation of band width with the realised |r5|, mean over folds (DESCRIPTIVE; a rank check that ignores calibration):
  HAR band (served)              0.266
  trailing 20-session band       0.256
  fitted constant band: undefined, its width does not vary

Per ticker (DESCRIPTIVE; tickers with at least 250 windows):
  D vs trailing: 207 tickers, median +0.9%, p10 -1.0%, p90 +2.9%, HAR better in 70%; equal-weighted mean +0.9% beside pooled +0.6%
  D vs constant: 207 tickers, median +8.7%, p10 +3.9%, p90 +14.5%, HAR better in 98%; equal-weighted mean +9.1% beside pooled +9.0%
  Named tickers (three tickers and a few hundred overlapping windows each are anecdote, not an inference sample; a result against the pooled one is flagged and changes no outcome):
    SAB: windows 1,684, coverage HAR 72.3% trailing 67.6% constant 80.5%; D vs trailing +2.4%, vs constant +15.1%
    VPB: windows 1,684, coverage HAR 65.1% trailing 66.0% constant 69.7%; D vs trailing +0.7%, vs constant +8.5%
    VIB: windows 1,671, coverage HAR 67.6% trailing 66.8% constant 73.6%; D vs trailing +4.2%, vs constant +10.7%

D, the HAR band's improvement in pinball loss at 0.68 over the trailing band: +0.61%
  month-block interval [-0.4%, +1.7%], half-width 1.05%, 82 blocks (distinct test months 82)
  quarter-block interval [-0.6%, +1.7%], half-width 1.17%, 28 blocks; quarter-block classification NOT_BETTER
  D positive in 4 of 7 test years
D, the HAR band's improvement in pinball loss at 0.68 over the fitted constant band: +9.01%
  month-block interval [+7.0%, +11.1%], half-width 2.06%, 82 blocks (distinct test months 82)
  quarter-block interval [+6.5%, +11.3%], half-width 2.38%, 28 blocks; quarter-block classification HAR_BETTER
  D positive in 7 of 7 test years
```

Recorded-figure references, labelled as such and not results of this study: the archived design's 0.431 and 0.424 correlations (this run's recomputed means on the grown database are 0.417 and 0.413, printed above as context); the regime study's recorded served-band coverage of about 61% in test years 2020 to 2022 and 70% to 74% in 2023 to 2026 (this run's HAR column above is 61.3% to 61.9% and 70.1% to 74.1%, a re-measurement on a database that has grown since).

## Decision record

Task 7.2, 2026-10-12. This records what each outcome leads to per Decision 8 and takes no action; every action below needs the owner's decision, and none has been given yet.

- **Against the trailing band: `NOT_BETTER`.** Decision 8 leads to a **follow-up change** that proposes swapping the served band for the trailing-stdev band, to be opened only if the owner decides so. It is not applied here. It would need: a fit-and-gate path for `k20` (a per-fold multiplier fitted on the purged fit windows, with its own pooled out-of-time coverage gates in the way `train_har_rv.py` gates `range_k`); a re-measured coverage figure for the brief's wording under Rule 4 (the brief says "about 2 in 3", which must keep matching the nominal coverage the swapped band actually measures out of time); and an artifact and `backend/app/ml/volatility.py` change (the trailing band needs no regression, so the artifact would carry one multiplier and a window length). It does not stop the weekly brief. The decision is the owner's: the point estimate favours the HAR band slightly (+0.61%), the interval includes zero, and the simplicity argument for the trailing band is a judgement the study does not make. No other margin is applied after the fact (the interval is printed above so a different margin can be read off, not applied).
- **Against the fitted constant band: `HAR_BETTER`.** Per-ticker scaling earns its place on this history. It is recorded in the `docs/MODEL_CARD.md` paragraph (task 7.3). No Rule 3 flag arises, because the constant-band `NOT_BETTER` path was not taken.
- **Recorded for the owner, not acted on:** the quarter-block intervals agree with the month-block classification for both comparisons (no flag); SAB, VPB and VIB all point the same way as the pooled result against the trailing band (+2.4%, +0.7%, +4.2%), which is anecdote and changes nothing.
- The owner's decision and its date: not yet given.
