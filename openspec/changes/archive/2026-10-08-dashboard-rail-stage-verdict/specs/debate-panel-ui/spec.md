## ADDED Requirements

### Requirement: The Verdict panel is in one of six states, chosen from the ticker's eligibility and the run's status
The Verdict panel (the component the requirements below call "the panel" and "DebatePanel" is this panel) SHALL be in exactly one of six states for the selected ticker: **ready** (the ticker can be analysed and no run exists), **running** (a run for the ticker is in flight), **result** (a run has finished with a verdict), **one agent unavailable** (a result in which one agent did not vote), **insufficient data** (the ticker cannot be analysed, or a run abstained) and **failed** (the latest run ended in an error; a kept result stays visible beneath it). With no ticker selected the panel SHALL show a prompt to select one. The state SHALL be chosen without a request from, in order: the latest run's status and error, the kept result, and the ticker's eligibility (the catalog entry's `eligibility`, else `GET /tickers/{ticker}/range`'s `status` and `reasons`). The range block (see `dashboard-ui`) SHALL be visible above every state, and the disclaimer with "About this analysis" SHALL be visible in every state, including with no ticker selected.

#### Scenario: Ready for an eligible ticker
- **WHEN** a ticker whose `eligibility.eligible` is true is selected and no run exists
- **THEN** the panel is ready: the range block, the Analyse action and the notice of its duration are shown, and no `POST /debate` has been issued

#### Scenario: Ineligible ticker is insufficient before any run
- **WHEN** a ticker whose `eligibility.reasons` is `["stale"]` is selected and no run exists
- **THEN** the panel is in the insufficient-data state with no request to the debate endpoint

#### Scenario: A run in flight is running
- **WHEN** a run for the selected ticker is pending
- **THEN** the panel is running, whatever a kept result or the eligibility says

#### Scenario: No ticker selected
- **WHEN** no ticker is selected
- **THEN** the panel shows a prompt to select a ticker, the range block's placeholders and the disclaimer

### Requirement: The ready state offers Analyse and says how long it takes
In the ready state the panel SHALL show an "Analyse {TICKER}" action and, before the run starts, the sentence "Analysis takes about 45 seconds." The duration SHALL come from one named constant. The panel SHALL NOT show placeholder verdict values in this state. In the insufficient-data state for a ticker the catalog or `/range` already says is ineligible, the panel SHALL NOT offer Analyse.

#### Scenario: Notice before the run
- **WHEN** a ticker that can be analysed is selected
- **THEN** the panel shows "Analyse TCB" and "Analysis takes about 45 seconds." and no verdict, Agreement or stance

#### Scenario: No Analyse for an ineligible ticker
- **WHEN** the selected ticker's `eligibility.eligible` is false
- **THEN** the panel shows a Refresh action and no Analyse action

### Requirement: The result state shows the verdict, Agreement, stance chips, Key tension, Synthesis and the data line
A result SHALL show, in order: the verdict badge (the display label from the `debate-synthesiser` table), Agreement, one stance chip per agent for its Round 2 position, Key tension, Synthesis, the data line, "Analysed HH:MM" (the time the result was produced), the report-saved line when it applies, and a Re-analyse action. The data line SHALL read "Data as of 2026-10-02 · 2 sessions old" from `data_as_of` and `data_age_sessions` ("· current" at age 0; the date alone when the age is absent), SHALL NOT use `as_of` as an analysis date and SHALL NOT rely on colour alone. Synthesis SHALL be shown as the synthesiser's paragraph without a disclosure control. None of these SHALL be hidden behind a toggle.

#### Scenario: Everything is visible at once
- **WHEN** a result with a verdict `BUY_SIGNAL`, three live agents and a key tension is shown
- **THEN** the badge, Agreement, three stance chips, Key tension, Synthesis and the data line are all visible without a click

#### Scenario: Data line with age
- **WHEN** a result has `data_as_of` "2026-10-02" and `data_age_sessions` 2
- **THEN** the panel shows "Data as of 2026-10-02 · 2 sessions old"

#### Scenario: Current data
- **WHEN** `data_age_sessions` is 0
- **THEN** the data line reads "Data as of <date> · current"

#### Scenario: Older server payload
- **WHEN** a payload carries no `data_as_of`
- **THEN** the panel still renders and shows no data line

### Requirement: Verdict and stance marks pair an arrow with the word and never rely on colour alone
Each stance chip SHALL show the agent's label, an arrow glyph and the stance word: "↑ Bullish", "→ Neutral" or "↓ Bearish" (Rule 6: labels are observations, never instructions). A bullish chip SHALL use the up ink on the up background, a bearish chip the down ink on the down background, a neutral chip the primary ink on the inset surface. The verdict badge SHALL show the display label unchanged and, for the two bullish labels an up arrow, for the two bearish labels a down arrow, and no arrow for Observe, Split or Insufficient data; the glyph SHALL be a separate element hidden from assistive technology so the badge's accessible text is exactly the display label. Observe and Split SHALL use the primary ink on the inset surface; Insufficient data SHALL use the muted ink on the inset surface with a dashed strong border. The warn colours SHALL NOT be used on any chip or badge.

#### Scenario: Chip carries glyph and word
- **WHEN** Round 2 stances are bull, neutral and bear
- **THEN** the chips read "Technical Signal ↑ Bullish", "News Context → Neutral" and "Macro ↓ Bearish"

#### Scenario: Badge text is the display label
- **WHEN** the verdict is `STRONG_CAUTION_SIGNAL`
- **THEN** the badge's accessible text is exactly "Strong bearish lean", with a separate hidden "↓" glyph, and no enum text appears

#### Scenario: No arrow on a non-directional verdict
- **WHEN** the verdict is `OBSERVE`, `SPLIT` or `INSUFFICIENT_DATA`
- **THEN** the badge shows its label and no arrow

#### Scenario: Warn colours are not on marks
- **WHEN** the panel shows an unavailable agent, a Split verdict or the insufficient-data badge
- **THEN** none uses a warn colour

### Requirement: Unavailable agents are marked, and Agreement counts only the agents that answered and names those that did not
For every agent in `agents_degraded` the panel SHALL replace its stance chip with an "unavailable" chip (text, dashed strong border, no warn colour) and the Debate matrix SHALL show an Unavailable card with a plain-language reason (`agent_error`: "The agent failed to run."; `no_input`: "No usable input data."; `llm_failed`: "The language-model analysis failed."; `round2_failed`: "Round 2 failed; its Round 1 position is shown but not counted."). Agreement SHALL count only live agents, as "N of M live agents", followed by the unavailable agents' labels, e.g. "Agreement: 2 of 2 live agents (News Context unavailable)"; a split of two live agents reads "Agreement: Split — 2 different positions"; with no unavailable agent it reads as the shipped three-agent forms: `Agreement: Unanimous — 3 of 3 agents`, `Agreement: Majority — 2 of 3 agents` or `Agreement: Split — 3 different positions`. The word "unanimous" SHALL NOT appear when any agent is unavailable. The panel SHALL show whatever verdict the server sends; with fewer than two live agents the server's verdict is `INSUFFICIENT_DATA` and the panel is in the insufficient-data state.

#### Scenario: One agent unavailable
- **WHEN** News is degraded and Technical and Macro are `bull`
- **THEN** the chips show News Context as unavailable, Agreement reads "Agreement: 2 of 2 live agents (News Context unavailable)", and the matrix shows the Unavailable card for News Context

#### Scenario: Two live agents disagree
- **WHEN** one agent is degraded and the two live agents are `bull` and `bear`
- **THEN** Agreement reads "Agreement: Split — 2 different positions (1 unavailable)" and the verdict label is the server's `SPLIT` label

#### Scenario: No agent unavailable
- **WHEN** `agents_degraded` is empty and the agreement level is `majority` with two agents on the majority stance
- **THEN** Agreement reads "Agreement: Majority — 2 of 3 agents" and no unavailable marker appears

#### Scenario: Round 2 failure
- **WHEN** an agent is `round2_failed`
- **THEN** its Round 1 card shows its position normally and its Round 2 card is the Unavailable card with the "Round 2 failed; its Round 1 position is shown but not counted." reason

### Requirement: The insufficient-data state gives reasons in plain words and offers Refresh, before or after a run
When the ticker's eligibility has reasons, or when a run's `verdict` is `INSUFFICIENT_DATA`, the panel SHALL render the insufficient-data state in place of the verdict, Agreement, stance chips, Key tension and Synthesis: the badge using the `INSUFFICIENT_DATA` display label, the data date and age when known, and one sentence per reason, in the order given: `delisted` "This ticker is delisted."; `insufficient_history` "Not enough price history (at least 65 sessions are needed)."; `stale` "Stored prices are N sessions old. Refresh the ticker, then analyse again." (N from `eligibility.age_sessions` or `data_age_sessions`; "many" when absent); `near_gap` "The price history has missing sessions."; `hard_quality_flag` "A recent price failed a data-quality check."; `indicators_missing` "Technical indicators are not available for the latest session.". When the reasons come from a run that abstained after the agents ran (empty reasons, degraded agents) the panel SHALL list each degraded agent with its reason and say that fewer than two agents produced a usable position. The state SHALL offer a "Refresh {TICKER}" action that calls `POST /tickers/{ticker}/load` as the Rail's Refresh does (disabled while that load is in flight, the same per-status messages), SHALL show no report-saved note, no Advice, Confidence or Sentiment value, and SHALL keep the disclaimer visible. The range block SHALL stay visible above it; it shows a band whenever `/range` serves one.

#### Scenario: Stale ticker before any run
- **WHEN** the selected ticker's `eligibility` is `{eligible: false, reasons: ["stale"], age_sessions: 21}` and no run exists
- **THEN** the panel shows "Stored prices are 21 sessions old. Refresh the ticker, then analyse again.", a Refresh action, no Analyse action and no stance chip

#### Scenario: Several reasons
- **WHEN** reasons are `["delisted", "stale"]`
- **THEN** both sentences are shown, in that order

#### Scenario: Abstention after degraded agents
- **WHEN** a run returns `INSUFFICIENT_DATA` with empty reasons and News and Macro degraded
- **THEN** the panel lists both agents with their reasons and says fewer than two agents produced a usable position

#### Scenario: Refresh recovers the ticker
- **WHEN** the user activates Refresh and the load completes with `status: "ok"`
- **THEN** the catalog, history and range are refetched and the panel leaves the insufficient-data state if the refreshed data is eligible

#### Scenario: Disclaimer and no export note
- **WHEN** the insufficient-data state is shown
- **THEN** the disclaimer is visible and no "Report saved" text appears

### Requirement: The Debate matrix shows three agents by two rounds, with cards clamped to five lines
The Stage SHALL contain a Debate matrix below the chart: three agent columns (Technical Signal, News Context, Macro, in that order; Rule 5) by two rows headed "Round 1 · Initial positions" and "Round 2 · Responses", each cell one card with the agent's label, its stance as glyph and word, and its reasoning bullets. Cards SHALL be aligned by row. A card's text SHALL be clamped to five lines of body text with a "Show more" button (`aria-expanded`, `aria-controls`; "Show less" when open), shown only when the text overflows, and the clamp SHALL keep list semantics. An agent that did not answer SHALL get a card with a dashed strong border reading "Unavailable — did not vote" and its plain-language reason. The matrix SHALL NOT print all rounds of all agents as one scrolling text column. Before a result it SHALL show a one-line prompt under its heading; while a run is in flight it SHALL show six skeleton cells hidden from assistive technology; for a refusal in which no agent ran it SHALL say that no debate was run. At 768 px and up the three columns SHALL stay; below 768 px the matrix SHALL be a tablist of three agent tabs (`role="tablist"` named "Agents", `role="tab"` with `aria-selected` and `aria-controls`, `role="tabpanel"`; Left, Right, Home and End move between tabs) with Round 1 and Round 2 stacked inside each panel. Agent text SHALL be rendered as text, with Markdown bold shown as bold and nothing interpreted as HTML.

#### Scenario: Three by two
- **WHEN** a result with three live agents is shown at 1440 px
- **THEN** the matrix has two rows headed "Round 1 · Initial positions" and "Round 2 · Responses" and three cards in each, in the order Technical Signal, News Context, Macro

#### Scenario: Long text is clamped
- **WHEN** a card's reasoning is longer than five lines
- **THEN** the card shows five lines and a "Show more" button with `aria-expanded="false"`, and activating it shows the whole text with `aria-expanded="true"`

#### Scenario: Short text has no button
- **WHEN** a card's reasoning fits in five lines
- **THEN** no "Show more" button is shown

#### Scenario: Unavailable card
- **WHEN** News is degraded with `agent_error`
- **THEN** its Round 1 and Round 2 cells read "Unavailable — did not vote" with "The agent failed to run." and a dashed strong border

#### Scenario: Phone tabs
- **WHEN** the viewport is 390 px wide
- **THEN** the matrix is a tablist with three tabs, the selected tab's panel holds that agent's Round 1 card above its Round 2 card, and the arrow keys move between tabs

#### Scenario: Before and while running
- **WHEN** no result exists, and then a run is pending
- **THEN** the matrix shows its prompt, and then six skeleton cells with no accessible text

#### Scenario: Provenance labels
- **WHEN** the matrix is shown
- **THEN** its card headings are exactly "Technical Signal", "News Context" and "Macro", and "Market Sentiment" appears nowhere

### Requirement: Language-model-written text is marked as such and the disclaimer accompanies agent reasoning (Rule 5, Rule 6)
The sentence `Reasoning, key tension and synthesis are written by a language model.` SHALL be shown above the Debate matrix's cards and above Key tension and Synthesis in the Verdict panel whenever a result is displayed. The inline disclaimer from `lib/disclaimer.js` SHALL be shown under the Debate matrix's heading in every state in which the matrix is displayed, in addition to the Verdict panel's own, since the matrix displays agent reasoning outside the Verdict panel.

#### Scenario: Note in both places
- **WHEN** a result is displayed
- **THEN** the sentence appears above the matrix's cards and above Key tension, and the inline disclaimer is visible under the matrix heading

### Requirement: Key tension is shown in the Verdict panel only, and says when it is unavailable
Key tension SHALL be shown in the Verdict panel, in the warn colours (the only use of the warn background, border and ink), under a "Key tension" heading in the warn border colour (4.5:1 on the warn background in both themes) with the body in the warn ink, as the synthesiser's one or two sentences; it SHALL NOT be shown anywhere else. When `synthesis.key_tension` is null the block SHALL say "Key tension unavailable" and SHALL NOT present any text as the key tension.

#### Scenario: Key tension in the panel
- **WHEN** a result has `synthesis.key_tension` "Technical is bullish but Macro warns of foreign outflows."
- **THEN** the Verdict panel shows it under "Key tension" in the warn colours, and it appears nowhere in the Debate matrix

#### Scenario: Null key tension
- **WHEN** the result's `synthesis.key_tension` is null
- **THEN** the block shows "Key tension unavailable" and no other text as the key tension

### Requirement: The report-saved line appears only when the report was saved
The result state SHALL show "Report saved to reports/<report_file>" only when the result has `report_saved` true, using the `report_file` value from the response, in the Verdict panel's result area. When `report_saved` is false or absent the panel SHALL NOT claim a saved report, and the insufficient-data state SHALL NOT show the line.

#### Scenario: Report saved
- **WHEN** the result has `report_saved` true and `report_file` "2026-10-05_VPB.md"
- **THEN** the panel shows "Report saved to reports/2026-10-05_VPB.md"

#### Scenario: Export failed
- **WHEN** the result has `report_saved` false
- **THEN** the panel contains no "Report saved" text

### Requirement: The vote count is labelled "Agreement", never "Confidence" (Rule 4)
The panel SHALL show the vote count under the label "Agreement" in the forms of "Unavailable agents are marked, and Agreement counts only the agents that answered and names those that did not". Fixed text on the dashboard SHALL NOT use the word "Confidence" (any letter case) for it or for any other figure.

#### Scenario: Split
- **WHEN** the agreement level is `split` with three live agents
- **THEN** the panel shows `Agreement: Split — 3 different positions`

#### Scenario: No Confidence wording
- **WHEN** the dashboard is rendered in any state
- **THEN** a case-insensitive search of its fixed text for `confiden(ce|t)` finds nothing

### Requirement: Fixed dashboard text contains no transaction verbs, enum text or Confidence (Rule 6)
All fixed text of the Verdict panel, the Debate matrix, the Rail, the topbar and the Stage (labels, headings, buttons, notes, tags, messages), excluding the two disclaimer texts and the backend-supplied agent text, SHALL NOT contain "buy", "sell" or "hold" as whole words in any letter case, nor any verdict enum text such as `BUY_SIGNAL`, nor the word "Confidence". This guard is case-insensitive.

#### Scenario: Guard over every state and verdict
- **WHEN** the dashboard is rendered in every Verdict state and populated for each of the seven verdicts from a fixture whose agent text avoids those words, with the disclaimer texts removed
- **THEN** a case-insensitive search for `\b(buy|sell|hold)\b`, for `[A-Z]+_SIGNAL` and for `confiden(ce|t)` finds nothing

## REMOVED Requirements

### Requirement: DebatePanel has three progressive disclosure levels
**Reason**: The Verdict panel shows the verdict, Agreement, stances, Key tension and Synthesis at once, and the Debate matrix shows both rounds of every agent at once; the three levels and their toggles ("Show reasoning", "Full debate") no longer exist.
**Migration**: "The result state shows the verdict, Agreement, stance chips, Key tension, Synthesis and the data line" and "The Debate matrix shows three agents by two rounds, with cards clamped to five lines".

### Requirement: DebatePanel shows "not run" state before first analysis
**Reason**: The not-run state becomes the ready state, which also states the duration and is only shown for a ticker that can be analysed.
**Migration**: "The ready state offers Analyse and says how long it takes". The running label sequence stays in "DebatePanel shows the running stage and elapsed time".

### Requirement: Disclaimer is visible at Level 1 at all times (Rule 6)
**Reason**: It is worded in terms of Level 1 and Level 3, which no longer exist.
**Migration**: "The Verdict panel is in one of six states, chosen from the ticker's eligibility and the run's status" (disclaimer in every state), "Language-model-written text is marked as such and the disclaimer accompanies agent reasoning (Rule 5, Rule 6)" and, in `dashboard-ui`, "Disclaimer stays visible with the Verdict panel, the Debate matrix and the range block, with no visibility control".

### Requirement: Agent cards use correct labels (Rule 5)
**Reason**: Agent cards live in the Debate matrix, not at "Level 2".
**Migration**: The "Provenance labels" scenario of "The Debate matrix shows three agents by two rounds, with cards clamped to five lines".

### Requirement: Panel shows the data date and age with every result
**Reason**: It is worded in terms of Level 1; the data line is now part of the result state, and the Stage header states the date and age before any run.
**Migration**: "The result state shows the verdict, Agreement, stance chips, Key tension, Synthesis and the data line" and, in `dashboard-ui`, "Stage header states the ticker, last close and the data date and age before any debate runs".

### Requirement: Panel marks degraded agents and states agreement over live agents
**Reason**: It is worded in terms of the Level 1 stance row, Level 2 cards and Level 3, and the Agreement text now names the agents that did not answer.
**Migration**: "Unavailable agents are marked, and Agreement counts only the agents that answered and names those that did not".

### Requirement: Panel shows an insufficient-data state with human-readable reasons
**Reason**: The state is now also shown before any run (from eligibility), offers a Refresh action in place of text pointing at a ticker panel that no longer exists, and is worded without Levels.
**Migration**: "The insufficient-data state gives reasons in plain words and offers Refresh, before or after a run".

### Requirement: Panel range line states the typical 5-session move and its coverage
**Reason**: The typical 5-session move and its coverage are the first element of the Verdict panel (the range block); a second line in the debate result would show the band twice, with one decimal where the block shows two.
**Migration**: `dashboard-ui` "Verdict panel's range block states the typical 5-session move, its range check and its coverage". "Range hit-rate, where shown, is labelled as a measurement (Rule 4)" is unchanged and governs the block's label and wording.

### Requirement: Vote count is labelled "Agreement", never "Confidence" (Rule 4)
**Reason**: It says "Level 1 SHALL show"; the labelling rule is unchanged and now covers the whole dashboard.
**Migration**: "The vote count is labelled "Agreement", never "Confidence" (Rule 4)".

### Requirement: Language-model-written text is marked as such (Rule 5)
**Reason**: It places the note at Level 2 and Level 3; it is now shown above the Debate matrix's cards and above Key tension and Synthesis.
**Migration**: "Language-model-written text is marked as such and the disclaimer accompanies agent reasoning (Rule 5, Rule 6)".

### Requirement: Fixed panel text contains no transaction verbs (Rule 6)
**Reason**: Its scenario renders the panel "at Levels 1 to 3" and covers one component; the guard now covers every zone of the dashboard.
**Migration**: "Fixed dashboard text contains no transaction verbs, enum text or Confidence (Rule 6)".

### Requirement: DebatePanel shows the report-saved line only when the report was saved
**Reason**: It places the line at Level 3.
**Migration**: "The report-saved line appears only when the report was saved".

### Requirement: DebatePanel marks an unavailable key tension
**Reason**: It places Key Tension at Level 2; Key tension is now a block of the Verdict panel.
**Migration**: "Key tension is shown in the Verdict panel only, and says when it is unavailable".
