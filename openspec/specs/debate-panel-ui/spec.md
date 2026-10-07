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

### Requirement: Panel shows the data date and age with every result
At Level 1 of every populated result, the panel SHALL show the data date and its age in sessions, from `data_as_of` and `data_age_sessions`, in text such as "Data as of 2026-10-02 · 2 sessions old". At age 0 it reads "Data as of <date> · current". The line SHALL NOT use `as_of` as an analysis date, and SHALL NOT rely on colour alone.

#### Scenario: Result with data two sessions old
- **WHEN** a result has `data_as_of = "2026-10-02"` and `data_age_sessions = 2`
- **THEN** Level 1 shows "Data as of 2026-10-02 · 2 sessions old" without expanding anything

#### Scenario: Current data
- **WHEN** `data_age_sessions = 0`
- **THEN** the line reads "Data as of <date> · current"

### Requirement: Panel marks degraded agents and states agreement over live agents
For every agent in `agents_degraded` the panel SHALL replace its stance arrow in the Level 1 stance row with an "unavailable" marker (text and icon) and SHALL show a marker and a plain-language reason on its Level 2 card and in Level 3 (`agent_error`: "The agent failed to run."; `no_input`: "No usable input data."; `llm_failed`: "The language-model analysis failed."; `round2_failed`: "Round 2 failed; its Round 1 position is shown but not counted."). The agreement text SHALL count only live agents, as "N of M live agents", followed by "(K unavailable)" when K is above 0; a split of two live agents reads "Split — 2 different positions". The word "unanimous" SHALL NOT appear when any agent is degraded.

#### Scenario: One agent degraded
- **WHEN** News is degraded and Technical and Macro are `bull`
- **THEN** the stance row shows News as unavailable, the agreement text reads "2 of 2 live agents (1 unavailable)", and the Level 2 News card shows its reason

#### Scenario: Round 2 failure card
- **WHEN** an agent is `round2_failed`
- **THEN** its card shows its Round 1 position under the marker "Round 2 failed; its Round 1 position is shown but not counted."

#### Scenario: No degraded agents
- **WHEN** `agents_degraded` is empty
- **THEN** the agreement text is computed over all three agents as before and no unavailable marker appears

### Requirement: Panel shows an insufficient-data state with human-readable reasons
When `verdict` is `INSUFFICIENT_DATA` the panel SHALL render a dedicated state in place of the verdict, agreement, stance row, range, Level 2 and Level 3: the verdict badge using the display label defined for `INSUFFICIENT_DATA`, the data date and age when present, and one sentence per reason in `eligibility.reasons`, in order: `delisted` "This ticker is delisted."; `insufficient_history` "Not enough price history (at least 65 sessions are needed)."; `stale` "Stored prices are N sessions old. Refresh the ticker in the ticker panel, then analyse again."; `near_gap` "The price history has missing sessions."; `hard_quality_flag` "A recent price failed a data-quality check."; `indicators_missing` "Technical indicators are not available for the latest session.". When `eligibility.reasons` is empty and agents are degraded (an abstention after the agents ran), it SHALL instead list each degraded agent with its reason text and state that fewer than two agents produced a usable position. The state SHALL show no report-saved note, no Advice, Confidence or Sentiment value, and SHALL keep the disclaimer (Rule 6) visible. A "Re-analyse" action SHALL remain available.

#### Scenario: Stale ticker
- **WHEN** the result is `INSUFFICIENT_DATA` with reasons `["stale"]` and `data_age_sessions = 21`
- **THEN** the panel shows "Stored prices are 21 sessions old. Refresh the ticker in the ticker panel, then analyse again." and no stance row

#### Scenario: Several reasons
- **WHEN** reasons are `["delisted", "stale"]`
- **THEN** both sentences are shown, in that order

#### Scenario: Abstention after degraded agents
- **WHEN** reasons are empty and News and Macro are degraded
- **THEN** the panel lists both agents with their reasons and says fewer than two agents produced a usable position

#### Scenario: Disclaimer and no export note
- **WHEN** the insufficient-data state is shown
- **THEN** the disclaimer is visible and no "Report saved" text appears

### Requirement: Panel range line states the typical 5-session move and its coverage
At Level 1 of a populated panel, when `result.range_5s_pct` is not null, the DebatePanel SHALL render a line "Typical 5-session move: ±X.X% (about 2 in 3 recent 5-session moves stayed within this range)" with one decimal. The coverage phrase SHALL be derived from `result.range_coverage`: 0.68 renders "about 2 in 3", any other value renders "about N%" with N rounded to the nearest 5. When `range_coverage` is null the line SHALL read "Typical 5-session move: ±X.X% (coverage not established for this stock)". When `range_5s_pct` is null the line SHALL be omitted with no placeholder. The line MUST NOT use the words "expected", "confidence" or "forecast", MUST NOT display `sigma_daily_pct`, and MUST appear inside the panel that carries the Rule 6 disclaimer. The wording is a proposal for the copy review owned by `align-rules-and-disclaimer`.

#### Scenario: Calibrated band shown with its coverage
- **WHEN** the result has `range_5s_pct` 5.3 and `range_coverage` 0.68
- **THEN** Level 1 shows "Typical 5-session move: ±5.3%" and "about 2 in 3"

#### Scenario: Other nominal coverage
- **WHEN** `range_coverage` is 0.8
- **THEN** the line says "about 80%"

#### Scenario: Uncalibrated ticker
- **WHEN** `range_5s_pct` is 5.3 and `range_coverage` is null
- **THEN** the line says "coverage not established for this stock" and does not say "about 2 in 3"

#### Scenario: No band
- **WHEN** `range_5s_pct` is null
- **THEN** no range line is rendered

### Requirement: Verdict badge uses non-transactional display labels (Rule 6)
The verdict badge SHALL show the display label for the verdict from the table in the `debate-synthesiser` capability ("Verdict display labels are non-transactional (Rule 6)") and SHALL NOT show enum text. A verdict value missing from the table SHALL render "Unrecognised verdict".

#### Scenario: Label for a bullish majority
- **WHEN** the result's verdict is `BUY_SIGNAL`
- **THEN** the badge reads "Bullish lean"

#### Scenario: Every contract value renders its label
- **WHEN** the panel is rendered for each of the seven verdict values
- **THEN** the badge reads, in turn, "Strong bullish lean", "Bullish lean", "Observe", "Bearish lean", "Strong bearish lean", "Split — no consensus" and "Insufficient data"

#### Scenario: Unknown verdict never shows the enum
- **WHEN** the result's verdict is a value not in the table
- **THEN** the badge reads "Unrecognised verdict"

### Requirement: Vote count is labelled "Agreement", never "Confidence" (Rule 4)
Level 1 SHALL show the vote count as `Agreement: Unanimous — 3 of 3 agents`, `Agreement: Majority — 2 of 3 agents` or `Agreement: Split — 3 different positions`. Fixed panel text SHALL NOT use the word "Confidence" (any letter case) for it or anywhere else.

#### Scenario: Majority
- **WHEN** the agreement level is `majority` and two agents hold the majority stance
- **THEN** Level 1 shows `Agreement: Majority — 2 of 3 agents`

#### Scenario: Split
- **WHEN** the agreement level is `split`
- **THEN** Level 1 shows `Agreement: Split — 3 different positions`

#### Scenario: No Confidence wording
- **WHEN** the panel is rendered in any state at any level
- **THEN** a case-insensitive search of its fixed text for `confiden(ce|t)` finds nothing

### Requirement: Range hit-rate, where shown, is labelled as a measurement (Rule 4)
Wherever the panel shows the range hit-rate (`range_hit_rate = {rate, n}`, defined by `calibrate-volatility-range` over non-overlapping five-session windows covering about the last year), it SHALL label it "Range hit-rate" and show it as "N of the last M five-session moves" (M is n, N is rate times n rounded to a whole number), with basis text saying those moves stayed inside the band. When the rate is unavailable it SHALL show "Not enough history" and no number. This requirement fixes the label and wording; where and when the figure is rendered is decided by the changes that supply it.

#### Scenario: Value shown with its basis
- **WHEN** the range hit-rate is `{rate: 0.68, n: 50}`
- **THEN** the panel shows "Range hit-rate" with "34 of the last 50 five-session moves" and basis text saying they stayed inside the band

#### Scenario: No value
- **WHEN** the range hit-rate is unavailable
- **THEN** the panel shows "Not enough history" and no count or percentage

### Requirement: Language-model-written text is marked as such (Rule 5)
Level 2 and Level 3 SHALL show, above the agent cards and above the transcript respectively, the sentence `Reasoning, key tension and synthesis are written by a language model.`

#### Scenario: Note at Level 2
- **WHEN** the panel is expanded to Level 2
- **THEN** the sentence is visible above the agent cards

#### Scenario: Note at Level 3
- **WHEN** the panel is expanded to Level 3
- **THEN** the sentence is visible above the Round 1 positions

### Requirement: Inline disclaimer matches docs/DISCLAIMER.md verbatim (Rule 6)
The always-visible inline disclaimer, held in the frontend module `frontend/src/lib/disclaimer.js` shared with any other component that shows it, SHALL equal the "Inline version" blockquote of `docs/DISCLAIMER.md` after whitespace normalisation (blockquote lines joined with one space, whitespace collapsed), and SHALL NOT include a repo path. A test SHALL fail if the module's string and the file differ.

#### Scenario: Text equals the file
- **WHEN** the panel test reads `docs/DISCLAIMER.md` and renders the panel
- **THEN** the inline disclaimer on screen equals the file's "Inline version" text

#### Scenario: Drift is caught
- **WHEN** either the file or the module's constant is edited alone
- **THEN** the test fails

### Requirement: Full disclaimer is one step away in every panel state (Rule 6)
In every panel state (not-run, loading, error, populated) the panel SHALL show, under the inline disclaimer, an "About this analysis" disclosure that contains the "Full disclaimer" blockquote of `docs/DISCLAIMER.md` verbatim (exported by the same module; same normalisation and drift test). The inline disclaimer SHALL stay visible whether or not the disclosure is open, and no control SHALL hide it.

#### Scenario: Disclosure present in all states
- **WHEN** the panel is rendered not-run, loading, in error and populated
- **THEN** an "About this analysis" disclosure holding the full text is present in each, with the inline disclaimer visible

#### Scenario: Opening the disclosure
- **WHEN** the user opens "About this analysis"
- **THEN** the full disclaimer is shown and the inline disclaimer remains visible

### Requirement: Fixed panel text contains no transaction verbs (Rule 6)
All fixed panel text (labels, headings, buttons, notes), excluding the two disclaimer texts and the backend-supplied agent text, SHALL NOT contain "buy", "sell" or "hold" as whole words in any letter case, nor any verdict enum text. This guard is case-insensitive, unlike the retired `/\bBUY\b/` check.

#### Scenario: Guard over every state and verdict
- **WHEN** the panel is rendered in every state, and populated for each verdict at Levels 1 to 3 from a fixture whose agent text avoids those words, with the disclaimer texts removed
- **THEN** a case-insensitive search for `\b(buy|sell|hold)\b` and for `[A-Z]+_SIGNAL` finds nothing

### Requirement: DebatePanel shows the running stage and elapsed time
While an analysis for the selected ticker is running, the panel SHALL show the stage reported by `GET /tickers/{ticker}/debate/progress` using the labels "Running agents…" (`round1`), "Comparing positions…" (`round2`) and "Synthesising…" (`synthesis`), and the elapsed seconds since the request was submitted, updated at least once per second. The label SHALL come from the server, not from a timer. A failed progress poll SHALL keep the last label and show no error. The disclaimer SHALL remain visible.

#### Scenario: Stage follows the server
- **WHEN** the progress endpoint reports `round2` while the request is pending
- **THEN** the panel shows "Comparing positions…" and an elapsed time

#### Scenario: Elapsed time keeps counting
- **WHEN** 12 seconds have passed since the request was submitted
- **THEN** the panel shows an elapsed time of 12 seconds

#### Scenario: Progress poll fails
- **WHEN** a progress request fails while the analysis is running
- **THEN** the previous label stays and no error message appears

### Requirement: DebatePanel keeps the last result per ticker for the session
The panel SHALL keep the last successful result for each ticker in memory until the page reloads or that ticker is analysed again, and SHALL show it with the time it was produced. Switching tickers SHALL NOT cancel an in-flight request or discard a result; when the user returns to a ticker whose analysis finished or is still running, the panel SHALL show that result or that running state. A failed run SHALL NOT remove a kept result: the error is shown above it.

#### Scenario: Switch away and back
- **WHEN** an analysis for VCB is running, the user selects FPT, and the VCB analysis finishes
- **THEN** selecting VCB again shows the finished VCB result without a new request

#### Scenario: Result is labelled with its time
- **WHEN** a kept result is displayed
- **THEN** the panel shows when it was produced (for example "Analysed 14:32")

#### Scenario: Failed re-run keeps the old result
- **WHEN** the user re-analyses a ticker that has a kept result and the run fails
- **THEN** the error is shown and the earlier result remains visible

#### Scenario: Other ticker has no result
- **WHEN** the user selects a ticker that has never been analysed this session
- **THEN** the panel shows the not-run state

### Requirement: DebatePanel stops waiting after a client time limit
The analysis request SHALL be aborted by the client after 200 seconds (the server run budget of 180 s plus 20 s). The panel SHALL then say that no answer arrived in that time, that the server may still be working, and that analysing again rejoins it. It SHALL NOT show the network-error message for this case.

#### Scenario: No response within the limit
- **WHEN** the request has had no response when the client limit is reached
- **THEN** the panel shows the time-limit message and an "Analyse again" action, not "could not reach the server"

### Requirement: DebatePanel names the reason an analysis could not run
The panel SHALL show a distinct message for each of: the ticker is not loaded (404); another analysis limit reached (429 `debate_busy`: "Another analysis is already running; try again shortly"); the service is not configured (503 `debate_not_configured`, showing the server's message); the server run timed out (504 `debate_timeout`); the client time limit. Any other failure SHALL show a generic message together with the server's `detail` when one exists. The disclaimer SHALL remain visible in each of these states.

#### Scenario: Busy
- **WHEN** the response is HTTP 429 with `code` "debate_busy"
- **THEN** the panel shows the busy message and offers a retry

#### Scenario: Not configured
- **WHEN** the response is HTTP 503 with `code` "debate_not_configured" and a message
- **THEN** the panel shows that message

#### Scenario: Server timeout
- **WHEN** the response is HTTP 504 with `code` "debate_timeout"
- **THEN** the panel says the analysis timed out on the server

#### Scenario: Disclaimer in failure states
- **WHEN** any of the failure messages is shown
- **THEN** the disclaimer is visible

### Requirement: DebatePanel shows the report-saved line only when the report was saved
Level 3 SHALL show "Report saved to reports/<report_file>" only when the result has `report_saved` true, using the `report_file` value from the response. When `report_saved` is false or absent the panel SHALL NOT claim a saved report.

#### Scenario: Report saved
- **WHEN** the result has `report_saved` true and `report_file` "2026-10-05_VPB.md"
- **THEN** Level 3 shows "Report saved to reports/2026-10-05_VPB.md"

#### Scenario: Export failed
- **WHEN** the result has `report_saved` false
- **THEN** Level 3 contains no "Report saved" text

### Requirement: DebatePanel marks an unavailable key tension
When `synthesis.key_tension` is null the Level 2 Key Tension block SHALL say "Key tension unavailable" and SHALL NOT present any text as the key tension.

#### Scenario: Null key tension
- **WHEN** the result's `synthesis.key_tension` is null
- **THEN** Level 2 shows "Key tension unavailable" under the Key Tension heading
