## ADDED Requirements

### Requirement: Export names the data date, data age and degraded agents
The Summary section SHALL contain a line `**Data as of**: <data_as_of> (<N> sessions old)` (or `(current)` at age 0) and, when `agents_degraded` is not empty, a line `**Unavailable agents**: <label> (<reason text>), ...` using the agent labels of the Agent Positions table. For a run with degraded agents the Agreement line SHALL read `<N> of <M> live agents (<K> unavailable)` in place of the `(N of 3 agents)` form, or `Split (2 different positions, <K> unavailable)` when two live agents disagree. In the Agent Positions table and the Full Debate sections a degraded agent's stance cell SHALL read `Unavailable` and its reasoning SHALL be marked not counted.

#### Scenario: One agent unavailable
- **WHEN** News is degraded and Technical and Macro are `bull`
- **THEN** the Summary contains `**Unavailable agents**: News Context (...)` and `**Agreement**: 2 of 2 live agents (1 unavailable)`

#### Scenario: Data age line
- **WHEN** `data_as_of = "2026-10-02"` and `data_age_sessions = 2`
- **THEN** the Summary contains `**Data as of**: 2026-10-02 (2 sessions old)`

#### Scenario: No degraded agents
- **WHEN** `agents_degraded` is empty
- **THEN** no Unavailable agents line is written and the Agreement line follows the existing requirement

### Requirement: Abstentions are not exported and the filename comes from as_of
The export service SHALL NOT write a report when the verdict is `INSUFFICIENT_DATA`, so a refusal cannot overwrite a real report of the same `as_of`. The filename and title date SHALL be `as_of`; the export SHALL NOT fall back to the system date.

#### Scenario: Abstention
- **WHEN** the verdict is `INSUFFICIENT_DATA`
- **THEN** no file is created or overwritten under `reports/`

#### Scenario: Stale data date in the filename
- **WHEN** `as_of = "2026-10-02"` and the system date is 2026-10-06
- **THEN** the file is `reports/2026-10-02_<TICKER>.md` and its title line carries 2026-10-02

#### Scenario: Earlier report survives a later refusal
- **WHEN** a report exists for `as_of` 2026-10-02 and a later run on the same `as_of` is refused for staleness
- **THEN** the earlier report is unchanged
