## Why

The typical 5-session band says "about 2 in 3 recent moves inside". Pooled out-of-time coverage is recorded at 0.676 against a nominal 0.68, and coverage is flat across the ticker's own sigma quintiles. By test year it is recorded as swinging from 0.614 to 0.741. Those by-year figures come from the model artifact's walk-forward folds as read by a reviewer, and are recorded again in the archived `calibrate-volatility-range` design. **They are motivation only: nobody has re-run them for this proposal, and this change does not treat them as a result.** A year is a market-wide quantity, so the swing could be a market-regime effect that a market-level reading could describe, or it could be year-specific noise that no regime variable explains.

`docs/DISCUSSION_describe_not_vote_redesign.md` (step S1 of the proposal breakdown, "Decided 2026-10-09" items 7 and 8) asks one question before anyone designs a regime-aware headline part (P7) or a by-year coverage disclosure: does the band's coverage differ by market regime (VN-Index volatility percentile at t) by more than a pre-stated amount, in both an early and a late half, beyond what the by-year variation already shows? The answer is a measurement, not a product change, so it follows the repo's study-script precedent (`evaluate_vol_range.py`, `evaluate_fibonacci_levels.py`, the `cross-sectional-momentum-evaluation` capability): a read-only script, its own spec requirement, and the kill criterion and pass level fixed before anything is run. It can start now because it depends on no other change.

## What Changes

- Add `backend/scripts/evaluate_band_coverage_by_regime.py`, a read-only study. It opens the database with `mode=ro`, writes no table and no model file, and measures how often the served band contains `|ln(close[t+5]/close[t])|` within each market-regime third.
- Regime at `t` is the percentile of the VN-Index's trailing 20-session realised volatility within its own trailing 252 sessions, cut into thirds. Dates without enough index history are excluded and counted, never assigned a regime.
- Band coverage is measured out of time, with the same expanding walk-forward by calendar year that `train_har_rv.py` uses, so the by-year figures are recomputed beside the regime figures instead of quoted.
- Results are split early (before 2023-01-01) and late, and every interval is date-clustered (calendar-month block bootstrap, the repo's precedent). Counts, effective sample and interval width are reported with every figure.
- The kill criterion and pass level are written into the spec and into constants in the script, and the script prints its verdict by applying them: PASS, KILL or INCONCLUSIVE. The level is fixed before any run.
- Index history comes from the vendor, through the same Unified UI call the Macro agent uses (`Market().index("VNINDEX")`), with an explicit `count`. The first task measures the history depth before anything is built on it. The series is cached as a plain CSV outside `app.db`, only when asked.
- Add `backend/tests/test_evaluate_band_coverage_by_regime.py` in the style of `test_evaluate_fibonacci_levels.py`.
- Add a gitignore entry for the CSV cache directory in `backend/.gitignore`.
- No API, UI, model, band or database schema change. No existing spec is modified.

**Out of scope, deliberately:**

- Any product or UI change, including a regime badge, a Rail chip or a headline part (P7).
- The by-year coverage disclosure: it is a second reliability figure and needs Rule 4 sign-off, so it belongs to a later change (P3).
- The event study S2 (`evaluate-event-windows`), which needs P2a's event data.
- A persisted index table, or any write to `app.db`.
- Any change to `macro.py`, which P1 is editing, and any change to `backend/requirements.txt`, which P2a owns (the `vnstock` and `vnai` pin).
- A market proxy built from the 208 stocks: decided circular with the coverage being tested (decision 7).

## Domain rules touched

All six rules are honoured unchanged; none needs sign-off.

- **Rule 1** (horizon and outcome): the outcome is still `outcome_t = ln(close[t+5]/close[t])`, a 5-trading-session move where a session is one stored OHLCV row, built by the existing `build_window_frame`. The regime variable is a function of the index's daily returns up to `t` and is not a second horizon.
- **Rule 4** (reliability measured, never asserted): no reliability figure is shown to any user. The study only measures; its coverage numbers go to a terminal and an optional JSON file, never to an API, the UI or an export. The nominal coverage of the band stays 0.68 and is not restated anywhere a user can see.
- **Rules 2 and 3**: nothing is displayed, so Rule 2 is not engaged. The regime cut-offs are percentiles, relative by construction; the 5-point gap level is a threshold on a difference of coverage rates, not on the size of a price move. It is new and covered by no domain rule (see design).
- **Rules 5 and 6**: no verdict, Agreement, agent text or model-written text is produced or rendered, and the script output is a developer printout, not a UI or an export. The script's first line says so.

## Capabilities

### New Capabilities

- `band-coverage-regime-evaluation`: the read-only regime-coverage study, its regime definition, its pre-stated kill criterion and pass level, its index-history source and cache, and how it reports counts, effective sample and cluster-robust intervals.

### Modified Capabilities

None. `volatility-range` already has a script requirement for `evaluate_vol_range.py`; this study is a separate script and capability, so the specs that P1 edits are not touched.

## Impact

- New: `backend/scripts/evaluate_band_coverage_by_regime.py`, `backend/tests/test_evaluate_band_coverage_by_regime.py`.
- Edited: `backend/.gitignore` (one line for the cache directory, which would otherwise be committable vendor data).
- Reads: `ohlcv` and `ticker_universe` in `backend/data/app.db` (read-only). Calls the vendor for one symbol (VNINDEX), a handful of times at most, no API key. It sends nothing but a symbol and a date range, and no user, company or regulated data.
- New importer of `vnstock`: the script calls `app.vnstock_guard.install()` before the import, as `test_every_vnstock_importer_installs_the_guard_first` requires. P2a also adds a `vnstock` importer in a different file; the two changes share only the vendor's rate limit.
- Vendor terms: `vnstock` 4.0.5 is licensed for personal, research and non-commercial use; this study is inside that, per decision 3. Work, paid or shared use is outside it and is not legal advice.
- Backlog: `docs/KNOWN_ISSUES.md` has no entry this change closes or worsens. `docs/DISCUSSION_calendar_staleness.md` and `docs/DISCUSSION_prediction_outcome_tracking.md` are not touched. The open question "where the by-year coverage disclosure goes" in the describe-not-vote note stays deferred to P3.
