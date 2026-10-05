## ADDED Requirements

### Requirement: Synthesiser maps Round 2 stances to a verdict and agreement level
The Synthesiser SHALL read the three Round 2 `AgentPosition` objects and apply the majority logic:
- 3/3 bull → `STRONG_BUY_SIGNAL` / `unanimous`
- 2/3 bull → `BUY_SIGNAL` / `majority`
- 3/3 neutral → `OBSERVE` / `unanimous`
- 1/3 neutral with no majority direction (one bull, one bear, one neutral) → `SPLIT` / `split`
- 2 neutral + 1 directional → `OBSERVE` / `majority`
- 2/3 bear → `CAUTION_SIGNAL` / `majority`
- 3/3 bear → `STRONG_CAUTION_SIGNAL` / `unanimous`

The verdict MUST NOT use the words "BUY" or "SELL" as standalone instructions (Rule 6). Labels are signals and observations, not directives.

#### Scenario: Unanimous bearish
- **WHEN** all three Round 2 stances are `bear`
- **THEN** `verdict = STRONG_CAUTION_SIGNAL`, `agreement_level = unanimous`

#### Scenario: Three-way split
- **WHEN** Round 2 stances are `bull`, `neutral`, `bear`
- **THEN** `verdict = SPLIT`, `agreement_level = split`

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
