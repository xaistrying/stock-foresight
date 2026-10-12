# debate-synthesiser

## Purpose

TBD
## Requirements
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

No display label SHALL contain "buy", "sell" or "hold" as a whole word, in any letter case. This requirement supersedes the sentence about "BUY" and "SELL" "as standalone instructions" in "Synthesiser maps agent stances to a verdict and agreement level".

#### Scenario: Every enum value has a label
- **WHEN** the set of values of the `Verdict` type is compared with the label table used by the export
- **THEN** the two sets are equal, so a new enum value without a label fails a test

#### Scenario: Labels carry no transaction verb
- **WHEN** each display label is checked case-insensitively for the whole words "buy", "sell" and "hold"
- **THEN** none is found

#### Scenario: Enum values are unchanged
- **WHEN** the debate endpoint returns a result whose majority is bullish
- **THEN** `verdict` is `BUY_SIGNAL` and only the display label reads "Bullish lean"

### Requirement: Synthesiser maps agent stances to a verdict and agreement level
The Synthesiser SHALL read the three Round 1 `AgentPosition` objects (the only round) and apply the majority logic:
- 3/3 bull → `STRONG_BUY_SIGNAL` / `unanimous`
- 2/3 bull → `BUY_SIGNAL` / `majority`
- 3/3 neutral → `OBSERVE` / `unanimous`
- 1/3 neutral with no majority direction (one bull, one bear, one neutral) → `SPLIT` / `split`
- 2 neutral + 1 directional → `OBSERVE` / `majority`
- 2/3 bear → `CAUTION_SIGNAL` / `majority`
- 3/3 bear → `STRONG_CAUTION_SIGNAL` / `unanimous`

This mapping applies when all three agents are live; the case of degraded agents is defined by the requirement "Synthesiser votes only the stances of live agents". Display wording of the verdict values is not defined here.

#### Scenario: Unanimous bearish
- **WHEN** all three Round 1 stances are `bear`
- **THEN** `verdict = STRONG_CAUTION_SIGNAL`, `agreement_level = unanimous`

#### Scenario: Three-way split
- **WHEN** Round 1 stances are `bull`, `neutral`, `bear`
- **THEN** `verdict = SPLIT`, `agreement_level = split`

#### Scenario: Two neutral and one directional
- **WHEN** Round 1 stances are `neutral`, `neutral`, `bull`
- **THEN** `verdict = OBSERVE`, `agreement_level = majority`

### Requirement: Synthesiser votes only the stances of live agents
The Synthesiser SHALL exclude every agent in `agents_degraded` from the vote. With three live agents the existing mapping requirement applies unchanged. With two live agents: if their Round 1 stances agree, `verdict` is `BUY_SIGNAL` (both `bull`), `CAUTION_SIGNAL` (both `bear`) or `OBSERVE` (both `neutral`) with `agreement_level = majority`, never a `STRONG_*` verdict and never `unanimous`; if they differ, `verdict = SPLIT` and `agreement_level = split`. With fewer than two live agents, `verdict = INSUFFICIENT_DATA` and `agreement_level = none`. A degraded agent SHALL NOT be counted as neutral.

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
- **THEN** the mapping of the requirement "Synthesiser maps agent stances to a verdict and agreement level" applies exactly as before

### Requirement: The vote is deterministic, makes no language-model call and returns no prose
The Synthesiser SHALL compute `verdict` and `agreement_level` from the agents' stances alone. It SHALL make no language-model call, including when it abstains, and SHALL return no prose: no key tension and no summary text. The key-tension and summary calls, and the prompts that carried the vote to a model, no longer exist.

#### Scenario: A vote needs no language model
- **WHEN** the vote is computed while every language-model call would raise
- **THEN** `verdict` and `agreement_level` are returned as the mapping defines

#### Scenario: Abstention makes no call
- **WHEN** two agents are degraded
- **THEN** the verdict is `INSUFFICIENT_DATA` and no language-model call is made by the vote

