## ADDED Requirements

### Requirement: Panel shows the data date and age with every result
At Level 1 of every populated result, the panel SHALL show the data date and its age in sessions, from `data_as_of` and `data_age_sessions`, in text such as "Data as of 2026-10-02 · 2 sessions old". At age 0 it reads "Data as of <date> · current". The line SHALL NOT use `as_of` as an analysis date, and SHALL NOT rely on colour alone.

#### Scenario: Result with data two sessions old
- **WHEN** a result has `data_as_of = "2026-10-02"` and `data_age_sessions = 2`
- **THEN** Level 1 shows "Data as of 2026-10-02 · 2 sessions old" without expanding anything

#### Scenario: Current data
- **WHEN** `data_age_sessions = 0`
- **THEN** the line reads "Data as of <date> · current"

### Requirement: Panel marks degraded agents and states agreement over live agents
For every agent in `agents_degraded` the panel SHALL replace its stance arrow in the Level 1 stance row with an "unavailable" marker (text and icon) and SHALL show a marker and a plain-language reason on its Level 2 card and in Level 3 (`agent_error`: "The agent failed to run."; `no_input`: "No usable input data."; `llm_failed`: "The language-model analysis failed."; `round2_failed`: "Round 2 failed; its Round 1 position is shown but not counted."). The agreement text SHALL count only live agents, as "N of M live agents", followed by "(K unavailable)" when K is above 0; a split of two live agents reads "Split — 2 different positions". The word "unanimous" SHALL NOT appear when any agent is degraded.

#### Scenario: One agent degraded
- **WHEN** News is degraded and Technical and Macro are `bull`
- **THEN** the stance row shows News as unavailable, the agreement text reads "2 of 2 live agents (1 unavailable)", and the Level 2 News card shows its reason

#### Scenario: Round 2 failure card
- **WHEN** an agent is `round2_failed`
- **THEN** its card shows its Round 1 position under the marker "Round 2 failed; its Round 1 position is shown but not counted."

#### Scenario: No degraded agents
- **WHEN** `agents_degraded` is empty
- **THEN** the agreement text is computed over all three agents as before and no unavailable marker appears

### Requirement: Panel shows an insufficient-data state with human-readable reasons
When `verdict` is `INSUFFICIENT_DATA` the panel SHALL render a dedicated state in place of the verdict, agreement, stance row, range, Level 2 and Level 3: the verdict badge using the display label defined for `INSUFFICIENT_DATA`, the data date and age when present, and one sentence per reason in `eligibility.reasons`, in order: `delisted` "This ticker is delisted."; `insufficient_history` "Not enough price history (at least 65 sessions are needed)."; `stale` "Stored prices are N sessions old. Refresh the ticker in the ticker panel, then analyse again."; `near_gap` "The price history has missing sessions."; `hard_quality_flag` "A recent price failed a data-quality check."; `indicators_missing` "Technical indicators are not available for the latest session.". When `eligibility.reasons` is empty and agents are degraded (an abstention after the agents ran), it SHALL instead list each degraded agent with its reason text and state that fewer than two agents produced a usable position. The state SHALL show no report-saved note, no Advice, Confidence or Sentiment value, and SHALL keep the disclaimer (Rule 6) visible. A "Re-analyse" action SHALL remain available.

#### Scenario: Stale ticker
- **WHEN** the result is `INSUFFICIENT_DATA` with reasons `["stale"]` and `data_age_sessions = 21`
- **THEN** the panel shows "Stored prices are 21 sessions old. Refresh the ticker in the ticker panel, then analyse again." and no stance row

#### Scenario: Several reasons
- **WHEN** reasons are `["delisted", "stale"]`
- **THEN** both sentences are shown, in that order

#### Scenario: Abstention after degraded agents
- **WHEN** reasons are empty and News and Macro are degraded
- **THEN** the panel lists both agents with their reasons and says fewer than two agents produced a usable position

#### Scenario: Disclaimer and no export note
- **WHEN** the insufficient-data state is shown
- **THEN** the disclaimer is visible and no "Report saved" text appears
