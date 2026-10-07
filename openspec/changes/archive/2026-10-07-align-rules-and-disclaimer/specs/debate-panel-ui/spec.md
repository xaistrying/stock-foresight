## ADDED Requirements

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
