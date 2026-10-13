## Why

The weekly brief's range line rests on the HAR-RV band. The repo's own record says that asset is thinner than it sounds. The archived `calibrate-volatility-range` design records the HAR band's out-of-time correlation with realised volatility at 0.431 against 0.424 for a plain `log(rv20)` baseline, and the first walk-forward run was refused by the baseline gate (pooled 0.4500 against 0.4533), "indistinguishable out of time on this history". The independent review in `docs/DISCUSSION_purpose_and_weekly_brief.md` read that as: the band is volatility clustering that a trailing standard deviation reproduces. A persona-run proxy (a 20-session standard deviation times the square root of 5, over twelve tickers) was used for the brief's trigger measurements, so the proxy is already standing in for the band in the owner's thinking. **Those figures are unreplicated, the proxy numbers are flagged as proxies, and none of them is a result of this change.**

Row E1 of that document's status record, and kill criterion 2 of the weekly brief's v1, ask one question: over the modelled tickers, is the band no better than a constant five-session range or a trailing 20-day-stdev band? The answer decides two things: whether the band the brief prints is worth its upkeep (a training script, an artifact, gates), and whether per-ticker scaling earns its place at all. It is a measurement, so it follows the repo's study-script precedent (`evaluate_band_coverage_by_regime.py` and its `band-coverage-regime-evaluation` capability): a read-only script, the decision rule written down before any figure exists, and both outcomes' consequences fixed in advance. It depends on no other change and can run in parallel with N1 to N3.

## What Changes

- Add `backend/scripts/evaluate_band_against_trailing_stdev.py`, a read-only study. It opens the database with `mode=ro`, writes no table and no model file, and scores three bands over the same out-of-time windows, tickers and folds: the served HAR-RV band, a trailing 20-session-stdev band (`k20 × √5 × rv20`, with its own multiplier fitted on the same training folds to the same 0.68 nominal coverage) and a constant five-session range.
- The constant comparator comes in two forms, both reported: the literal ±2.5% the owner named, and a constant band whose half-width is fitted per fold to the same 0.68 nominal coverage, so that sharpness can be compared at equal coverage. Only the fitted form enters the decision (the reason is in the design).
- The decision rule is stated first, in the spec and in constants in the script: a pooled relative improvement in out-of-time quantile (pinball) loss at 0.68, a margin, a month-block interval corrected for two comparisons, a per-year consistency condition and a calibration guard. The outcome per comparator is `HAR_BETTER`, `NOT_BETTER` or `INCONCLUSIVE`; the script prints it by applying the rule.
- Everything the owner listed is reported but only the rule's inputs decide: pooled coverage with a month-block interval, coverage by sigma quintile, mean band width (as fitted, and rescaled to exactly 0.68 on the test period, marked as an oracle figure), Spearman rank correlation of band width with the realised 5-session absolute move, and per-year and per-ticker stability with SAB, VPB and VIB called out.
- The spec fixes in advance what each outcome leads to: `HAR_BETTER` against the trailing band means keep the band and record the comparison in `docs/MODEL_CARD.md`; `NOT_BETTER` means a follow-up change proposes swapping to the simpler band (the weekly brief is not killed); `INCONCLUSIVE` means the shipped band stays and nothing is swapped on this evidence. Against the constant band, `NOT_BETTER` is a flagged decision for the owner, never an automatic action.
- Add `backend/tests/test_evaluate_band_against_trailing_stdev.py` for the pure functions (bands, loss, the decision rule, the paired bootstrap, fold equality with `train_har_rv.py`, read-only behaviour), in the style of `test_evaluate_band_coverage_by_regime.py`.
- No API, UI, model, band, artifact or database schema change. No existing spec is modified.

**Out of scope, deliberately:**

- Swapping the served band, deleting `train_har_rv.py` or the artifact, or any change to `volatility.py`. A `NOT_BETTER` outcome opens a separate change.
- Any other comparator (an EWMA, `rv5`, `rv60`, a re-fitted HAR): the two named ones are fixed so that the study has two confirmatory comparisons and not a search. A third comparator is a new change.
- Changing the 20-session window, the 0.68 nominal coverage or the fold scheme after a result.
- Whether the weekly brief is useful (v1 kill criterion 1) and any figure about direction.
- Any edit to `docs/` or the domain rules by the proposal itself. The tasks add a pointer line and a MODEL_CARD paragraph only after the run.

## Domain rules touched

All six rules are honoured unchanged; none needs sign-off now. Two flags concern what a later change would need.

- **Rule 1** (horizon and outcome): the outcome is still `outcome_t = ln(close[t+5]/close[t])`, built by `build_window_frame`, a session being one stored OHLCV row. The trailing band targets the same thing as the served band: a daily sigma over trailing sessions scaled by `√5` to a 5-session half-width, scored against `|outcome_t|`.
- **Rule 3** (magnitude thresholds are volatility-relative): the trailing band is volatility-relative. The constant ±2.5% is a fixed number, but here it is a reference comparator in a developer printout, not a threshold the tool uses to classify any move, so the rule is not engaged by this study. **Flag:** if the study ever found that a constant band was as good as the per-ticker band, adopting it as a product range would put a fixed number on the size of a price move, which Rule 3 forbids; that would need the owner's sign-off on Rule 3 before any follow-up, and the spec says so.
- **Rule 4** (reliability measured, never asserted): no figure from the study is shown to any user; it prints to a terminal and an optional JSON file. Every coverage figure is measured out of time and labelled as such, and none is called Confidence. A follow-up that swapped the band would have to re-measure its coverage before the brief's "about 2 in 3" wording could stay (the phrase must match the nominal coverage).
- **Rules 2, 5 and 6**: nothing is displayed or exported, so Rule 2 is not engaged. The study produces no verdict, Agreement, agent text or model-written text, and its outcomes (`HAR_BETTER`, `NOT_BETTER`, `INCONCLUSIVE`) are about bands, not about any stock and not trading instructions. The script's first line says it is study output, not shown to any user and not investment advice.

## Capabilities

### New Capabilities

- `band-baseline-comparison`: the read-only comparison of the served band with a trailing 20-session-stdev band and a constant band, the pre-registered decision rule and its consequences, the fold, purge and no-look-ahead scheme, and how results are reported with cluster-robust intervals.

### Modified Capabilities

None. `volatility-range` already has a requirement for `evaluate_vol_range.py`; this is a separate script and capability, so no existing spec is touched.

## Impact

- New: `backend/scripts/evaluate_band_against_trailing_stdev.py`, `backend/tests/test_evaluate_band_against_trailing_stdev.py`.
- Reads: `ohlcv` and `ticker_universe` in `backend/data/app.db` (read-only). No network call, no vendor call, no API key, no new dependency: everything it needs is in the stored closes. This is simpler than the regime study, which needed index history from the vendor.
- Imports: `load_frame`, `split_fold`, `fit_fold`, `RANGE_COVERAGE`, `MIN_TRAIN_ROWS` from `train_har_rv.py` and `scaled_band`, `sigma_pct`, `FEATURE_NAMES` from `app/ml/volatility.py`; neither file is edited. The script does not import `vnstock`, so the guard test is unaffected.
- After the run (tasks 5 and 6): one "Result" section in this change's `design.md`, one pointer line in `docs/DISCUSSION_purpose_and_weekly_brief.md` and, per the owner's decision of 2026-10-12 (design, "Owner decisions"), one factual paragraph for every outcome in `docs/MODEL_CARD.md`.
- Backlog: `docs/KNOWN_ISSUES.md` has no entry this closes or worsens. It touches the open question "is the band a validated asset" in the weekly-brief discussion and the v1 kill criteria; the dependency on C1 and C2 (their gate is the 4-week check, of which this is one input) is unchanged.
- Vendor terms and data: nothing is sent anywhere, and no personal, company or regulated data is read; the study uses stored prices only.
