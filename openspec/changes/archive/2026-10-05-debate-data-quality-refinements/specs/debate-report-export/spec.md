## MODIFIED Requirements

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

#### Scenario: Three-way split names its positions
- **WHEN** the agreement level is `split` (the three agents hold three different stances)
- **THEN** the Agreement line reads `**Agreement**: Split (3 different positions)`, not a count of agreeing agents

#### Scenario: Majority and unanimous count the agreeing agents
- **WHEN** the agreement level is `majority` or `unanimous`
- **THEN** the Agreement line reads `Majority (2 of 3 agents)` or `Unanimous (3 of 3 agents)` respectively
