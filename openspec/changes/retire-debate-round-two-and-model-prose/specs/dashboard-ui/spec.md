## MODIFIED Requirements

### Requirement: Layout mode follows the viewport width and each component renders in one place
The dashboard SHALL choose one layout mode from the viewport width: `wide` (1440 px and up), `collapsed` (1144 to 1439 px), `drawer` (768 to 1143 px) or `phone` (below 768 px). The breakpoints in the stylesheet and in the script that selects the mode SHALL be equal, and a test SHALL fail if they differ. In `collapsed` mode the Rail SHALL be `--rail-w-min` (56 px) wide and show symbols only. In `drawer` mode the Rail SHALL be a drawer opened from a "Tickers" button in the topbar, and the Verdict panel SHALL be a full-width strip between the chart and the Debate matrix: the typical move and its range check at the left, the verdict with Agreement and the stance chips at the right, and the data line, the report-saved line and the disclaimer in a full-width row under them. In `phone` mode the page SHALL be one column ordered: the typical move and its range check, the chart (240 px high, the chart history control above it), the verdict with Agreement and the stance chips, then the Debate matrix as three tabs. The Debate matrix SHALL keep three columns down to 768 px, each at least 220 px wide. A component whose content is the only place a figure may appear (the range check, the disclaimer) SHALL be rendered once in every mode, never twice with one hidden.

#### Scenario: Collapsed Rail keeps three Debate columns
- **WHEN** the viewport is 1144 px wide with a ticker selected and a result present
- **THEN** the Rail is 56 px wide, the Verdict panel is 340 px wide, and the Debate matrix shows three agent columns each at least 220 px wide

#### Scenario: Drawer mode moves the Verdict panel between chart and Debate
- **WHEN** the viewport is 900 px wide
- **THEN** the Verdict panel is a strip in the flow after the chart and before the Debate matrix with the range block at the left and the verdict at the right, and the Rail is reachable only through the topbar "Tickers" button

#### Scenario: Phone mode puts the typical move first
- **WHEN** the viewport is 390 px wide and a ticker with a served band is selected
- **THEN** the typical 5-session move and its range check appear before the chart in reading order, and the Debate matrix is a tablist of three agent tabs

#### Scenario: One copy of each single-place element
- **WHEN** the dashboard renders in each of the four modes with a result present
- **THEN** the range check text and the inline disclaimer each occur exactly once in the Verdict panel in every mode

#### Scenario: Breakpoints cannot drift
- **WHEN** the breakpoint constants in the layout script are compared with the `@media` widths in the layout stylesheet
- **THEN** they are equal, and the test fails if either changes alone

### Requirement: Token colour pairs meet the contrast the design claims
Every foreground and background pair the design relies on SHALL meet its contrast ratio in both themes, measured on the dashboard's actual stylesheet: 4.5:1 for text (ink and muted ink on each of the three surfaces; accent text on the page and panel surfaces; the on-accent text on the accent fill; up and down ink on the panel surface and on their own tinted backgrounds; the warn ink and the warn border colour on the warn background, which are the design's tokens for a notice and which no element uses while Key tension is removed) and 3:1 for non-text (the strong line on the page and panel surfaces; the candle colours on the panel surface; the focus ring on every surface it appears on). A test SHALL compute these ratios from the stylesheet's token values and fail if any pair falls below its requirement.

#### Scenario: Contrast is computed from the real stylesheet
- **WHEN** the contrast test reads the dashboard's token stylesheet
- **THEN** it resolves both themes' values and asserts each pair against its 3:1 or 4.5:1 requirement

#### Scenario: A token edit that breaks a pair fails the test
- **WHEN** a text token is changed so that its ratio on a surface drops below 4.5:1
- **THEN** the contrast test fails and names the pair and the theme

#### Scenario: No element uses the warn tokens
- **WHEN** the component stylesheets are read
- **THEN** none of them refers to a `--warn-` token
