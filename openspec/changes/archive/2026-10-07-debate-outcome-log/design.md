## Context

The debate (`multi-agent-debate-analyst`, archived 2026-10-05) and the HAR-RV band are live, but nothing they output is stored in a scoreable form (`docs/DISCUSSION_post_pivot_review.md`, Finding 4, "A minimal honest evaluation loop"). Current state, re-verified against commit `e77986e`:

- `POST /tickers/{ticker}/debate` (`backend/app/api/debate.py`) runs the engine, calls `export_debate_report` inside a `try/except` that only does `logger.warning`, and returns the result. There is no debate table (`app.db` holds `ohlcv`, `features`, `tickers`, `ticker_universe`, `ohlcv_quality_flags`, `backtest_predictions`). `harden-debate-runtime` moves the run into a runner task, where duplicate in-flight requests for a ticker join one run; it introduces the post-run step this change registers with.
- `reports/YYYY-MM-DD_<TICKER>.md` is gitignored and overwritten per ticker and date. Six exist (VIB, VPB, SAB for 10-02; SAB, VPB for 10-05; SAB for 10-06).
- `engine._get_as_of` falls back to `date.today()` when the technical agent did not finish (`engine.py:157-163`); the log must not inherit that.
- `AgentPosition` carries only stance and reasoning text. The headlines the News agent saw and the macro numbers the Macro agent computed are local variables and are lost after the call. `fetch_headlines` returns tagged strings (`"[tag] YYYY-MM-DD title — snippet"`), not ids.
- `ohlcv` is upserted per `(ticker, date)` on every reload (`UPSERT_OHLCV`), so a close can change between pulls (the docs record VNM 60.5 then 60.3). `VNINDEX` has no rows in `ohlcv`.
- Data is stale: most tickers end in September 2026, so a debate on them has an `as_of` weeks old and its fifth-session outcome is already known when it runs.
- No scheduler exists and none is to be introduced.

Figures quoted from the review are "measured in the 2026-10-06 review" and have not been reproduced by us; task group 6 reproduces what this design relies on.

Stakeholders: the owner (single user, local app). Constraint: FastAPI + SQLite, no new dependency.

## Goals / Non-Goals

**Goals:**
- Record every debate run with enough provenance to score the verdict and the displayed band once five sessions have passed (`docs/DISCUSSION_prediction_outcome_tracking.md` options 2 and 3, re-framed for the pivot).
- A write that happens once per run, can never fail the debate response, and can never fail silently.
- A log that survives any rebuild of `app.db`.
- A manual, idempotent, offline scoring script that reports range coverage and directional hit-rates against honest baselines with an honest sample size.

**Non-Goals:**
- A scheduler, background job, nightly basket, or piggyback on Refresh (Decision 7).
- A UI for live hit-rate, or any change to how Confidence or Agreement is displayed (option 4 of the outcome-tracking doc; Rule 4 belongs to `align-rules-and-disclaimer`).
- Retraining, recalibrating the band, or changing agent behaviour.
- Backfilling the six existing reports (Decision 9).
- Watchlist curation, quantile-XGBoost, cross-sectional work, a multi-ticker Rail.

## Decisions

### Decision 1: one row per run, surrogate `id` key, every run kept

**Chosen**: `id INTEGER PRIMARY KEY AUTOINCREMENT`; no uniqueness on `(ticker, as_of)`. A re-run of the same ticker and `as_of` is a new row.

**Why**: the report file is already overwritten per ticker and date, which hides re-runs; the log exists to remove that. LLM output is non-deterministic, so two runs on the same inputs can disagree, and that disagreement is itself a measurement (the report counts it). The scorer analyses the first run per `(ticker, as_of)` (Decision 10), so keeping all rows costs nothing statistically and prevents silent cherry-picking by re-running.

**Alternatives**: `UNIQUE(ticker, as_of)` with replace (loses runs, same flaw as the report file); composite PK `(ticker, as_of, run_at)` (awkward to reference, no benefit); a UUID `run_id` returned to the client (more API surface than the `debate_log_id` already proposed); an append-only JSONL file (no joins, no atomic update of outcome columns). No index is added: the table grows by tens of rows a day at most, and a scan of a few thousand rows is milliseconds.

### Decision 2: the log lives in its own SQLite file, `backend/data/debate_log.db`

**Chosen** (the owner's ruling, replacing an earlier draft that put the table in `app.db`): a new module `backend/app/db/debate_log.py` holds the path (`DEBATE_LOG_DB_PATH`, next to `app.db`; `data/*.db` is already gitignored), `get_debate_log_connection()`, `CREATE_DEBATE_LOG_TABLE` and `init_debate_log_db()`. The file and table are created on first write by running `CREATE TABLE IF NOT EXISTS` on the connection the writer opens (cheap, idempotent). `app.db`'s `init_db`, `schema.py` and every existing table are untouched.

**Why**: `backend/.gitignore` and the docs call `app.db` generated and reproducible by reloading tickers, and the data pipeline treats it that way. The log is not reproducible (News and Macro read live data, so a lost row cannot be recreated). A file with its own lifecycle cannot be lost by an `app.db` rebuild or a cleanup of the ohlcv database.

**Consequences**: the scorer needs two connections: `app.db` opened read-only (`file:...?mode=ro`, for `ohlcv` and the modelling-universe filter) and the log file read-write (the only file it writes). `close_at_asof` is read from `app.db` by the writer at log time. There is no cross-file transaction; none is needed, because the writer only inserts into the log and the scorer only reads `app.db`. The log file is still a single local file and needs a normal backup (Risks).

**Alternatives**: the table in `app.db` (the original shape; simple joins with `ohlcv`, but loses data on a rebuild, which is the failure this ruling removes); an append-only JSONL file (no atomic update of outcome columns, no SQL for the per-agent tables); `ATTACH` instead of two connections (works, but gives the scorer write access to `app.db` unless carefully limited).

### Decision 3: what a row stores, and what it does not

Column groups (final list; types in the delta spec):

| Group | Columns | Why |
|---|---|---|
| Identity | `id`, `ticker`, `as_of`, `run_at` | `as_of` is the features-row date, never today; `run_at` is UTC ISO-8601 with offset (the dev server's local zone is UTC+8, so a naive time is ambiguous) |
| Price anchor | `close_at_asof` | read from `ohlcv` at log time (Decision 8) |
| Guards | `eligible`, `eligibility_reasons` (JSON list), `data_age_sessions`, `agents_degraded` (JSON list) | from `debate-data-guards`; needed to exclude look-ahead and degraded runs (Decision 10) |
| Band | `sigma_daily_pct`, `range_5s_pct`, `range_k`, `range_coverage` | from `calibrate-volatility-range`; NULL when the band is unavailable |
| Votes | `r1_technical`, `r1_news`, `r1_macro`, `r2_technical`, `r2_news`, `r2_macro`, `verdict`, `agreement_level` | six stances as columns so per-agent hit-rates are plain SQL; NULL when the agents did not run (an `INSUFFICIENT_DATA` abstention) |
| Provenance | `model_sha256`, `llm_provider`, `llm_model`, `llm_effort`, `code_rev` | what produced the row |
| Evidence | `evidence` (JSON text) | technical inputs, headline ids, macro signal values (Decision 5); a JSON column because agents are being changed by sibling changes and the shape must be able to move without a migration |
| Outcome (nullable) | `outcome_status`, `scored_at`, `date_t5`, `close_asof_at_scoring`, `close_t5`, `r5`, `inside_band`, `direction_hit` | filled by the scorer, once |

`model_sha256` is the SHA-256 of `har_rv_model.pkl` (`app.ml.volatility.MODEL_PATH`), computed at log time (the file is 653 bytes), NULL if absent. If the calibration lives in another artifact, `range_k` and `range_coverage` already capture its effect. `code_rev` is `git rev-parse --short HEAD`, suffixed `+dirty` when `git status --porcelain` is non-empty, resolved once per process, NULL if git is unavailable: prompts and gates are about to change in five sibling changes, so rows from different code are not comparable without it, and the audit that motivated this change was itself run on uncommitted edits. `llm_effort` is only meaningful for `claude_cli`.

`inside_band` and `direction_hit` are derived from the row and `r5`. They are stored anyway so the owner can query with plain `sqlite3`, and so the definitions in force at scoring time are frozen with the row (tests pin them; the unit slip between log return and percent is the classic bug and is made once, in tested code). `direction_hit` is NULL for non-directional verdicts. `r5` is stored as a log return, like `features.target`; Rule 2 concerns the UI and the script prints percentages.

**Deliberately not stored**:
- LLM free text (reasoning bullets, key tension, synthesis): already in `reports/*.md`, large, and it can quote third-party headlines. Scoring needs stances, not prose.
- Headline titles and snippets (Decision 4).
- `range_hit_rate`: it is recomputed from `ohlcv` by `calibrate-volatility-range`; storing it would freeze an in-sample reconstruction next to live outcomes and invite confusing the two.
- The market return over the window: computed at report time from the then-current cross-section (Decision 11); freezing it at scoring time would freeze a 3-ticker average forever.
- Any environment value other than provider, model and effort (no API keys, base URLs).

### Decision 4: third-party headlines are stored as hashed ids, not text

**Chosen**: `evidence.news.headline_ids` is a list of `{tag, date, id}`, where `id` is the first 12 hex characters of the SHA-256 of the exact tagged line the agent saw. The lines are third-party press text (VnExpress, CafeF, Vietstock): short and public, but copyrighted, and retaining 19 per run indefinitely adds a content store the product has not had. Hashing keeps an auditable, reversible-only-by-the-source fingerprint and the tag mix (how much was `[market]` backdrop versus `[ticker]` evidence).

**Cost, stated plainly**: the feeds reach back only 1 to 5 days, so a hash cannot be turned back into text later; "what did the News agent actually read" is unrecoverable from the log (the local report file may still quote some of it). Scoring News stances against outcomes does not need the text, so this is accepted. The owner ruled that titles are not stored.

**Privacy and data handling**: the database is local and gitignored (`data/*.db`); the scorer makes no network call; the log sends nothing to any third party. The rows reveal which tickers the owner chose to analyse and when, so they are personal research history and should be treated like the reports directory. No data is sent to an LLM provider by this change beyond what the debate already sends.

**Alternatives**: store titles (better audit, retains copyrighted text); store nothing about headlines (loses the tag mix); store the full tagged lines (largest).

### Decision 5: agents hand their evidence over; the log does not re-fetch

**Chosen**: `AgentPosition` gains an optional `evidence: dict | None = None` (last field, so existing positional constructors keep working). In Round 1 the technical agent fills the indicator values it voted on plus `near_gap`; the news agent fills `headline_ids`; the macro agent fills raw numbers, not the formatted prompt strings: `vnindex_slope` (-1, 0, 1 or null), `rel_vs_vnindex_pct`, `usdvnd_change_pct`, `foreign_net_vnd`, `foreign_gross_vnd`, `foreign_vote_counted` (bool). `outcome_log.log_debate_run(result)` assembles `evidence` from `result.round1[...]`.

**Why**: re-fetching at log time returns different headlines and a different foreign-flow reading (the board moves until about 15:15); the only honest record is the one the agents used. A single JSON column keeps the schema stable as agents change.

**Alternatives**: widen `DebateResult` with an `evidence` field (collides with `debate-data-guards`, which adds result fields); one column per signal (migration on every agent change); parse the numbers back out of the prompt strings (fragile). The requirement lives in the new capability, not in `debate-engine`, to avoid two deltas on one requirement.

### Decision 6: one write per run, as the runner's post-run hook; non-fatal and loud

**Chosen**: `log_debate_run(result) -> int` is registered as the post-run hook of the runner introduced by `harden-debate-runtime`, which calls it once when a run completes, inside the run's task. Requests that arrive while the run is in flight join it and receive the same result, so a per-request write would insert duplicate rows for one run; the hook runs once, and the id it returns is stored with the run so every joiner's response carries the same `debate_log_id`. Until `harden-debate-runtime` lands, the endpoint calls the writer directly, right after the export (the same `try/except` shape), and the call moves into the hook when that change applies. The hook contract is "called once per run with the `DebateResult`, may return a value that is added to the response under its key"; if the runner's hook ends up with a different signature, only the registration changes.

The write is non-fatal and loud: any exception is caught around the hook call, logged with `logger.error(..., exc_info=True)` naming ticker and `as_of`, and `debate_log_id` is `null` (the run still returns its full result with HTTP 200). `as_of` comes from the result's `data_as_of`; if that is missing the writer raises rather than using `date.today()`.

**Why a response field** (kept by the owner): the existing export failure is a `logger.warning` nobody sees (Finding 3: the panel prints "Report saved" regardless). A log that silently starves defeats the whole loop. An error-level line with a traceback plus a machine-visible null in the response gives two independent signals; a third is the scorer's reconciliation line (Decision 12).

**Alternatives**: write in the endpoint always (duplicates under joining, and a run abandoned by its client would still be logged only if the endpoint is reached again); fail the request (violates the brief); `logger.warning` like the export (the silent-failure pattern); a background queue (a new moving part for a ~1 ms insert); a response header (works, but the body already carries run metadata). The export's own warning is left as it is; hardening it belongs to `harden-debate-runtime`.

**Test hygiene**: tests that reach the endpoint post a fake `DebateResult` for a real ticker; once the write exists they could insert fake rows into the owner's real log. The default test setup therefore points `DEBATE_LOG_DB_PATH` at a temporary file (an autouse fixture); see tasks 3.1.

### Decision 7: scoring is a manual offline script; no scheduler, no piggyback

**Chosen**: `backend/scripts/score_debates.py`, run from the project root (like `evaluate_cross_sectional_momentum.py`), reading `ohlcv` from `backend/data/app.db` (read-only) and reading and writing `backend/data/debate_log.db`. It never calls vnstock. Tickers must be refreshed beforehand with the existing Refresh; the script lists tickers whose pending rows are waiting for data. `--dry-run` reports without writing. It opens `app.db` read-only and writes only to the log file.

**Rejected or deferred**:
- *Piggyback on the manual Refresh* (outcome-tracking doc option 3): deferred. Refresh is per ticker and latency-sensitive; scoring is a batch over the cross-section (the market baseline needs many tickers refreshed), and it would couple ingestion to evaluation. Because the scorer is a pure function of the database, a later change can call it from Refresh without redesign.
- *At server startup*: restart-dependent and silent.
- *A scheduler*: explicitly not to be introduced.

### Decision 8: the t+5 rule is "fifth market session", and the logged close is an audit anchor

**Readiness**: the market session calendar is `SELECT DISTINCT date FROM ohlcv` (any ticker). For a row with `as_of` at calendar index `i`, `d5 = calendar[i+5]`. A row is scored only if the calendar has `d5` and the ticker has bars on `as_of` and on `d5`. If the ticker has no bar on `d5` but has a later bar, the row is `void_gap` (a halted or gapped ticker has no five-session return); if it has no later bar the row stays pending (not refreshed yet). If the ticker has no usable bar on `as_of`, `void_no_bar`. For a ticker without gaps this equals the row-position `t+5` of `verify_backtest_predictions.py`; the calendar form adds the gap guard, because Rule 1 is five trading sessions, not five rows. Readiness never consults the wall clock, only the data. Union-of-tickers is chosen over a minimum-count calendar because most tickers are stale, so a count threshold would erase the recent sessions.

**Provisional bars (added at apply)**: `ohlcv` is written by pulls made at any time of day, so the latest stored session can be a partial candle (SAB 2026-10-07 was stored about 11:45 Vietnam time), and a scored row is never rewritten. Readiness therefore also requires that the *ticker itself* has a bar after the target session: that pull included a later session, so it rewrote the target bar with final values. A bar anywhere else on the calendar is not enough (another ticker may have been refreshed later). The cost is one extra session before scoring. The same reasoning applies to `close_at_asof`: a debate run before the close logs the partial close, which is deliberate (it is what the owner saw), and the scorer anchors on the final close, so the revision line counts these rows.

**Price basis for `r5`**: `r5 = ln(close_t5 / close_asof_at_scoring)`, both read from current `ohlcv`. An upsert rewrites every date a pull returns, so when one pull covers both dates they are on the same adjustment basis; mixing the logged close (old pull) with a new `close_t5` would mix bases whenever a dividend or split adjustment lands in between. `close_at_asof` (logged, in the log file) is kept as an audit anchor: the report counts rows where `|ln(close_at_asof / close_asof_at_scoring)|` exceeds 0.1% (revision or adjustment) and how many would change `inside_band` under the logged anchor.

**Alternatives**: logged close to new `close_t5` (a raw price move, wrong around adjustments); plain row-position (silently wrong on gaps). The 0.1% tolerance is new and provisional (not covered by Rules 1 to 6); the VNM example in the outcome-tracking doc differed by 0.33%.

### Decision 9: nothing is backfilled

The six report files are not imported. Reasons: they hold no structured fields (stances are markdown text; no `close_at_asof`, eligibility, degradation flags, model hash, headlines or macro values); the date in a filename comes from `result.as_of`, which can be `date.today()` when the technical agent failed; the number printed as "Volatility range" in them is the per-session sigma labelled as a 5-session range, with no `range_k`; they were produced while the agents were still being changed (the foreign-flow vote rule changed on 2026-10-05), so they are not runs of one specification; and any value reconstructed now (close at the time) would be exactly the revised data this log exists to avoid. Six rows from three tickers carry almost no statistical weight. The earliest `as_of` (2026-10-02) reaches its fifth session on 2026-10-09, so nothing was scoreable on 2026-10-06 anyway. Importing them would also contaminate a table whose value is provenance.

### Decision 10: the analysis population, and the look-ahead guard

Headline statistics use rows with `outcome_status = 'scored'`, `eligible = 1`, `agents_degraded = '[]'`, and `data_age_sessions <= --max-age-sessions` (default 0); then the first run (lowest `id`) per `(ticker, as_of)`.

**Why the age guard**: with data a month stale, a debate run today has an `as_of` whose whole five-session window is already in the past, and the News and Macro agents read today's news and market. Scoring such a row measures hindsight, not foresight. Age 0 means the run happened on the `as_of` session. The default is strict and the report always prints how many rows the guard removed, so its cost is visible. This relies on the `data_age_sessions` semantics of `debate-data-guards` (Open Question 1). Rows with unknown age are excluded.

**Why first run only**: re-running until the answer looks right would otherwise be rewarded; degraded or ineligible runs are infrastructure outcomes, not opinions, and are excluded and counted. `--all-runs` is not provided (YAGNI); the report prints how many `(ticker, as_of)` pairs had several runs and how many of those disagreed on the verdict.

### Decision 11: what is reported, and against what

All thresholds here are new, not covered by Rules 1 to 6.

1. **Funnel**: rows logged, ineligible, degraded, age-excluded, void, pending, scored, analysed.
2. **Range coverage at the stated band**: share of analysed rows with `inside_band = 1`, next to the mean nominal `range_coverage`; also coverage with `range_k` divided out (is the multiplier doing its job) and the median of `|r5| / range_5s`.
3. **Directional hit-rates**, only for directional verdicts and stances: bull-lean verdicts (`STRONG_BUY_SIGNAL`, `BUY_SIGNAL`) score a hit when `r5 > 0`, bear-lean (`CAUTION_SIGNAL`, `STRONG_CAUTION_SIGNAL`) when `r5 < 0`; `r5 == 0` is a miss (same zero rule as `verify_backtest_predictions.py`). The comparison is the base rate over all analysed rows (P(up) for bull, P(down) for bear), and the edge `hit - base`, as `DISCUSSION_model_direction.md` does. Verdict enum values are used, never display labels, so label renames cannot break scoring.
4. **Market-demeaned baseline**: the same test on `r5 - market_r5`, where `market_r5` is the equal-weight mean of `ln(close[d5]/close[as_of])` over modelling-universe tickers (same SQL filters as `modelling_universe`: `ingestion_state='ok'`, `fails_liquidity_filter=0`, `below_minimum_history=0`; raw SQL, because importing `ticker_universe` imports vnstock) that have both bars, requiring at least 30 (provisional). Computed at report time. Until the owner refreshes a broad set of tickers around the logged dates the baseline will mostly be unavailable, and the report says so.
5. **Per agent**: for each of technical, news, macro and each of Round 1 (before the agents read each other) and Round 2 (the voting stance), hit-rate, base rate and edge over directional stances; plus the verdict's hit-rate minus technical-only on the same rows, so News and Macro have to show they add something.

Alternatives for the baseline: VN-Index (not in `ohlcv`; the macro agent fetches it live and stores nothing, so it would need a network call or a new ingestion; a separate change); median instead of mean; value-weighting (needs market caps).

### Decision 12: effective sample size is estimated, not assumed

Rows overlap within a ticker (four of five sessions shared for consecutive `as_of` dates) and are correlated across tickers (a market move hits every row; Finding 9 of `DISCUSSION_model_direction.md` puts effective breadth near 3.2 of 203 for returns). A row count is therefore not a sample size.

**Chosen**: print the naive Wilson interval, labelled optimistic, and a cluster bootstrap by calendar block of `as_of` dates (block = 20 sessions, 2000 resamples, fixed seed), from which the report prints the half-width and the implied effective n, `p(1-p)/se^2`. The bootstrap is withheld with an explicit message when there are fewer than 8 blocks. The report also prints the number needed for a given half-width: about 384 effective observations for plus or minus 5 points at p = 0.5 (`1.96^2 * 0.25 / 0.05^2`). Selection is also stated: the rows are tickers the owner chose to analyse, and nothing corrects for that.

**Where the numbers stand**: the review's planning figure is about 150 effective observations a year for a nightly basket, a hit-rate error of about plus or minus 8 points (arithmetic check: `1.96 * sqrt(0.25/150) = 0.080`; it is `3 independent bets x 50 non-overlapping five-session windows`). A rough exploratory check made while drafting this change (not preserved, single seed, a daily 25-ticker random basket over 250 sessions to 2026-08-28, the technical vote's hit-rate and a trailing-volatility band as stand-ins for the debate) gave intervals of roughly plus or minus 3 to 5 points, and an effective breadth of daily returns of about 3.4 (ρ̄ about 0.29), consistent with Finding 9. If that holds, the review's figure is conservative for a nightly basket because hit indicators are less correlated across tickers than returns (votes differ across tickers while the market factor is shared). That check used historical proxies, 5-session blocks understate regime dependence, and the real log will start as a handful of hand-picked tickers. **The two estimates are unreconciled**: the review says about plus or minus 8 points, the author's rough check says about plus or minus 3 to 5 for the same kind of basket, and neither has been reproduced by the repo's own script. Task group 6 is the arbiter, and this design hard-codes neither figure. The decision that matters is that the script computes its own interval.

**Alternatives**: assume `n_eff = 3 x blocks` (hard-codes Finding 9's return breadth onto a different statistic); block length 5 (the horizon; leaves cross-block overlap and regime persistence out); per-ticker blocks (ignores cross-ticker correlation).

### Decision 13: the script is self-contained and shares no code with soon-to-be-removed modules

`score_debates.py` loads by path in tests (the precedent in `test_evaluate_cross_sectional_momentum.py`), imports nothing from `ml/backtest.py`, `backtest_predictions` or `verify_backtest_predictions.py` (`retire-direction-model` deletes them), and carries its own `HORIZON_SESSIONS = 5` (Rule 1) rather than importing `training.TARGET_HORIZON`, whose module that change touches.

## Risks / Trade-offs

- **[The log file is irreplaceable and sits beside rebuildable ones]** → it is a separate file (Decision 2); `KNOWN_ISSUES.md` and `DATA_DICTIONARY.md` say to back up `backend/data/debate_log.db` (copy the file, or `sqlite3 backend/data/debate_log.db ".dump"`) and not to delete `data/*.db` in a cleanup. It is still one local file with no off-machine copy.
- **[Duplicate rows from joined requests]** → the write is a once-per-run hook, not per request (Decision 6); a test pins one row for several joined requests.
- **[Look-ahead on stale data]** → age guard (Decision 10), default 0, visible count.
- **[Too few rows for a long time]** → manual runs on fresh data are a handful a week; the report states the effective n and the number needed, and claims nothing below it. A nightly basket would change that but is out of scope.
- **[News and Macro rows are not reproducible]** → that is why they are logged now; no mitigation needed beyond storing the evidence.
- **[Hit-rate against a selected sample]** → stated in the report; not correctable.
- **[LLM or prompt changes mix populations]** → `code_rev` and `llm_*` columns; the report does not stratify automatically (YAGNI) but the columns make it a one-line query.
- **[Fake rows from tests]** → default test redirection of `DEBATE_LOG_DB_PATH` (Decision 6).
- **[Hashed headlines cannot be recovered]** → accepted (Decision 4).
- **[Bootstrap intervals are still optimistic]** → block edges and multi-month regimes leak; the report says the interval is a floor on uncertainty.
- **[Sibling merge conflicts in `engine.py`, `news.py`, `macro.py`]** → the `evidence` edits are small and additive; the author reconciles.

## Migration Plan

1. Deploy: nothing happens at startup. `backend/data/debate_log.db` and its table are created by the first write. `app.db` and its tables are untouched.
2. First scoring is possible five market sessions after the first fresh-data run, once those tickers are refreshed.
3. Rollback: remove the hook registration (or the interim endpoint call); the file is inert and may be left or deleted with no effect on anything else. Copy it first if it holds rows.

## Open Questions

Decided by the owner and no longer open: the log file is separate (Decision 2); the write is the runner's once-per-run hook, interim call from the endpoint (Decision 6); `debate_log_id` stays in the response (null on failure); headline ids are hashes only, no titles (Decision 4); the thresholds below stay provisional; apply order is after `debate-data-guards`, `calibrate-volatility-range` and `harden-debate-runtime`; `range_hit_rate` is not logged.

1. **Semantics of `data_age_sessions`** (owned by `debate-data-guards`): this design assumes 0 means the run happened on the `as_of` session, and defaults the guard to 0. Confirm, and confirm that a run before the next session closes counts as age 0.
2. **Market baseline source**: broad refresh of the modelling universe around logged dates (assumed), or ingest `VNINDEX` into `ohlcv` (a separate change).
3. **Provisional thresholds, new and covered by no rule**: block length 20, minimum 8 blocks, minimum 30 market tickers, revision tolerance 0.1%, default age guard 0. Task 6 may change them.
4. **The effective-sample estimates are unreconciled** (about plus or minus 8 points in the audit, about plus or minus 3 to 5 in the author's rough check); task 6 decides which the report's wording follows.
5. **`code_rev` and first-run-only analysis**: included by default; the owner may drop either.
6. **Hook signature**: if `harden-debate-runtime`'s post-run hook cannot return a value into the response, `debate_log_id` needs the runner to carry it per run; reconcile when both apply.
7. **Piggyback on Refresh** stays deferred; revisit after the first batch of scored rows shows whether manual scoring is being skipped.
