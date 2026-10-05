# debate-panel-ui

## Purpose

TBD

## Requirements

### Requirement: DebatePanel has three progressive disclosure levels
The DebatePanel component SHALL implement three disclosure levels controlled by internal `disclosureLevel` state (`1`, `2`, `3`). The component renders Level 1 content always after an analysis has run; Level 2 and Level 3 expand in place without page navigation.

- **Level 1**: Verdict badge, agreement label ("2 of 3 agents"), per-agent stance icons, disclaimer (Rule 6), "Show reasoning" toggle
- **Level 2**: Per-agent card (stance + bullet reasoning), key tension block, "Full debate" toggle
- **Level 3**: Full Round 1 positions, Round 2 responses, synthesiser reasoning, "Export to .md" button

#### Scenario: User sees verdict at a glance
- **WHEN** an analysis has completed and the panel is at Level 1
- **THEN** verdict badge, agreement label, and three stance icons are visible without scrolling or clicking

#### Scenario: User expands to reasoning
- **WHEN** user clicks "Show reasoning" at Level 1
- **THEN** Level 2 content (agent cards + key tension) is revealed below Level 1 content; Level 1 content remains visible

#### Scenario: User collapses back to Level 1
- **WHEN** user clicks "Show reasoning" again at Level 2
- **THEN** Level 2 content collapses; Level 1 remains

### Requirement: DebatePanel shows "not run" state before first analysis
Before the first analysis is triggered for a selected ticker, the panel SHALL show an "Analyse" button and a brief description of what the analysis does. It MUST NOT show placeholder N/A values (unlike the old AIInsightPanel). The disclaimer (Rule 6) IS shown in the not-run state.

#### Scenario: Ticker selected, no analysis yet
- **WHEN** a ticker is selected in the ticker panel and no debate has been run for it this session
- **THEN** the panel shows "Analyse [TICKER]" button and the disclaimer; no verdict, no agent stances

#### Scenario: Analysis in progress
- **WHEN** the user clicks "Analyse" and the backend is running the debate
- **THEN** the panel shows a loading state with per-stage labels: "Running agents…" then "Comparing positions…" then "Synthesising…"

### Requirement: Disclaimer is visible at Level 1 at all times (Rule 6)
The disclaimer text from `docs/DISCLAIMER.md` SHALL be rendered unconditionally at Level 1, including in the not-run state, the loading state, and all populated states. It MUST NOT be hidden behind a toggle, collapsed by default, or removed at any disclosure level.

#### Scenario: Disclaimer present in not-run state
- **WHEN** the panel is in not-run state (no analysis triggered)
- **THEN** the disclaimer is visible

#### Scenario: Disclaimer present at Level 3
- **WHEN** the panel is expanded to Level 3 (full transcript)
- **THEN** the disclaimer remains visible (it does not scroll away or collapse)

### Requirement: Agent cards use correct labels (Rule 5)
At Level 2, the TechnicalAgent card header SHALL read "Technical Signal". The NewsAgent card header SHALL read "News Context". The MacroAgent card header SHALL read "Macro". The label "Market Sentiment" MUST NOT appear anywhere in the DebatePanel.

#### Scenario: Label enforcement in agent cards
- **WHEN** the panel is at Level 2 showing all three agent cards
- **THEN** card headers are exactly "Technical Signal", "News Context", "Macro" — not "Sentiment", "Market Sentiment", or any other variant

### Requirement: Feature flag gates the DebatePanel rollout
The DebatePanel SHALL be rendered only when the `VITE_DEBATE_PANEL_ENABLED` environment variable is `true`. When the flag is `false`, the existing `AIInsightPanel` is rendered instead. This allows rollback without code change.

#### Scenario: Feature flag enabled
- **WHEN** `VITE_DEBATE_PANEL_ENABLED=true`
- **THEN** DebatePanel replaces AIInsightPanel in the dashboard layout

#### Scenario: Feature flag disabled
- **WHEN** `VITE_DEBATE_PANEL_ENABLED=false` or unset
- **THEN** AIInsightPanel is rendered as before; DebatePanel is not mounted
