# debate-engine

## Purpose

TBD

## Requirements

### Requirement: Debate engine runs three agents in parallel for Round 1
The engine SHALL invoke TechnicalAgent, NewsAgent, and MacroAgent concurrently (asyncio) for Round 1. Each agent returns a `AgentPosition` object: `{ agent_id, stance, reasoning, volatility_range_pct }` where `stance ∈ {bull, bear, neutral}` and `reasoning` is a list of 3–5 bullet strings.

#### Scenario: All three agents complete Round 1
- **WHEN** `POST /tickers/{ticker}/debate` is called for a loaded ticker with features
- **THEN** all three agents are invoked concurrently and all three positions are collected before Round 2 begins

#### Scenario: One agent fails in Round 1
- **WHEN** one agent raises an exception or times out during Round 1
- **THEN** that agent's position is set to `{ stance: "neutral", reasoning: ["Agent unavailable"] }` and the debate proceeds with the two remaining positions

### Requirement: Debate engine runs a response round (Round 2) in parallel
After collecting Round 1 positions, the engine SHALL pass each agent its own Round 1 position plus the other two agents' Round 1 positions, and invoke all three response calls concurrently. Each agent returns an updated `AgentPosition` (may differ from Round 1 or remain unchanged).

#### Scenario: Agent holds its Round 1 position in Round 2
- **WHEN** an agent's Round 2 prompt does not find a compelling counter-argument
- **THEN** the Round 2 position has the same `stance` as Round 1 but MAY add a rebuttal to `reasoning`

#### Scenario: Agent shifts stance in Round 2
- **WHEN** an agent finds a specific counter-argument from another agent compelling
- **THEN** the Round 2 `stance` MAY differ from Round 1, and `reasoning` MUST explain the shift

### Requirement: Debate engine produces a structured `DebateResult` object
After synthesis, the engine SHALL return a `DebateResult`:
```
{
  ticker, as_of, verdict, agreement_level,
  round1: { technical, news, macro },
  round2: { technical, news, macro },
  synthesis: { verdict, agreement_level, key_tension, reasoning },
  volatility_range_pct,
  duration_ms
}
```
`verdict ∈ {STRONG_BUY_SIGNAL, BUY_SIGNAL, OBSERVE, CAUTION_SIGNAL, STRONG_CAUTION_SIGNAL, SPLIT}`  
`agreement_level ∈ {unanimous, majority, split}`

#### Scenario: All agents agree bullish
- **WHEN** all three Round 2 stances are `bull`
- **THEN** `verdict = STRONG_BUY_SIGNAL`, `agreement_level = unanimous`

#### Scenario: Two agents agree, one dissents
- **WHEN** two Round 2 stances are `bull` and one is `bear` or `neutral`
- **THEN** `verdict = BUY_SIGNAL`, `agreement_level = majority`

#### Scenario: Agents split with no majority direction
- **WHEN** Round 2 stances are one of each (`bull`, `neutral`, `bear`) or two `neutral` with one directional
- **THEN** `verdict = SPLIT`, `agreement_level = split`

### Requirement: Debate endpoint is `POST /tickers/{ticker}/debate`
The API SHALL expose `POST /tickers/{ticker}/debate` returning a `DebateResult` JSON. The endpoint requires the ticker to be loaded (features exist); returns HTTP 404 if not loaded, HTTP 503 if feature computation failed.

#### Scenario: Ticker not loaded
- **WHEN** `POST /tickers/{ticker}/debate` is called for a ticker with no loaded features
- **THEN** HTTP 404 is returned with `{ detail: "Ticker has not been loaded" }`

#### Scenario: Analysis completes successfully
- **WHEN** `POST /tickers/{ticker}/debate` is called for a loaded ticker
- **THEN** HTTP 200 is returned with a complete `DebateResult` object including all round positions and synthesis
