# Discussion: After the pivot, the new outputs are unvalidated and the old model is still live (2026-10-06)

Raised while planning dashboard changes after the move from the XGBoost
return prediction to a HAR-RV volatility range plus a three-agent debate
(commits c89b501 and 974c905, plus uncommitted edits under
`backend/app/services/debate/`). Six read-only reviews were run in parallel,
each from a different angle: ML and serving, debate architecture, debate
failure modes, frontend, rules/specs/docs, and evaluation/data. This file
merges them. Nothing here has been actioned.

**How to read the numbers.** They come from the reviewers' own read-only
queries (database opened `mode=ro`) and code reading, not from a re-run by the
author of this file. Where two reviewers measured the same thing
independently, that is said. The reviewers' scratch scripts were not kept in
the repo (see "Reproducing").

## Summary

1. The range shown as "±X% (5 sessions)" is a per-session σ. Measured
   coverage of the real 5-session move is about a third. It is also uncapped.
2. The debate gives a verdict on data that is about a month old, with no
   staleness, `near_gap` or quality-flag guard, and a failed agent still
   counts as a vote.
3. Nothing shows the verdicts carry information. The technical vote has no
   directional edge on history, news and macro cannot be backtested, and no
   verdict is stored in a scoreable form.
4. The retired XGBoost model is still the headline Prediction card, the
   chart's projected point, a hard startup dependency, and the source of the
   Fresh/Stale dot.
5. The rules, specs and docs were not updated for the pivot, and Rules 1, 3,
   4 and 5 each need a ruling.
6. "Buy Signal" and "Strong Buy Signal" reuse a word the project's own M5
   notes rejected.

## Finding 1: the range is a per-session σ labelled as a 5-session range

- Target is the std of the next five daily log returns
  (`backend/app/ml/volatility.py:90-98`); the output is `exp(pred) * 100`
  with no √5 (`:154-155`). The UI, the LLM prompt and the export all say
  "5 sessions" (`DebatePanel.jsx:233`, `technical.py:98`, `export.py:102`).
- Coverage of |ln(close[t+5]/close[t])| by the shipped band, 208 modelling
  tickers, 385,909 overlapping windows (one reviewer; a second reviewer got
  32% on about 386k rows with its own script):

  | Test | Inside ±range as shipped | Inside ±range × √5 |
  | --- | --- | --- |
  | In-sample, all dates | 32.3% | 61.0% |
  | Non-overlapping (every 5th date) | 32.2% | |
  | Last 12 months | 33.8% | |
  | Time-split refit (train before 2024, test from 2024-02) | 34.8% | 64.7% |

  About ×2.75 would be needed for 69%; tails are fat. Coverage is flat across
  range quintiles (31–36% as shipped), so the ranking is fine and the level is
  wrong. Even a correct 1σ band holds about 68% under a normal distribution,
  so the coverage has to be stated.
- Worked example (VCB): shown 1.13, trailing 20-day daily std 1.11, 5-session
  1σ about 2.49.
- The model is `log σ = −4.94 + 9.28·rv5 + 13.77·rv20 + 14.18·rv60` on raw
  (not log) features, with no clip. 28 loaded tickers return more than 25%,
  all delisted (MTC 2818%, SQC 722%); 49 are above 15%. Live tickers top out
  at about 6.3%. Delisted tickers are loaded, selectable, and not filtered by
  the debate endpoint.
- Trained on the 208 modelling-universe tickers, served to all 599 loaded symbols (the dashboard lists only 208 of them). On
  the 379 outside it, ×1 covers 53.7% and ×√5 covers 74.7%, so it is too wide
  there. The range is `None` only for the 7 tickers with fewer than 60 closes.
- The estimate is median-type: realised mean σ is about 14% above mean
  `exp(pred)`.
- The docstring's corr 0.479 is the 15-ticker "all volatility features"
  model. The shipped model measures 0.433 in-sample and 0.431 out-of-time; a
  plain `log(rv20)` baseline scores 0.424 and a log-feature HAR scores 0.450.
- Limits: windows overlap, so the effective sample is far smaller than n
  (date-clustered coverage sd 0.25 across 2,456 dates); per-year coverage at
  ×√5 swings from 54% to 66%; the time-split refit is the reviewer's own, not
  the shipped model.
- The served model file is 653 B, a pooled `LinearRegression` (sklearn 1.9.0,
  matching `requirements.txt`) with no time split. The only check is an
  in-sample correlation floor (`train_har_rv.py:33`, `:94-104`). It is written
  non-atomically (`:106-108`), carries no version/universe/date metadata, is
  gitignored, and is unpickled on every call (`volatility.py:138`, about
  20 ms warm, 2.8 s on the first call). A refit from the current database
  reproduces the coefficients to three decimals, but nothing is snapshotted.
- `/prediction` already returns `volatility_range_pct` on every status
  (`predictions.py:63,71,84`) and no frontend component reads it. The range
  appears only in the debate panel, as a small muted line, after clicking
  Analyse.

## Finding 2: the debate has no data guards, and the data is about a month old

- 599 tickers are loaded. `last_loaded_at` is 2026-09-07 for 596, 2026-10-05
  for 2, 2026-10-06 for 1. Only 3 have a bar from the last few days. Most of
  the rest end in September 2026 (reviewers counted 367 and 392) and 156–168
  end before 2026. 205 of the 208 modelling tickers are stale. About 21
  sessions are missing.
- `debate.py:59-71` checks only `features_computed` and row existence.
  `/prediction` and `/insight` refuse `near_gap`; the debate does not, and the
  technical agent ignores it.
- Latest feature rows: 199 of 599 are `near_gap`; 129 of those tickers have all
  indicators present, 88 rows have an indicator null (core indicators: 1);
  49 tickers have a hard quality flag within 120 days.
- Technical reads the stored row (RSI, MACD histogram, Tenkan, Kijun) while
  Macro and News use live data. `macro.py:302-310` compares the ticker's last
  20 stored closes with the live index's last 20 by position, so a stale
  ticker is compared with a different calendar window. The foreign-flow
  settling logic (`macro.py:286,333`) is handled well.
- `as_of` is shown only in the Level 3 note. `engine.py:157-163` falls back to
  `date.today()` when technical did not run to completion
  (`technical.py:112-127,140`), which also changes the report filename.

## Finding 3: degraded agents still vote

- `engine.py:138-154`: a Round 1 failure becomes a neutral placeholder; a
  Round 2 failure keeps Round 1 plus a note. Both count as normal votes, and
  the response has no degraded field (`debate.py:28-53`).
- Stub run with the LLM down: three agents down gives OBSERVE / unanimous,
  rendered "Unanimous — 3 of 3 agents", HTTP 200. One bull live and two down
  gives OBSERVE / majority. Two bull live and one down gives BUY_SIGNAL.
- News stance comes only from the LLM (`news.py:126-140`), so a missing key
  forces neutral. A reply the parser does not recognise ("Verdict: bear",
  Vietnamese text) becomes neutral in Round 1 while the bullets argue bearish
  (`news.py:132`), and keeps the Round 1 stance in Round 2.
- Round 2 herding: `news.respond` never re-sees the headlines
  (`news.py:92-117`), and the Round 1 to Round 2 shift is not shown.
- Canned text contradicts reality: a technical LLM failure with a computed
  stance shows "Indicator data unavailable" (`technical.py:206-208`); a news
  LLM failure says "could not fetch the news feeds" (`news.py:134-140`); a
  failed synthesis shows "Unable to generate key tension analysis." as normal
  content (`synthesiser.py:147`), and blank or refused replies render as Key
  Tension.
- The three votes are not independent: News and Macro share the market
  backdrop, Round 2 agents read each other's bullets, and one LLM provider
  serves all of them.
- Uncommitted edits (a Round 2 failure keeps Round 1 plus a note; a tolerant
  stance parser) have no spec delta. A failed Round 2 now silently counts as a
  confirmation.
- `DebatePanel.jsx:122` always prints "Report saved to reports/…", while an
  export failure is only logged (`debate.py:77-81`).

## Finding 4: the verdict is unvalidated and cannot be scored

- Technical vote (RSI / MACD / Ichimoku majority) against the 5-session
  target: bull-or-bear hits 49.2% (n=330,617) against a 48.7% base rate of up
  moves; market-demeaned 49.6%; by year 46–53%. A second reviewer, on 255k
  clean rows: P(up) 49.1% after a bull vote, 48.2% after a bear vote,
  correlation 0.046. Descriptive only: windows overlap, no significance test.
- News and macro are live only (`macro.py:81` uses `date.today()`, news is the
  last 7 days of RSS), so they cannot be backtested, only evaluated going
  forward.
- Nothing is stored. There is no debate table. `reports/YYYY-MM-DD_TICKER.md`
  is gitignored, overwritten per ticker and date, and has no close at `as_of`,
  model version, LLM model, headlines or macro values. Six reports exist
  (VIB, VPB, SAB for 10-02 and 10-05; SAB for 10-06); none is scoreable before
  10-09.
- "Confidence" no longer exists on the debate path. `/insight` still computes
  it from `backtest_predictions`: 10,191 rows, 10 tickers, last date
  2026-08-05, pooled hit-rate 47.7%, so 589 of 599 tickers would read N/A.
  The agreement count that replaces it is a vote count among agents on one
  provider, not a calibrated number.
- Cost and latency: 8 LLM calls per run in 4 sequential stages (the two
  synthesiser calls are independent but awaited in sequence). The README says
  about 45–50 s on `claude_cli` (one measured run: 41 s). The `claude_cli`
  timeout is 120 s with no retries; the openai/anthropic providers and the
  frontend client set no timeout. `POST /debate` has no auth, rate limit or
  concurrency cap. A bad LLM config raises an unhandled 500.

## Finding 5: the old model is still live

- `main.py:33-34` loads the XGBoost Booster at startup and
  `test_tickers_api.py:80-85` asserts startup fails without it. The file is
  gitignored (`backend/.gitignore:42`), so a fresh clone or CI cannot start the
  app. The live HAR model, by contrast, fails silently to `None`.
- `/prediction` still computes `predicted_log_return` (flagged
  `deprecated: true`, `predictions.py:78-85`); `PredictionDisplay.jsx:73` and
  the chart's projected point (`ChartPanel.jsx:333-366`) still render it.
  `/insight` and `AIInsightPanel` still depend on XGBoost and the backtest
  hit-rate. `VITE_DEBATE_PANEL_ENABLED` defaults to off (`App.jsx:11`); it is
  on in the owner's running app.
- The Fresh/Stale dot is wrong for nearly every ticker (see
  `DISCUSSION_calendar_staleness.md`) and is fed by `/prediction`.
- Page load makes about 1 + 3 × 208 = 625 requests (derived from code, not
  measured in a browser; corrected 2026-10-07, this file first said 1,800):
  `GET /tickers` returns the 208-symbol catalog (all loaded, 4 delisted;
  `list_tickers_endpoint` filters by the universe), `TickerPanel.jsx:34` renders
  each as a chip, and each chip fires `/prediction` and `/history`
  (`useTickerFreshness.js:26-38`) and `/insight` (`TickerChip.jsx:88`). Each
  `/prediction` unpickles the HAR model and reads the full OHLCV. The other 391
  of the 599 rows in `tickers` are outside the catalog and are reachable only
  through search. Removing the prefetch loses instant first paint
  on selection (history and prediction share cache keys with the chart), not
  correctness.
- Blast radius if the direction model were removed (ML reviewer):
  - Dead: `ml/backtest.py`, `train_xgb_model` / `train_final_model` /
    `XGB_PARAMS`, the `main.py` lifespan load, the XGBoost branch of
    `/prediction`, all of `/insight`, `POST /backtest`, the
    `backtest_predictions` table, `verify_backtest_predictions.py`,
    `baseline_model_diagnostics.py`, `PredictionDisplay`, the chart's
    prediction line, `AIInsightPanel`, `useBacktestTicker`, `MODEL_CARD.md`,
    and the tests for training, backtest, single-ticker backtest, `/insight`
    and parts of the predictions and tickers API tests.
  - Legacy but harmless: `features.target`, `near_gap`, the ten indicator
    columns not used by the debate, `TRAINING_TICKERS` (drives
    `in_training_set`).
  - Still needed: the four indicators the technical agent reads, the
    OHLCV and quality-gate pipeline, the fold/purge helpers in `training.py`
    (used by `evaluate_cross_sectional_momentum.py`), and
    `get_latest_features_row` / `get_features_computed`, which live in
    `predictions.py` but are imported by `debate.py` and `technical.py`.
- Tests that encode the old behaviour (frontend reviewer): most of
  `App.test.jsx` (the flag is never set, so the debate panel has no
  integration test), all of `PredictionDisplay.test.jsx` and
  `AIInsightPanel.test.jsx`, `ChartPanel.test.jsx` around `:307` and `:398`,
  and `TickerPanel.test.jsx` `:232-264` and `:578-612`.

## Finding 6: rules, specs and docs were not updated for the pivot

| Item | Status | Evidence |
| --- | --- | --- |
| Rule 1, target `ln(close[t+5]/close[t])` | Needs a ruling | HAR target is the std of five daily returns; the debate keeps only the horizon. `DISCUSSION_model_direction.md:474` already asked for a ruling |
| Rule 2, no raw log return | Valid | The UI shows ±% |
| Rule 3, advice thresholds `0.5 × rolling_std(60)` | Dormant | No debate agent uses it (`technical.py:26-27` uses fixed RSI 55/45); live only in the deprecated `/insight` |
| Rule 4, confidence = hit-rate | Contradicted | Replaced by an agreement count (archived design Decision 3, flagged "requires sign-off"; no sign-off recorded, `CLAUDE.md:32` unchanged; `dashboard-ui` spec `:269-294` still mandates the hit-rate) |
| Rule 5, sentiment is a technical proxy | Needs a ruling | The News agent is real news analysis; `config.yaml:144-148` still says M8 is "not started"; labels are compliant (`debate-panel-ui` spec `:50`) |
| Rule 6, not investment advice | Valid, one ruling | See Finding 7 |
| `ticker-prediction` spec | Contradicted | Makes XGBoost a hard startup dependency, and its `predicted_log_return` "MUST NOT remove" contradicts the proposal's "BREAKING remove" |
| `debate-engine` vs `debate-synthesiser` specs | Conflict | 2 neutral + 1 directional is SPLIT in the engine spec and design (`:52`), OBSERVE in the synthesiser spec and code (`synthesiser.py:49-51`) |
| `technical-agent` spec | Underspecified | The "±X%" statistic is not defined |

- Archived task 12.7 ("update MODEL_CARD… config.yaml milestone/model note") is
  ticked but neither pivot commit touched `docs/`, `CLAUDE.md` or
  `openspec/config.yaml`. None of `CLAUDE.md`, `config.yaml`, `MODEL_CARD`,
  `DATA_DICTIONARY`, `DISCLAIMER` or `KNOWN_ISSUES` contains "debate" or
  "HAR-RV". Every `/opsx` session still loads "XGBoost return predictor with
  Confidence / Market Sentiment / Advice" (`config.yaml:6-11`).
- The six rules match between `CLAUDE.md` and `config.yaml` (wording differences
  only). `CLAUDE.md:13` promises an "AI insight panel response contract" in
  `config.yaml` that does not exist.
- Stale elsewhere: `MODEL_CARD.md:3-6,108-110,165-167,259`;
  `DISCUSSION_model_direction.md:574-575` ("open, undecided… still serving")
  while the pivot took its Option 3; `DISCLAIMER.md:19-24`;
  `config.yaml:51-56,91-136,144-148`; `DATA_DICTIONARY.md` (pre-archive
  paths, no HAR-RV artifact or `reports/`); `DISCUSSION_calendar_staleness.md`
  (calls `ticker-manual-refresh` still active; archived 2026-08-12);
  `DISCUSSION_prediction_outcome_tracking.md:97` (frames Rule 4 as the
  backtest hit-rate).
- Archived debate change, still open: prompt language; the unmeasured
  15:00–15:12 board-settle time; `[ticker]` company aliases; the rolling
  foreign-flow window; outcome tracking; removing `/insight` and the flag;
  Rule 4 and Rule 5 sign-off. The last two open questions of 974c905 live only
  in the archived `design.md`, and `CLAUDE.md`'s backlog pointer does not
  cover it.
- `KNOWN_ISSUES.md` has no entry for the new untrusted-input surfaces (RSS text
  inside LLM prompts, a `claude_cli` subprocess, `pickle.load` of the model
  file) or for ticker and indicator context being sent to third-party LLM
  APIs.

## Finding 7: Rule 6 wording and the disclaimer

- Labels `STRONG_BUY_SIGNAL` / `BUY_SIGNAL` ("Strong Buy Signal" / "Buy
  Signal", `engine.py:21`, `DebatePanel.jsx:15-16`, `export.py:37-41`) contain
  the transaction verb that `docs/M5_DASHBOARD_EXPLORE_NOTES.md:185-188`
  rejected, and `insight.py:127` and `synthesiser.py:12` both say "never
  BUY/SELL". The `debate-synthesiser` spec `:19` bans BUY only "as standalone
  instructions". The old test guard `/\bBUY\b/` (`AIInsightPanel.test.jsx:255`)
  is case-sensitive and would not catch these.
- The same labels go into exported `.md` reports that can circulate.
- The disclaimer is shown in all states (`DebatePanel.jsx:278`) and appended to
  every report (`export.py:22`), but its text is a paraphrase of
  `DISCLAIMER.md:31` with a repo path the user cannot open
  (`DebatePanel.jsx:10`). `DISCLAIMER.md` describes Confidence, hit-rate and a
  "statistical model"; it says nothing about LLM agents, news content, the
  range, or that the range as shipped covers about a third of 5-session moves.
  `PredictionDisplay` still shows the retired return as a headline percentage
  with no disclaimer.
- Only the News Round 1 prompt says "do not recommend" and calls headlines
  untrusted. Headlines are capped (19 headlines, 200/160 characters, control
  characters stripped, `news_feeds.py:178-186`) but not fenced, and are echoed
  into Round 2, the synthesis, the UI and the reports. The reviewers
  recommend confirming label wording with whoever owns compliance; this is not
  a legal opinion.

## Where the reviewers disagreed, or earlier statements were wrong

- Loaded tickers: the `tickers` table holds 599 rows, but the dashboard's
  catalog and Watchlist are the 208-symbol modelling universe, so the comment
  at `TickerPanel.jsx:41` ("208") was right. An earlier version of this review
  (and its first summary to the owner) said the Watchlist rendered 599 chips
  and about 1,800 requests; that was wrong and was corrected on 2026-10-07 by
  the `retire-direction-model` draft, then confirmed against the database.
- Debate latency: "4–8 s" exists only as a frontend comment
  (`DebatePanel.jsx:163`). The README documents about 45–50 s on `claude_cli`.
- Stale-ticker counts differ slightly between reviewers (367 vs 392 ending in
  September; 156 vs 168 ending before 2026). The conclusion is the same.
- The debate-architecture reviewer could not run `git diff`; its summary of the
  uncommitted edits is inferred from tests and comments. The failure-mode
  reviewer confirmed the working-tree behaviour in `engine.py`. The diffstat is
  5 files, 288 insertions, 61 deletions.
- `frontend/src/api/tickers.js:90` imports types from `./types`, which does not
  exist (JSDoc only).

## A minimal honest evaluation loop (evaluation reviewer)

- One `debate_log` row (or JSONL line) per run: ticker, `as_of` (the feature
  row date, not today), `run_at`, close at `as_of` (kept from log time, because
  vnstock closes revise between pulls), per-agent Round 1 and Round 2 stances,
  verdict, agreement, raw daily σ and the displayed range, model-file hash, LLM
  model, headline ids, macro values, staleness in sessions.
- A script such as `scripts/score_debates.py`, run by hand or on Refresh (the
  app has no scheduler), scoring rows once `ohlcv` has the t+5 session.
- Range check: coverage of |r5| at ×1 and ×√5, and realised-over-predicted σ.
- Verdict check: hit-rate for BUY and CAUTION only, against the base rate and a
  market-demeaned baseline, with per-agent stance hit-rates so news and macro
  must show they add something over the technical stance.
- A fixed nightly basket (about 25 tickers) would accumulate sample; manual
  runs would take months.

## Options, none decided

1. **Range semantics.** Per-session σ, a 5-session σ (×√5), or a quantile with
   a stated coverage. Cap it. Refuse delisted, stale or too-short-history
   tickers. Require walk-forward validation before it is displayed or charted.
2. **Debate guard.** Refuse or flag stale, `near_gap` and hard-flagged tickers
   as `/prediction` does. Add an `agents_degraded` list to the response and
   abstain (an `INSUFFICIENT_DATA` verdict) when two or more agents are down.
   Show `as_of` and data age.
3. **Old model.** Delete the XGBoost serving path (card, chart point, startup
   load, `/prediction` XGBoost branch, `/insight`, `AIInsightPanel`, the flag)
   or keep it. The freshness dot needs a new source or goes.
4. **Rule 4.** Keep the agreement count under the name "Agreement", require
   interval-coverage calibration, or require an outcome-tracked hit-rate. Who
   signs off.
5. **Rule 6.** Keep or rename "Buy Signal" / "Strong Buy Signal" (for example a
   "lean" wording). Update `DISCLAIMER.md` for LLM agents, news and the range.
6. **Rules 1, 3, 5.** Horizon-only Rule 1 or a separate volatility rule; retire,
   re-home or keep dormant Rule 3; keep Rule 5 as a label ban or rewrite it as
   provenance labelling. Resolve 2 neutral + 1 directional (SPLIT or OBSERVE).
7. **Outcome tracking now.** The only route to a measurable Rule 4 replacement
   and to range-coverage scoring.
8. **Watchlist.** Decide whether to curate it further: it currently lists the
   208-symbol catalog (4 delisted). The 391 other loaded symbols, 190 of them delisted,
   appear only through search.
9. **Doc sync.** One change that updates `CLAUDE.md` and `config.yaml` in
   lockstep, plus `MODEL_CARD`, `DISCLAIMER` and the status lines above.

A suggested order from the review, not a decision: fix and cap the range, then
add the debate guard and degraded-agent markers, then remove the old model from
the UI and serving, then sync the docs, then add the evaluation log. Items
that change a rule or the shape of the product are `/opsx:propose` territory,
not quick patches.

## Reproducing

All figures come from read-only queries against `backend/data/app.db` and
reading the code at the working-tree state on 2026-10-06, including the
uncommitted debate edits. The range-coverage figure used, for each ticker and
date, |ln(close[t+5]/close[t])| against the model's range over the 208
modelling tickers (385,909 overlapping windows), with the shipped
`har_rv_model.pkl` loaded read-only, and a time-split refit trained before 2024
and tested from 2024-02. The scratch scripts were not preserved in the repo.
If these numbers are going to drive decisions, preserve the coverage and
technical-vote scripts under `backend/scripts/` first, as
`DISCUSSION_model_direction.md` did for its own findings.

**Status**: open, undecided. Nothing here has been implemented. The design
artifact for the dashboard is on hold until items 1 to 3 are decided.
