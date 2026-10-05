## MODIFIED Requirements

### Requirement: Dashboard renders AI insight panel for selected ticker
The dashboard SHALL render the `DebatePanel` component in the AI insight panel region when `VITE_DEBATE_PANEL_ENABLED=true`, replacing the `AIInsightPanel`. When the flag is false or unset, `AIInsightPanel` is rendered unchanged. The panel region's layout dimensions and grid position are unchanged — only the component rendered within it changes.

#### Scenario: Feature flag enabled — DebatePanel shown
- **WHEN** `VITE_DEBATE_PANEL_ENABLED=true` and a ticker is selected
- **THEN** DebatePanel is rendered in the AI insight panel region; AIInsightPanel is not mounted

#### Scenario: Feature flag disabled — AIInsightPanel shown
- **WHEN** `VITE_DEBATE_PANEL_ENABLED=false` or unset and a ticker is selected
- **THEN** AIInsightPanel is rendered as before; no change to existing behaviour
