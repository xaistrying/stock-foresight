## MODIFIED Requirements

### Requirement: Every debate run is recorded as one row in `debate_log`
The system SHALL keep a table `debate_log` in its own SQLite file, `backend/data/debate_log.db`, separate from the application database `app.db`, and SHALL insert one new row for every completed debate run (once per run, not once per request), including runs whose verdict is `INSUFFICIENT_DATA`, runs with degraded agents, and re-runs of the same ticker and `as_of`. The key is a surrogate `id INTEGER PRIMARY KEY AUTOINCREMENT`; there is no uniqueness on `(ticker, as_of)`. A row SHALL hold: `ticker`; `as_of` (NOT NULL); `run_at` (UTC, ISO-8601 with offset); `close_at_asof`; `data_age_sessions`; `eligible` and `eligibility_reasons` (JSON list); `agents_degraded` (JSON list); `sigma_daily_pct`, `range_5s_pct`, `range_k`, `range_coverage`; `r1_technical`, `r1_news`, `r1_macro`, `r2_technical`, `r2_news`, `r2_macro`; `verdict`, `agreement_level`; `model_sha256`, `llm_provider`, `llm_model`, `llm_effort`, `code_rev`; `evidence` (JSON text); and the nullable outcome columns `outcome_status`, `scored_at`, `date_t5`, `close_asof_at_scoring`, `close_t5`, `r5`, `inside_band`, `direction_hit`. Band columns SHALL be NULL when the band was unavailable, and the `r1_*` stance columns SHALL be NULL when the agents did not run. The `r2_*` columns are kept so that rows written while a second round existed read unchanged, and SHALL be NULL in every row written after that round was removed; the verdict and `agreement_level` of such a row are the vote over its `r1_*` stances. No column is added or altered, and no existing row is rewritten.

#### Scenario: A completed run is logged
- **WHEN** a debate for `VCB` completes with `data_as_of = 2026-10-06`, verdict `BUY_SIGNAL` and all agents healthy
- **THEN** one `debate_log` row exists with `ticker = 'VCB'`, `as_of = '2026-10-06'`, the three `r1_*` stances, NULL `r2_*` stances, the verdict, the band values from the result, and every outcome column NULL

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

#### Scenario: Older rows are untouched
- **WHEN** the log holds rows with `r2_*` stances written before this change and a new run is logged
- **THEN** the older rows are unchanged in every column afterwards and the new row's `r2_*` columns are NULL

### Requirement: The report states coverage and hit-rates against baselines
For the analysed population the script SHALL print: (a) range coverage at the stated band (share with `inside_band = 1`, with n) next to the mean nominal `range_coverage`, coverage with `range_k` divided out, and the median of `abs(r5) * 100 / range_5s_pct`; (b) for directional verdicts, reported separately for each vote basis as the requirement "Verdict statistics are reported separately for each vote basis" defines, and separately for each agent's Round 1 directional stances over all analysed rows and its Round 2 directional stances over the rows that have them, the hit-rate, the base rate over all analysed rows (the share of up moves for bull-lean, of down moves for bear-lean) and their difference, and the same test on `r5` minus `market_r5`, where `market_r5` is the equal-weight mean of `ln(close[target]/close[as_of])` over modelling-universe tickers with both bars, available only when at least 30 such tickers exist; (c) the verdict's hit-rate minus the technical-only hit-rate on the same rows, for each vote basis. Non-directional verdicts and neutral stances SHALL NOT be given a hit-rate. Output SHALL use percentages, not log returns.

#### Scenario: Only directional verdicts have a hit-rate
- **WHEN** the analysed rows include `OBSERVE` and `SPLIT` verdicts
- **THEN** they appear in the funnel and in coverage but not in the directional hit-rate table

#### Scenario: Hit-rate shown with its baseline
- **WHEN** bull-lean verdicts hit 55% and 52% of analysed rows were up moves
- **THEN** the report prints hit 55%, base 52%, edge +3 points, and the demeaned equivalent or "unavailable (fewer than 30 market tickers)"

#### Scenario: Per-agent stances
- **WHEN** the News agent's Round 2 stance was bear on 40 analysed older rows
- **THEN** the report prints that stance's hit-rate against the down-move base rate over the analysed rows, separately from its Round 1 figure

#### Scenario: Rows with no second round
- **WHEN** an analysed row has NULL `r2_*` stances
- **THEN** it contributes to every Round 1 figure and to no Round 2 figure, and the report does not fail

## ADDED Requirements

### Requirement: Verdict statistics are reported separately for each vote basis
A row's **vote basis** SHALL be `round2` when any of its `r2_technical`, `r2_news` and `r2_macro` is not NULL, and `round1` when all three are NULL; inside the analysed population every agent is live, so an older row has all three `r2_*` stances and a newer row has none. The report SHALL compute and print every statistic that depends on the verdict (the directional hit-rates of the verdict, with their baselines, and the verdict-minus-technical figure) once per vote basis, each group with its n and the distinct `code_rev` values of its rows, and SHALL NOT print a verdict figure pooled across the two bases. Range coverage, the funnel, the sample-size lines and the per-agent Round 1 tables do not depend on the vote and SHALL stay pooled. A basis with no analysed rows SHALL be reported as having none, not omitted silently.

#### Scenario: Two bases, two figures
- **WHEN** the analysed rows include older rows with `r2_*` stances and newer rows with NULL `r2_*`
- **THEN** the report prints the verdict hit-rates for the `round2` rows and for the `round1` rows as separate groups, each with its n and `code_rev` values, and no pooled verdict hit-rate

#### Scenario: One basis only
- **WHEN** every analysed row has NULL `r2_*` stances
- **THEN** the report prints the `round1` group and states that no analysed row was voted on Round 2 stances

#### Scenario: Coverage stays pooled
- **WHEN** the analysed rows span both bases
- **THEN** range coverage is printed once over all analysed rows
