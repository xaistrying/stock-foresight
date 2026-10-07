# debate-report-export

## Purpose

TBD

## Requirements

### Requirement: Export service writes a structured markdown file per analysis
The export service SHALL write `reports/YYYY-MM-DD_<TICKER>.md` at the repo root after every completed debate. If a report for the same ticker and date already exists, it SHALL be overwritten (re-running the analysis on the same day replaces the previous result). The file uses the schema defined in design.md Decision 10.

#### Scenario: Successful export
- **WHEN** a `DebateResult` is returned by the debate engine
- **THEN** a file is written at `reports/<date>_<ticker>.md` with Summary, Agent Positions table, Key Tension, and Full Debate sections

#### Scenario: Re-analysis on same day
- **WHEN** `POST /tickers/{ticker}/debate` is called twice on the same calendar day for the same ticker
- **THEN** the second result overwrites the first `.md` file; the backend returns the new result

### Requirement: Markdown export structure is NotebookLM-optimised
The exported `.md` file SHALL use the following structure so that NotebookLM can answer both summary-level and detail-level queries from the same document. The Agreement line counts the agents holding the majority stance, except for a three-way split, where it reads `Split (3 different positions)`:

    # <TICKER> · <DATE>

    ## Summary
    **Verdict**: <verdict>
    **Agreement**: <agreement_level> (<N> of 3 agents)   -- or: Split (3 different positions)
    **Agents**: Technical <icon> · News Context <icon> · Macro <icon>
    **Volatility range**: ±X.X% (5 trading sessions)

    ## Agent Positions
    | Agent | Stance | Key reasoning |
    |-------|--------|---------------|
    | Technical Signal | ... | ... |
    | News Context | ... | ... |
    | Macro | ... | ... |

    ## Key Tension
    <synthesiser key_tension paragraph>

    ## Full Debate
    ### Round 1 — Initial Positions
    #### Technical Signal
    ...
    #### News Context
    ...
    #### Macro
    ...
    ### Round 2 — Responses
    ...
    ### Synthesis
    ...

    ---
    <full disclaimer from docs/DISCLAIMER.md, one plain paragraph>

#### Scenario: NotebookLM summary query
- **WHEN** a user queries NotebookLM "what was the verdict for VCB on 04 Oct 2026?"
- **THEN** the Summary section provides a complete answer without requiring the Full Debate section

#### Scenario: NotebookLM detail query
- **WHEN** a user queries NotebookLM "what did the news agent say about VCB on 04 Oct 2026?"
- **THEN** the Full Debate section provides the NewsAgent's complete Round 1 and Round 2 positions

#### Scenario: Sections appear in the documented order
- **WHEN** a report is generated for a completed debate
- **THEN** the file contains, in this order: the title line `# <TICKER> · <DATE>`, the Summary, Agent Positions, Key Tension and Full Debate sections (the last holding Round 1 — Initial Positions, Round 2 — Responses and Synthesis), a `---` rule, and the disclaimer line

#### Scenario: Volatility range is omitted when unavailable
- **WHEN** the debate result has no volatility range (the Technical agent could not compute one)
- **THEN** the Summary section omits the Volatility range line entirely, with no placeholder value

#### Scenario: Three-way split names its positions
- **WHEN** the agreement level is `split` (the three agents hold three different stances)
- **THEN** the Agreement line reads `**Agreement**: Split (3 different positions)`, not a count of agreeing agents

#### Scenario: Majority and unanimous count the agreeing agents
- **WHEN** the agreement level is `majority` or `unanimous`
- **THEN** the Agreement line reads `Majority (2 of 3 agents)` or `Unanimous (3 of 3 agents)` respectively

### Requirement: Disclaimer appears at the bottom of every exported report (Rule 6)
Every exported `.md` file SHALL end with a `---` rule followed by the full disclaimer from `docs/DISCLAIMER.md` (the blockquote under "Full disclaimer"), written as one plain paragraph that is the last non-empty line, with no italics and no repo path (Rule 6). This replaces the last line of the template in "Markdown export structure is NotebookLM-optimised". The text SHALL equal the file's text after whitespace normalisation (blockquote lines joined with one space, whitespace collapsed), and a test SHALL fail if it does not. The footer MUST be present regardless of verdict.

#### Scenario: Disclaimer in export
- **WHEN** any `.md` report is generated
- **THEN** the last non-empty line is the full disclaimer text, unconditionally

#### Scenario: Footer matches the source file
- **WHEN** the export test reads `docs/DISCLAIMER.md` and a generated report
- **THEN** the report's last non-empty line equals the normalised "Full disclaimer" text, and the test fails if the file or the exporter's copy is edited alone

#### Scenario: Old one-line footer is gone
- **WHEN** a report is generated
- **THEN** it does not contain `See docs/DISCLAIMER.md`

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

### Requirement: Export Summary states the typical 5-session move and its coverage
The Summary section of an exported report SHALL contain, in place of the `**Volatility range**: ±X.X% (5 trading sessions)` line of the earlier template, the line `**Typical 5-session move**: ±X.X% (about 2 in 3 recent 5-session moves stayed within this range)` when `range_5s_pct` is not null and `range_coverage` is 0.68; the coverage phrase follows the same derivation as the panel ("about N%" for other values). When `range_coverage` is null the parenthetical SHALL read `(coverage not established for this stock)`. When `range_5s_pct` is null the line SHALL be omitted entirely with no placeholder. The line MUST NOT print `sigma_daily_pct` as a 5-session figure. This requirement supersedes the `**Volatility range**` template line and the scenario "Volatility range is omitted when unavailable" in the requirement "Markdown export structure is NotebookLM-optimised".

#### Scenario: Calibrated band in the report
- **WHEN** a report is written for a result with `range_5s_pct` 5.3 and `range_coverage` 0.68
- **THEN** the Summary contains `**Typical 5-session move**: ±5.3% (about 2 in 3 recent 5-session moves stayed within this range)` and no `**Volatility range**` line

#### Scenario: Uncalibrated band in the report
- **WHEN** `range_5s_pct` is 5.3 and `range_coverage` is null
- **THEN** the Summary line ends with `(coverage not established for this stock)`

#### Scenario: Band omitted when not served
- **WHEN** the debate result has `range_5s_pct` null
- **THEN** the Summary has no typical-move line and no placeholder

### Requirement: Report verdict line uses the display label (Rule 6)
The `**Verdict**:` line of the Summary SHALL show the verdict's display label from the table in the `debate-synthesiser` capability ("Verdict display labels are non-transactional (Rule 6)"), never the enum text. The Agreement line keeps the word "Agreement"; the report SHALL NOT use the word "Confidence" in fixed text.

#### Scenario: Label for each verdict
- **WHEN** a report is generated for `BUY_SIGNAL`
- **THEN** the Summary reads `**Verdict**: Bullish lean` and does not contain `BUY_SIGNAL`

#### Scenario: Split label
- **WHEN** a report is generated for `SPLIT`
- **THEN** the Summary reads `**Verdict**: Split — no consensus`

### Requirement: Report marks language-model-written sections (Rule 5)
The first line under the `## Agent Positions` heading SHALL be `Reasoning, key tension and synthesis are written by a language model.`, the same string the panel shows.

#### Scenario: Note present
- **WHEN** a report is generated
- **THEN** the line directly after `## Agent Positions` is that sentence

### Requirement: Fixed report text contains no transaction verbs (Rule 6)
All fixed report text (headings, labels, notes, verdict label), excluding the disclaimer footer and the agents' own reasoning, SHALL NOT contain "buy", "sell" or "hold" as whole words in any letter case, nor any verdict enum text.

#### Scenario: Guard over every verdict
- **WHEN** a report is generated for each verdict value from a fixture whose agent text avoids those words, and the footer is removed
- **THEN** a case-insensitive search for `\b(buy|sell|hold)\b` and for `[A-Z]+_SIGNAL` finds nothing
