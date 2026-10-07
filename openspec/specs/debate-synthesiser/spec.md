# debate-synthesiser

## Purpose

TBD

## Requirements

### Requirement: Synthesiser maps Round 2 stances to a verdict and agreement level
The Synthesiser SHALL read the three Round 2 `AgentPosition` objects and apply the majority logic:
- 3/3 bull → `STRONG_BUY_SIGNAL` / `unanimous`
- 2/3 bull → `BUY_SIGNAL` / `majority`
- 3/3 neutral → `OBSERVE` / `unanimous`
- 1/3 neutral with no majority direction (one bull, one bear, one neutral) → `SPLIT` / `split`
- 2 neutral + 1 directional → `OBSERVE` / `majority`
- 2/3 bear → `CAUTION_SIGNAL` / `majority`
- 3/3 bear → `STRONG_CAUTION_SIGNAL` / `unanimous`

This mapping applies when all three agents are live; the case of degraded agents is defined by the requirement "Synthesiser votes only the Round 2 stances of live agents". Display wording of the verdict values is not defined here.

#### Scenario: Unanimous bearish
- **WHEN** all three Round 2 stances are `bear`
- **THEN** `verdict = STRONG_CAUTION_SIGNAL`, `agreement_level = unanimous`

#### Scenario: Three-way split
- **WHEN** Round 2 stances are `bull`, `neutral`, `bear`
- **THEN** `verdict = SPLIT`, `agreement_level = split`

#### Scenario: Two neutral and one directional
- **WHEN** Round 2 stances are `neutral`, `neutral`, `bull`
- **THEN** `verdict = OBSERVE`, `agreement_level = majority`

### Requirement: Synthesiser identifies and surfaces the key tension
The Synthesiser SHALL use the LLM to identify the most important disagreement between agents — the "key tension" — defined as the strongest argument from the minority position (or the most salient uncertainty in a unanimous result). `key_tension` is a single plain-language paragraph of 2–4 sentences, included in `synthesis.key_tension`.

#### Scenario: Majority result with a dissenting agent
- **WHEN** two agents are bullish and one is bearish
- **THEN** `key_tension` states specifically what the bearish agent argued and why it matters, without dismissing it

#### Scenario: Unanimous result
- **WHEN** all three agents agree
- **THEN** `key_tension` states the most significant risk or uncertainty the unanimous agents did not fully resolve, e.g. "All agents agree on the bullish technical picture; the key uncertainty is whether current VN-Index momentum will hold into next week's macro data releases."

### Requirement: Synthesiser prompt instructs agents to maintain positions, not capitulate
The Round 2 prompt for each agent SHALL explicitly instruct: "Maintain your position if the evidence supports it. Only shift if a specific counter-argument is compelling and you can state exactly why." The Synthesiser SHALL report each agent's final Round 2 stance without rewarding convergence or penalizing disagreement.

#### Scenario: Agents remain split after Round 2
- **WHEN** agents do not converge in Round 2
- **THEN** the `SPLIT` verdict is returned and the full disagreement is preserved in `key_tension`, not smoothed over

#### Scenario: Synthesiser reasoning reflects Round 2 final positions
- **WHEN** an agent shifted from Round 1 to Round 2
- **THEN** `synthesis.reasoning` notes the shift and cites the reason given by the agent

### Requirement: Synthesiser votes only the Round 2 stances of live agents
The Synthesiser SHALL exclude every agent in `agents_degraded` from the vote. With three live agents the existing mapping requirement applies unchanged. With two live agents: if their Round 2 stances agree, `verdict` is `BUY_SIGNAL` (both `bull`), `CAUTION_SIGNAL` (both `bear`) or `OBSERVE` (both `neutral`) with `agreement_level = majority`, never a `STRONG_*` verdict and never `unanimous`; if they differ, `verdict = SPLIT` and `agreement_level = split`. With fewer than two live agents, `verdict = INSUFFICIENT_DATA` and `agreement_level = none`. A degraded agent SHALL NOT be counted as neutral.

#### Scenario: Two live agents agree bullish, one degraded
- **WHEN** Technical and Macro are `bull` and News is degraded
- **THEN** `verdict = BUY_SIGNAL`, `agreement_level = majority`, and the verdict is not `STRONG_BUY_SIGNAL`

#### Scenario: Two live agents disagree
- **WHEN** one live agent is `bull` and the other `neutral`, third degraded
- **THEN** `verdict = SPLIT` (a placeholder neutral would have produced `OBSERVE`)

#### Scenario: Two live agents both neutral
- **WHEN** both live agents are `neutral`
- **THEN** `verdict = OBSERVE`, `agreement_level = majority`

#### Scenario: One live agent
- **WHEN** only one agent is live
- **THEN** `verdict = INSUFFICIENT_DATA`, `agreement_level = none`

#### Scenario: Three live agents unchanged
- **WHEN** no agent is degraded
- **THEN** the mapping of the requirement "Synthesiser maps Round 2 stances to a verdict and agreement level" applies exactly as before

### Requirement: Synthesiser makes no LLM call when it abstains
When the verdict is `INSUFFICIENT_DATA` the Synthesiser SHALL skip the key-tension and summary LLM calls and return empty `key_tension` and `reasoning`. When the verdict is not `INSUFFICIENT_DATA`, the prompts SHALL name any degraded agent as unavailable and SHALL NOT present its placeholder as a position. A failure of the synthesis prose SHALL NOT change the verdict.

#### Scenario: Abstention
- **WHEN** two agents are degraded
- **THEN** no synthesis LLM call is made

#### Scenario: Degraded agent in the prompt
- **WHEN** News is degraded and the verdict is `BUY_SIGNAL`
- **THEN** the synthesis prompts state that the News agent was unavailable and carry no News stance

#### Scenario: Prose failure keeps the verdict
- **WHEN** the key-tension LLM call raises
- **THEN** the verdict and agreement level are unchanged

### Requirement: Verdict display labels are non-transactional (Rule 6)
Every verdict enum value SHALL have exactly one display label, and the panel and the exported report SHALL show that label instead of the enum text. Enum values (the API contract) do not change. The labels are:

| Enum value | Display label |
| --- | --- |
| `STRONG_BUY_SIGNAL` | Strong bullish lean |
| `BUY_SIGNAL` | Bullish lean |
| `OBSERVE` | Observe |
| `CAUTION_SIGNAL` | Bearish lean |
| `STRONG_CAUTION_SIGNAL` | Strong bearish lean |
| `SPLIT` | Split — no consensus |
| `INSUFFICIENT_DATA` | Insufficient data |

No display label SHALL contain "buy", "sell" or "hold" as a whole word, in any letter case. This requirement supersedes the sentence about "BUY" and "SELL" "as standalone instructions" in "Synthesiser maps Round 2 stances to a verdict and agreement level".

#### Scenario: Every enum value has a label
- **WHEN** the set of values of the `Verdict` type is compared with the label table used by the export
- **THEN** the two sets are equal, so a new enum value without a label fails a test

#### Scenario: Labels carry no transaction verb
- **WHEN** each display label is checked case-insensitively for the whole words "buy", "sell" and "hold"
- **THEN** none is found

#### Scenario: Enum values are unchanged
- **WHEN** the debate endpoint returns a result whose majority is bullish
- **THEN** `verdict` is `BUY_SIGNAL` and only the display label reads "Bullish lean"

### Requirement: Synthesiser prompts and fallback text describe the vote neutrally (Rule 6)
The key-tension prompt, the synthesis-summary prompt and the synthesis fallback text SHALL describe the outcome by stance counts and agreement level (for example `2 bullish, 1 neutral, 0 bearish (majority)`), and SHALL NOT contain verdict enum text or the words "buy", "sell" or "hold".

#### Scenario: Prompts contain no enum text for any stance combination
- **WHEN** both prompts are built for every combination of three Round 2 stances
- **THEN** neither contains an enum value (such as `BUY_SIGNAL`) nor, case-insensitively, the whole words "buy", "sell" or "hold"

#### Scenario: Synthesis fallback shows the vote, not the enum
- **WHEN** the synthesis LLM call fails for a debate whose Round 2 stances are bull, bull, neutral
- **THEN** the returned reasoning reads `Vote: 2 bullish, 1 neutral, 0 bearish.` and contains no enum text
