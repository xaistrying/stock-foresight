## RENAMED Requirements

- FROM: `### Requirement: The result state shows the verdict, Agreement, stance chips, Key tension, Synthesis and the data line`
- TO: `### Requirement: The result state shows the verdict, Agreement, stance chips and the data line`

- FROM: `### Requirement: The Debate matrix shows three agents by two rounds, with cards clamped to five lines`
- TO: `### Requirement: The Debate matrix shows one card per agent, clamped to five lines`

## MODIFIED Requirements

### Requirement: DebatePanel shows the running stage and elapsed time
While an analysis for the selected ticker is running, the panel SHALL show the stage reported by `GET /tickers/{ticker}/debate/progress` using the label "Running agents…" for `round1`, the only stage, and the elapsed seconds since the request was submitted, updated at least once per second. The label SHALL come from the server, not from a timer; a stage value the panel has no label for SHALL show the same label. A failed progress poll SHALL keep the last label and show no error. The disclaimer SHALL remain visible.

#### Scenario: Stage follows the server
- **WHEN** the progress endpoint reports `round1` while the request is pending
- **THEN** the panel shows "Running agents…" and an elapsed time

#### Scenario: A stage the panel does not know
- **WHEN** the progress endpoint reports a stage value that has no label
- **THEN** the panel shows "Running agents…" and no enum text

#### Scenario: Elapsed time keeps counting
- **WHEN** 12 seconds have passed since the request was submitted
- **THEN** the panel shows an elapsed time of 12 seconds

#### Scenario: Progress poll fails
- **WHEN** a progress request fails while the analysis is running
- **THEN** the previous label stays and no error message appears

### Requirement: The ready state offers Analyse and says how long it takes
In the ready state the panel SHALL show an "Analyse {TICKER}" action and, before the run starts, the sentence "Analysis takes about N seconds.", where N is the value of one named constant (`TYPICAL_ANALYSIS_SECONDS`) and that value is set from a measured typical run of the current agent set. The panel SHALL NOT show placeholder verdict values in this state. In the insufficient-data state for a ticker the catalog or `/range` already says is ineligible, the panel SHALL NOT offer Analyse.

#### Scenario: Notice before the run
- **WHEN** a ticker that can be analysed is selected
- **THEN** the panel shows "Analyse TCB" and "Analysis takes about N seconds." with N read from the named constant, and no verdict, Agreement or stance

#### Scenario: One source for the duration
- **WHEN** the named constant is changed
- **THEN** the sentence changes with it and no other fixed text in the panel states a duration

#### Scenario: No Analyse for an ineligible ticker
- **WHEN** the selected ticker's `eligibility.eligible` is false
- **THEN** the panel shows a Refresh action and no Analyse action

### Requirement: The result state shows the verdict, Agreement, stance chips and the data line
A result SHALL show, in order: the verdict badge (the display label from the `debate-synthesiser` table), Agreement, one stance chip per agent for its Round 1 position, the data line, "Analysed HH:MM" (the time the result was produced), the report-saved line when it applies, and a Re-analyse action. The data line SHALL read "Data as of 2026-10-02 · 2 sessions old" from `data_as_of` and `data_age_sessions` ("· current" at age 0; the date alone when the age is absent), SHALL NOT use `as_of` as an analysis date and SHALL NOT rely on colour alone. None of these SHALL be hidden behind a toggle. The Verdict panel SHALL show no Key tension and no Synthesis, and no language-model-written text.

#### Scenario: Everything is visible at once
- **WHEN** a result with a verdict `BUY_SIGNAL` and three live agents is shown
- **THEN** the badge, Agreement, three stance chips and the data line are all visible without a click, and no Key tension or Synthesis text appears

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
- **WHEN** Round 1 stances are bull, neutral and bear
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
For every agent in `agents_degraded` the panel SHALL replace its stance chip with an "unavailable" chip (text, dashed strong border, no warn colour) and the Debate matrix SHALL show an Unavailable card with a plain-language reason (`agent_error`: "The agent failed to run."; `no_input`: "No usable input data."; `llm_failed`: "The language-model analysis failed."). Agreement SHALL count only live agents, as "N of M live agents", followed by the unavailable agents' labels, e.g. "Agreement: 2 of 2 live agents (News Context unavailable)"; a split of two live agents reads "Agreement: Split — 2 different positions"; with no unavailable agent it reads as the shipped three-agent forms: `Agreement: Unanimous — 3 of 3 agents`, `Agreement: Majority — 2 of 3 agents` or `Agreement: Split — 3 different positions`. The word "unanimous" SHALL NOT appear when any agent is unavailable. The panel SHALL show whatever verdict the server sends; with fewer than two live agents the server's verdict is `INSUFFICIENT_DATA` and the panel is in the insufficient-data state.

#### Scenario: One agent unavailable
- **WHEN** News is degraded and Technical and Macro are `bull`
- **THEN** the chips show News Context as unavailable, Agreement reads "Agreement: 2 of 2 live agents (News Context unavailable)", and the matrix shows the Unavailable card for News Context

#### Scenario: Two live agents disagree
- **WHEN** one agent is degraded and the two live agents are `bull` and `bear`
- **THEN** Agreement reads "Agreement: Split — 2 different positions (1 unavailable)" and the verdict label is the server's `SPLIT` label

#### Scenario: No agent unavailable
- **WHEN** `agents_degraded` is empty and the agreement level is `majority` with two agents on the majority stance
- **THEN** Agreement reads "Agreement: Majority — 2 of 3 agents" and no unavailable marker appears

#### Scenario: A retired reason code is not shown
- **WHEN** a position carries a `degraded_reason` the panel has no text for
- **THEN** the panel shows the code as received rather than a Round 2 sentence, and no text names a Round 2

### Requirement: The insufficient-data state gives reasons in plain words and offers Refresh, before or after a run
When the ticker's eligibility has reasons, or when a run's `verdict` is `INSUFFICIENT_DATA`, the panel SHALL render the insufficient-data state in place of the verdict, Agreement and stance chips: the badge using the `INSUFFICIENT_DATA` display label, the data date and age when known, and one sentence per reason, in the order given: `delisted` "This ticker is delisted."; `insufficient_history` "Not enough price history (at least 65 sessions are needed)."; `stale` "Stored prices are N sessions old. Refresh the ticker, then analyse again." (N from `eligibility.age_sessions` or `data_age_sessions`; "many" when absent); `near_gap` "The price history has missing sessions."; `hard_quality_flag` "A recent price failed a data-quality check."; `indicators_missing` "Technical indicators are not available for the latest session.". When the reasons come from a run that abstained after the agents ran (empty reasons, degraded agents) the panel SHALL list each degraded agent with its reason and say that fewer than two agents produced a usable position. The state SHALL offer a "Refresh {TICKER}" action that calls `POST /tickers/{ticker}/load` as the Rail's Refresh does (disabled while that load is in flight, the same per-status messages), SHALL show no report-saved note, no Advice, Confidence or Sentiment value, and SHALL keep the disclaimer visible. The range block SHALL stay visible above it; it shows a band whenever `/range` serves one.

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

### Requirement: The Debate matrix shows one card per agent, clamped to five lines
The Stage SHALL contain a Debate matrix below the chart: three agent cards in one row (Technical Signal, News Context, Macro, in that order; Rule 5), each with the agent's label, its stance as glyph and word, and its reasoning bullets. No round is named anywhere in the matrix. A card's text SHALL be clamped to five lines of body text with a "Show more" button (`aria-expanded`, `aria-controls`; "Show less" when open), shown only when the text overflows, and the clamp SHALL keep list semantics. An agent that did not answer SHALL get a card with a dashed strong border reading "Unavailable — did not vote" and its plain-language reason. The matrix SHALL NOT print all agents' reasoning as one scrolling text column. Before a result it SHALL show a one-line prompt under its heading; while a run is in flight it SHALL show three skeleton cells hidden from assistive technology; for a refusal in which no agent ran it SHALL say that no debate was run. At 768 px and up the three columns SHALL stay; below 768 px the matrix SHALL be a tablist of three agent tabs (`role="tablist"` named "Agents", `role="tab"` with `aria-selected` and `aria-controls`, `role="tabpanel"`; Left, Right, Home and End move between tabs) with that agent's one card inside each panel. Agent text SHALL be rendered as text, with Markdown bold shown as bold and nothing interpreted as HTML.

#### Scenario: Three cards in one row
- **WHEN** a result with three live agents is shown at 1440 px
- **THEN** the matrix has three cards in one row, in the order Technical Signal, News Context, Macro, and no heading or label names a round

#### Scenario: Long text is clamped
- **WHEN** a card's reasoning is longer than five lines
- **THEN** the card shows five lines and a "Show more" button with `aria-expanded="false"`, and activating it shows the whole text with `aria-expanded="true"`

#### Scenario: Short text has no button
- **WHEN** a card's reasoning fits in five lines
- **THEN** no "Show more" button is shown

#### Scenario: Unavailable card
- **WHEN** News is degraded with `agent_error`
- **THEN** its card reads "Unavailable — did not vote" with "The agent failed to run." and a dashed strong border

#### Scenario: Phone tabs
- **WHEN** the viewport is 390 px wide
- **THEN** the matrix is a tablist with three tabs, the selected tab's panel holds that agent's card, and the arrow keys move between tabs

#### Scenario: Before and while running
- **WHEN** no result exists, and then a run is pending
- **THEN** the matrix shows its prompt (which names no round), and then three skeleton cells with no accessible text

#### Scenario: Provenance labels
- **WHEN** the matrix is shown
- **THEN** its card headings are exactly "Technical Signal", "News Context" and "Macro", and "Market Sentiment" appears nowhere

### Requirement: Language-model-written text is marked as such and the disclaimer accompanies agent reasoning (Rule 5, Rule 6)
The sentence `News Context reasoning is written by a language model; Technical Signal and Macro reasoning are computed values.` SHALL be shown above the Debate matrix's cards whenever a result with agent positions is displayed. The Verdict panel SHALL NOT show it, because the Verdict panel holds no language-model-written text. The inline disclaimer from `lib/disclaimer.js` SHALL be shown under the Debate matrix's heading in every state in which the matrix is displayed, in addition to the Verdict panel's own, since the matrix displays agent reasoning outside the Verdict panel.

#### Scenario: Note above the cards
- **WHEN** a result is displayed
- **THEN** the sentence appears above the matrix's cards, and the inline disclaimer is visible under the matrix heading

#### Scenario: Note not in the Verdict panel
- **WHEN** a result is displayed
- **THEN** the Verdict panel contains neither that sentence nor the earlier sentence naming key tension and synthesis

## REMOVED Requirements

### Requirement: Key tension is shown in the Verdict panel only, and says when it is unavailable
**Reason**: Key tension (a model-written paragraph) is removed from the product in step 1 of `docs/DISCUSSION_describe_not_vote_redesign.md`; the warn colours it alone used are removed with it.
**Migration**: None. The Verdict panel shows the badge, Agreement, the stance chips and the data line; the contrast requirement in `dashboard-ui` drops the warn pairs.
