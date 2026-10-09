## MODIFIED Requirements

### Requirement: Export service writes a structured markdown file per analysis
The export service SHALL write `reports/YYYY-MM-DD_<TICKER>.md` at the repo root after every completed debate. If a report for the same ticker and date already exists, it SHALL be overwritten (re-running the analysis on the same day replaces the previous result). The file uses the structure defined by "Markdown export structure is NotebookLM-optimised". Report files written before this structure existed are not rewritten, renamed or parsed.

#### Scenario: Successful export
- **WHEN** a `DebateResult` is returned by the debate engine
- **THEN** a file is written at `reports/<date>_<ticker>.md` with Summary, Agent Positions table and Agent Reasoning sections

#### Scenario: Re-analysis on same day
- **WHEN** `POST /tickers/{ticker}/debate` is called twice on the same calendar day for the same ticker
- **THEN** the second result overwrites the first `.md` file; the backend returns the new result

#### Scenario: Older report files are left alone
- **WHEN** a report is written for one ticker and date and `reports/` holds files for other tickers or dates in the earlier structure
- **THEN** those files are unchanged

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

    ## Agent Reasoning
    ### Technical Signal (<stance>)
    ...
    ### News Context (<stance>)
    ...
    ### Macro (<stance>)
    ...

    ---
    <full disclaimer from docs/DISCLAIMER.md, one plain paragraph>

The report SHALL contain no Key Tension section, no Round heading and no Synthesis section. The Key reasoning cell is the agent's first reasoning bullet.

#### Scenario: NotebookLM summary query
- **WHEN** a user queries NotebookLM "what was the verdict for VCB on 04 Oct 2026?"
- **THEN** the Summary section provides a complete answer without requiring the Agent Reasoning section

#### Scenario: NotebookLM detail query
- **WHEN** a user queries NotebookLM "what did the news agent say about VCB on 04 Oct 2026?"
- **THEN** the Agent Reasoning section provides the NewsAgent's complete position

#### Scenario: Sections appear in the documented order
- **WHEN** a report is generated for a completed debate
- **THEN** the file contains, in this order: the title line `# <TICKER> · <DATE>`, the Summary, Agent Positions and Agent Reasoning sections (the last holding one block per agent, in the order Technical Signal, News Context, Macro), a `---` rule, and the disclaimer line

#### Scenario: No removed sections
- **WHEN** a report is generated for any completed debate
- **THEN** it contains no `## Key Tension` heading, no heading containing "Round" and no `### Synthesis` heading

#### Scenario: Volatility range is omitted when unavailable
- **WHEN** the debate result has no volatility range (the Technical agent could not compute one)
- **THEN** the Summary section omits the Volatility range line entirely, with no placeholder value

#### Scenario: Three-way split names its positions
- **WHEN** the agreement level is `split` (the three agents hold three different stances)
- **THEN** the Agreement line reads `**Agreement**: Split (3 different positions)`, not a count of agreeing agents

#### Scenario: Majority and unanimous count the agreeing agents
- **WHEN** the agreement level is `majority` or `unanimous`
- **THEN** the Agreement line reads `Majority (2 of 3 agents)` or `Unanimous (3 of 3 agents)` respectively

### Requirement: Export names the data date, data age and degraded agents
The Summary section SHALL contain a line `**Data as of**: <data_as_of> (<N> sessions old)` (or `(current)` at age 0) and, when `agents_degraded` is not empty, a line `**Unavailable agents**: <label> (<reason text>), ...` using the agent labels of the Agent Positions table. For a run with degraded agents the Agreement line SHALL read `<N> of <M> live agents (<K> unavailable)` in place of the `(N of 3 agents)` form, or `Split (2 different positions, <K> unavailable)` when two live agents disagree. In the Agent Positions table and the Agent Reasoning section a degraded agent's stance cell SHALL read `Unavailable` and its reasoning SHALL be marked not counted.

#### Scenario: One agent unavailable
- **WHEN** News is degraded and Technical and Macro are `bull`
- **THEN** the Summary contains `**Unavailable agents**: News Context (...)` and `**Agreement**: 2 of 2 live agents (1 unavailable)`

#### Scenario: Data age line
- **WHEN** `data_as_of = "2026-10-02"` and `data_age_sessions = 2`
- **THEN** the Summary contains `**Data as of**: 2026-10-02 (2 sessions old)`

#### Scenario: No degraded agents
- **WHEN** `agents_degraded` is empty
- **THEN** no Unavailable agents line is written and the Agreement line follows the existing requirement

### Requirement: Report marks language-model-written sections (Rule 5)
The first line under the `## Agent Positions` heading SHALL be `News Context reasoning is written by a language model; Technical Signal and Macro reasoning are computed values.`, the same string the panel shows. No other fixed sentence of the report SHALL describe the reasoning as written by a language model.

#### Scenario: Note present
- **WHEN** a report is generated
- **THEN** the line directly after `## Agent Positions` is that sentence

#### Scenario: The earlier sentence is gone
- **WHEN** a report is generated
- **THEN** it does not contain "key tension and synthesis are written by a language model"
