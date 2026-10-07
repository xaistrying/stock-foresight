## MODIFIED Requirements

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

## ADDED Requirements

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
