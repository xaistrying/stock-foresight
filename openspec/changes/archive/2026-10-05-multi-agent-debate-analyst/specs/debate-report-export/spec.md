## ADDED Requirements

### Requirement: Export service writes a structured markdown file per analysis
The export service SHALL write `reports/YYYY-MM-DD_<TICKER>.md` at the repo root after every completed debate. If a report for the same ticker and date already exists, it SHALL be overwritten (re-running the analysis on the same day replaces the previous result). The file uses the schema defined in design.md Decision 10.

#### Scenario: Successful export
- **WHEN** a `DebateResult` is returned by the debate engine
- **THEN** a file is written at `reports/<date>_<ticker>.md` with Summary, Agent Positions table, Key Tension, and Full Debate sections

#### Scenario: Re-analysis on same day
- **WHEN** `POST /tickers/{ticker}/debate` is called twice on the same calendar day for the same ticker
- **THEN** the second result overwrites the first `.md` file; the backend returns the new result

### Requirement: Markdown export structure is NotebookLM-optimised
The exported `.md` file SHALL use the following structure so that NotebookLM can answer both summary-level and detail-level queries from the same document:

    # <TICKER> · <DATE>

    ## Summary
    **Verdict**: <verdict>
    **Agreement**: <agreement_level> (<N> of 3 agents)
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
    *Technical observation — not investment advice. See docs/DISCLAIMER.md.*

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

### Requirement: Disclaimer appears at the bottom of every exported report (Rule 6)
Every exported `.md` file SHALL end with the disclaimer line: `*Technical observation — not investment advice. See docs/DISCLAIMER.md.*` (Rule 6). This line MUST be present regardless of verdict.

#### Scenario: Disclaimer in export
- **WHEN** any `.md` report is generated
- **THEN** the last non-empty line is the disclaimer, unconditionally
