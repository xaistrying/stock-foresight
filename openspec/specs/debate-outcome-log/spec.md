# debate-outcome-log

## Purpose

Record one scoreable row per debate run in `backend/data/debate_log.db`, and score verdicts and the displayed band against realised five-session outcomes by hand, offline, with honest baselines and sample sizes.

## Requirements

### Requirement: Every debate run is recorded as one row in `debate_log`
The system SHALL keep a table `debate_log` in its own SQLite file, `backend/data/debate_log.db`, separate from the application database `app.db`, and SHALL insert one new row for every completed debate run (once per run, not once per request), including runs whose verdict is `INSUFFICIENT_DATA`, runs with degraded agents, and re-runs of the same ticker and `as_of`. The key is a surrogate `id INTEGER PRIMARY KEY AUTOINCREMENT`; there is no uniqueness on `(ticker, as_of)`. A row SHALL hold: `ticker`; `as_of` (NOT NULL); `run_at` (UTC, ISO-8601 with offset); `close_at_asof`; `data_age_sessions`; `eligible` and `eligibility_reasons` (JSON list); `agents_degraded` (JSON list); `sigma_daily_pct`, `range_5s_pct`, `range_k`, `range_coverage`; `r1_technical`, `r1_news`, `r1_macro`, `r2_technical`, `r2_news`, `r2_macro`; `verdict`, `agreement_level`; `model_sha256`, `llm_provider`, `llm_model`, `llm_effort`, `code_rev`; `evidence` (JSON text); and the nullable outcome columns `outcome_status`, `scored_at`, `date_t5`, `close_asof_at_scoring`, `close_t5`, `r5`, `inside_band`, `direction_hit`. Band columns SHALL be NULL when the band was unavailable, and the six stance columns SHALL be NULL when the agents did not run.

#### Scenario: A completed run is logged
- **WHEN** a debate for `VCB` completes with `data_as_of = 2026-10-06`, verdict `BUY_SIGNAL` and all agents healthy
- **THEN** one `debate_log` row exists with `ticker = 'VCB'`, `as_of = '2026-10-06'`, the six stances, the verdict, the band values from the result, and every outcome column NULL

#### Scenario: Re-running keeps both rows
- **WHEN** the same ticker is analysed twice with the same `as_of`
- **THEN** `debate_log` holds two rows with different `id` and `run_at`

#### Scenario: An abstention is logged
- **WHEN** a run ends with verdict `INSUFFICIENT_DATA` and no agent stances
- **THEN** a row is written with `eligible = 0`, the reasons, NULL stance columns, and the verdict

#### Scenario: `as_of` is never today's date
- **WHEN** the technical agent did not complete and the engine's own fallback would have been today's date
- **THEN** the row's `as_of` is the result's `data_as_of`, and if that is unavailable the write fails with an error instead of using `date.today()`

#### Scenario: `run_at` carries its timezone
- **WHEN** a row is written
- **THEN** `run_at` is UTC with an explicit offset, independent of the server's local timezone

### Requirement: The close at `as_of` is captured at log time
The writer SHALL read the `ohlcv` close for `(ticker, as_of)` from `app.db` when the row is written and store it as `close_at_asof`, because stored closes can change between vnstock pulls. The writer SHALL also store `model_sha256` (SHA-256 of the HAR-RV model file, NULL if the file is absent), the LLM provider, model and effort in force, and `code_rev` (the short git revision, suffixed `+dirty` when the working tree has uncommitted changes, NULL if git is unavailable).

#### Scenario: Close is kept as seen at the time
- **WHEN** a row is logged with `close_at_asof = 42.55` and a later reload revises that day's close to 42.50
- **THEN** the row still holds 42.55

#### Scenario: Model file hash recorded
- **WHEN** `har_rv_model.pkl` exists
- **THEN** `model_sha256` equals the SHA-256 of its bytes, and two rows written before and after the file is replaced differ

### Requirement: The log stores no free text, no third-party headline text and no credentials
`debate_log` SHALL NOT contain any agent reasoning bullet, key-tension or synthesis text, any headline title or snippet, or any environment value other than the LLM provider, model and effort. Headlines SHALL appear only as `evidence.news.headline_ids`, a list of `{tag, date, id}` where `id` is the first 12 hex characters of the SHA-256 of the exact tagged line the News agent was given.

#### Scenario: No prose in the row
- **WHEN** a row is written for a run whose reasoning contains a distinctive sentence and whose headlines contain a distinctive title
- **THEN** neither string occurs in any column of the row

#### Scenario: Headline ids are stable
- **WHEN** the same tagged headline line is hashed twice
- **THEN** both calls yield the same 12-character id

### Requirement: Agents expose the evidence the log stores
In Round 1 each agent SHALL attach an `evidence` mapping to its `AgentPosition` (an optional field defaulting to `None`), and `evidence` SHALL be what the log stores, not a re-fetch. The technical agent SHALL provide the indicator values it voted on and `near_gap`; the News agent SHALL provide `headline_ids`; the Macro agent SHALL provide raw numeric values, not formatted prompt strings: `vnindex_slope`, `rel_vs_vnindex_pct`, `usdvnd_change_pct`, `foreign_net_vnd`, `foreign_gross_vnd` and `foreign_vote_counted`, each null when its signal was unavailable.

#### Scenario: Macro values are numbers
- **WHEN** the Macro agent computes a relative return of +1.23 percentage points and a settled foreign net of -365e9 VND of 1488e9 gross
- **THEN** `evidence.macro` holds `rel_vs_vnindex_pct = 1.23`, `foreign_net_vnd = -365e9`, `foreign_gross_vnd = 1488e9` and `foreign_vote_counted = true`

#### Scenario: Unavailable signal
- **WHEN** USD/VND cannot be fetched
- **THEN** `evidence.macro.usdvnd_change_pct` is null

#### Scenario: Evidence is the evidence the agent used
- **WHEN** the News agent was given 12 headlines
- **THEN** `evidence.news.headline_ids` has 12 entries and the log performs no feed request

### Requirement: Logging happens once per run, is non-fatal and is never silent
The log writer SHALL be called once per debate run, as the post-run hook of the debate runner (`harden-debate-runtime`), after the report export step. Until that runner exists, the debate endpoint SHALL call the writer once per request right after the export. Requests that join an in-flight run SHALL NOT cause a second row, and SHALL receive the same `debate_log_id`. A failure to write SHALL NOT change the HTTP status or the debate content of the response, SHALL be logged at ERROR level with the traceback and naming the ticker and `as_of`, and SHALL be visible in the response as `debate_log_id: null`. A successful write SHALL return the new row's `id` as `debate_log_id`.

#### Scenario: Successful write
- **WHEN** a debate completes and the insert succeeds
- **THEN** the response is 200 and `debate_log_id` is the integer id of the new row

#### Scenario: Joined requests share one row
- **WHEN** three requests for the same ticker arrive while one run is in flight
- **THEN** exactly one row is written and all three responses carry the same `debate_log_id`

#### Scenario: Insert fails
- **WHEN** the insert raises (for example the file is locked or unwritable)
- **THEN** the response is still 200 with the full debate result, `debate_log_id` is null, and an ERROR record with a traceback is emitted

#### Scenario: Export failure does not prevent the log
- **WHEN** the export raises and the insert succeeds
- **THEN** the row is still written and `debate_log_id` is its id

#### Scenario: Tests do not write to the real log
- **WHEN** the backend test suite runs
- **THEN** no row is added to the real `backend/data/debate_log.db`, and the file is not created by the tests

### Requirement: The log file is created on first write and never touches `app.db`
The log module SHALL create `backend/data/debate_log.db` and its table with `CREATE TABLE IF NOT EXISTS` when the first row is written, through its own init function. `app.db`'s `init_db` SHALL NOT create, alter or drop `debate_log`, and the log module SHALL NOT alter any `app.db` table.

#### Scenario: First write creates the file
- **WHEN** `debate_log.db` does not exist and a run is logged
- **THEN** the file is created with the table and one row, and `app.db` is unchanged

#### Scenario: Re-initialising a populated log
- **WHEN** the init function runs against a log file that already holds rows
- **THEN** the rows are unchanged and no error is raised

#### Scenario: Rebuilding app.db
- **WHEN** `app.db` is deleted and rebuilt
- **THEN** `debate_log.db` and its rows are unaffected

### Requirement: Scoring reads `app.db` read-only and writes only the log file
`score_debates.py` SHALL open `app.db` read-only (`mode=ro`) for `ohlcv` and the modelling-universe filter, and SHALL write only to `debate_log.db`.

#### Scenario: app.db is not modified
- **WHEN** the script scores rows
- **THEN** `app.db` is byte-identical before and after, and only `debate_log` rows in the log file change

### Requirement: Scoring runs only by hand and offline
Scoring SHALL be performed by `backend/scripts/score_debates.py`, started manually. No scheduler, startup hook, background task or Refresh hook SHALL call it, and it SHALL make no network call and import no vnstock module. Readiness SHALL be decided from `ohlcv` content, never from the wall clock.

#### Scenario: Offline
- **WHEN** the script runs with the network disabled
- **THEN** it completes and scores whatever the database allows

#### Scenario: The clock does not matter
- **WHEN** the system date is far in the future but `ohlcv` has no bar five sessions after a row's `as_of`
- **THEN** the row stays unscored

### Requirement: A row is scored only when its fifth market session exists in `ohlcv` and the ticker has a later bar
The market session calendar SHALL be the distinct `ohlcv.date` values. For a row whose `as_of` is at calendar index `i`, the target session is `calendar[i+5]`. The script SHALL score the row only if that session exists, the ticker has a bar on both `as_of` and the target session, and the ticker has a bar after the target session (a pull made during the target session stores a provisional bar there, and a later bar shows the ticker was refreshed once it was over, which rewrote that bar with its final values; this uses data only, never the clock). A row whose ticker has no bar on the target session but has a later bar SHALL be marked `outcome_status = 'void_gap'`; a row whose ticker has a non-positive close on `as_of` or the target session, or has later bars but none on `as_of`, SHALL be marked `void_no_bar`; any other row, including one whose ticker has a bar on the target session but none after it, or no bar at or after `as_of` at all, SHALL stay pending with all outcome columns NULL. For a ticker with no gaps this is the row-position `t+5` used by `verify_backtest_predictions.py`.

#### Scenario: Not scored early
- **WHEN** a row has `as_of = 2026-10-06` and the ticker's latest bar is four sessions later
- **THEN** the row remains pending and the script reports it as awaiting data

#### Scenario: Provisional fifth-session bar
- **WHEN** the ticker's last bar is the fifth session after `as_of` (for example pulled before that day's close)
- **THEN** the row stays pending and the ticker is listed as needing a refresh after the following session has closed

#### Scenario: Scored when a later bar confirms the fifth session
- **WHEN** the ticker has bars on the fifth session after `as_of` and on a later session
- **THEN** the row gets `outcome_status = 'scored'`, `scored_at`, `date_t5`, `close_asof_at_scoring`, `close_t5`, `r5 = ln(close_t5 / close_asof_at_scoring)`, `inside_band`, and `direction_hit`

#### Scenario: Ticker skipped the target session
- **WHEN** the market calendar has five sessions after `as_of` but the ticker has no bar on the fifth and has a later bar
- **THEN** the row is `void_gap` and is excluded from every statistic

#### Scenario: Ticker not refreshed
- **WHEN** the market calendar has the target session but the ticker has no bar after it
- **THEN** the row stays pending and the ticker is listed as needing a refresh

### Requirement: Scoring is idempotent and never rewrites a scored row
A row with a non-NULL `outcome_status` SHALL NOT be modified by any later run. Running the script twice with no new `ohlcv` data SHALL change no row and report zero newly scored rows. With `--dry-run` the script SHALL print what it would score and write nothing.

#### Scenario: Second run changes nothing
- **WHEN** the script is run twice in a row
- **THEN** the second run reports 0 newly scored rows and every `scored_at` is unchanged

#### Scenario: Dry run
- **WHEN** the script is run with `--dry-run`
- **THEN** no `debate_log` column changes

### Requirement: Outcome definitions are fixed
`r5` SHALL be `ln(close_t5 / close_asof_at_scoring)` with both closes read from current `ohlcv` (Rule 1: five trading sessions). `inside_band` SHALL be `1` when `abs(r5) * 100 <= range_5s_pct` and `0` otherwise, NULL when `range_5s_pct` is NULL. `direction_hit` SHALL be NULL unless the verdict is directional; for `STRONG_BUY_SIGNAL` and `BUY_SIGNAL` it is `1` when `r5 > 0`, for `CAUTION_SIGNAL` and `STRONG_CAUTION_SIGNAL` it is `1` when `r5 < 0`, and `r5 == 0` is a miss. The script SHALL key on verdict enum values, not display labels. The script SHALL also count scored rows whose logged `close_at_asof` differs from `close_asof_at_scoring` by more than 0.1% and how many of them would change `inside_band` under the logged close.

#### Scenario: Zero return is a miss
- **WHEN** a `BUY_SIGNAL` row has `close_t5 == close_asof_at_scoring`
- **THEN** `r5 = 0` and `direction_hit = 0`

#### Scenario: Neutral verdict has no direction
- **WHEN** a row's verdict is `OBSERVE`, `SPLIT` or `INSUFFICIENT_DATA`
- **THEN** `direction_hit` is NULL

#### Scenario: Revised close is flagged, not hidden
- **WHEN** the logged close was 60.5 and the current close at `as_of` is 60.3
- **THEN** the row is scored on the current closes and counted in the revision line of the report

### Requirement: Headline statistics exclude look-ahead, degraded and repeated runs
The analysed population SHALL be rows with `outcome_status = 'scored'`, `eligible = 1`, `agents_degraded = '[]'`, and `data_age_sessions` not NULL and at most `--max-age-sessions` (default 0), reduced to the lowest `id` per `(ticker, as_of)`. The report SHALL print a funnel of counts: rows logged, ineligible, degraded, excluded for age, void, pending, scored, analysed, and the number of `(ticker, as_of)` pairs with more than one run and how many of those disagreed on the verdict.

#### Scenario: Stale-data run is excluded
- **WHEN** a scored row has `data_age_sessions = 20`
- **THEN** it is counted in the funnel as excluded for age and contributes to no hit-rate or coverage

#### Scenario: Re-run does not double count
- **WHEN** a `(ticker, as_of)` pair has three rows
- **THEN** only the lowest-`id` eligible, healthy row is analysed and the pair is counted as repeated

### Requirement: The report states coverage and hit-rates against baselines
For the analysed population the script SHALL print: (a) range coverage at the stated band (share with `inside_band = 1`, with n) next to the mean nominal `range_coverage`, coverage with `range_k` divided out, and the median of `abs(r5) * 100 / range_5s_pct`; (b) for directional verdicts, and separately for each agent's Round 1 and Round 2 directional stances, the hit-rate, the base rate over all analysed rows (the share of up moves for bull-lean, of down moves for bear-lean) and their difference, and the same test on `r5` minus `market_r5`, where `market_r5` is the equal-weight mean of `ln(close[target]/close[as_of])` over modelling-universe tickers with both bars, available only when at least 30 such tickers exist; (c) the verdict's hit-rate minus the technical-only hit-rate on the same rows. Non-directional verdicts and neutral stances SHALL NOT be given a hit-rate. Output SHALL use percentages, not log returns.

#### Scenario: Only directional verdicts have a hit-rate
- **WHEN** the analysed rows include `OBSERVE` and `SPLIT` verdicts
- **THEN** they appear in the funnel and in coverage but not in the directional hit-rate table

#### Scenario: Hit-rate shown with its baseline
- **WHEN** bull-lean verdicts hit 55% and 52% of analysed rows were up moves
- **THEN** the report prints hit 55%, base 52%, edge +3 points, and the demeaned equivalent or "unavailable (fewer than 30 market tickers)"

#### Scenario: Per-agent stances
- **WHEN** the News agent's Round 2 stance was bear on 40 analysed rows
- **THEN** the report prints that stance's hit-rate against the down-move base rate over the analysed rows, separately from its Round 1 figure

### Requirement: The report states the effective sample size honestly
Beside every rate the script SHALL print n and the naive Wilson 95% interval labelled as ignoring overlap and clustering. When the analysed `as_of` dates span at least 8 blocks of 20 market sessions it SHALL also print a cluster-bootstrap 95% interval (resampling blocks, fixed seed) and the implied effective n `p(1-p)/se^2`; otherwise it SHALL print that the clustered interval is not estimable. It SHALL print the number of distinct tickers, `as_of` dates and blocks, the effective observations needed for a half-width of 5 points at p = 0.5 (about 384), and a statement that the rows come from tickers the owner chose to analyse. It SHALL NOT present a bare hit-rate without its n.

#### Scenario: Few blocks
- **WHEN** the analysed rows span 3 blocks
- **THEN** the report prints the Wilson interval and "clustered interval not estimable: 3 blocks (need 8)"

#### Scenario: Many tickers, few dates
- **WHEN** 200 analysed rows come from 25 tickers on 8 `as_of` dates inside one block
- **THEN** the report prints 200 rows, 8 dates and 1 block, and the effective n it prints is not 200

### Requirement: The report cross-checks the log against report files
The script SHALL list `reports/YYYY-MM-DD_<TICKER>.md` files modified after the earliest `run_at` in `debate_log` for which no row has that ticker and `as_of`, as a possible failed write. It SHALL also list tickers with pending rows whose target session already exists in the market calendar, as tickers to refresh. Report files older than the first logged run SHALL be ignored.

#### Scenario: Missing log row
- **WHEN** a report file written after the first logged run has no matching `(ticker, as_of)` row
- **THEN** the report lists it under "possible failed log writes"

### Requirement: Existing report files are not backfilled
The change SHALL NOT import `reports/*.md` files that predate the log, and the script SHALL NOT parse report files into rows.

#### Scenario: Old reports stay out
- **WHEN** `reports/` holds files from before the log existed and `debate_log` is empty
- **THEN** running the script leaves `debate_log` empty
