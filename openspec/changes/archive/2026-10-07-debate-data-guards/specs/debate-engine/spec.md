## MODIFIED Requirements

### Requirement: Debate engine runs three agents in parallel for Round 1
The engine SHALL invoke TechnicalAgent, NewsAgent, and MacroAgent concurrently (asyncio) for Round 1. Each agent returns a `AgentPosition` object: `{ agent_id, stance, reasoning, degraded_reason }` where `stance ∈ {bull, bear, neutral}`, `reasoning` is a list of 3–5 bullet strings and `degraded_reason` is `null` for a live agent or one of the codes defined by the degraded-agent requirement. The Technical agent's position additionally carries the range fields defined by the `volatility-range` capability. An agent that raises, or that reports it could not form a stance, is **degraded**: it SHALL NOT be given a neutral vote.

#### Scenario: All three agents complete Round 1
- **WHEN** `POST /tickers/{ticker}/debate` is called for an eligible ticker
- **THEN** all three agents are invoked concurrently and all three positions are collected before Round 2 begins

#### Scenario: One agent fails in Round 1
- **WHEN** one agent raises an exception or times out during Round 1
- **THEN** its position has `stance: "neutral"`, `reasoning: ["Agent unavailable — analysis could not be completed."]` and `degraded_reason: "agent_error"`, it is listed in `agents_degraded`, and the debate proceeds with the two live agents

#### Scenario: Two agents fail in Round 1
- **WHEN** two agents are degraded after Round 1
- **THEN** Round 2 and the synthesis LLM calls are not made and the result is `INSUFFICIENT_DATA`

### Requirement: Debate engine runs a response round (Round 2) in parallel
After collecting Round 1 positions, the engine SHALL pass each **live** agent its own Round 1 position plus the other positions, and invoke those response calls concurrently. Degraded agents SHALL NOT be called in Round 2. Each live agent returns an updated `AgentPosition` (may differ from Round 1 or remain unchanged). A Round 2 call that raises, returns a blank reply, or returns a reply without a recognisable stance line makes that agent degraded with `degraded_reason: "round2_failed"`: its Round 1 position and a note stay visible in `round2`, but it is excluded from the vote.

#### Scenario: Agent holds its Round 1 position in Round 2
- **WHEN** an agent's Round 2 prompt does not find a compelling counter-argument
- **THEN** the Round 2 position has the same `stance` as Round 1 but MAY add a rebuttal to `reasoning`

#### Scenario: Agent shifts stance in Round 2
- **WHEN** an agent finds a specific counter-argument from another agent compelling
- **THEN** the Round 2 `stance` MAY differ from Round 1, and `reasoning` MUST explain the shift

#### Scenario: Round 2 call fails
- **WHEN** the Round 2 call for a live agent raises
- **THEN** that agent is in `agents_degraded` with `degraded_reason: "round2_failed"`, its `round2` entry shows its Round 1 stance and reasoning plus "Round 2 unavailable — Round 1 position kept, not counted in the vote.", and it does not vote

#### Scenario: Unrecognised Round 2 stance
- **WHEN** a Round 2 reply has no recognisable stance line
- **THEN** the call is treated as failed (`round2_failed`), not as a kept stance

#### Scenario: LLM provider down
- **WHEN** every LLM call fails
- **THEN** News is degraded (`llm_failed`) in Round 1, Technical and Macro are degraded (`round2_failed`) in Round 2, and the verdict is `INSUFFICIENT_DATA`

### Requirement: Debate engine produces a structured `DebateResult` object
After synthesis, the engine SHALL return a `DebateResult`:
```
{
  ticker, as_of, data_as_of, data_age_sessions,
  verdict, agreement_level,
  eligibility: { eligible, reasons },
  agents_degraded,
  round1: { technical, news, macro },
  round2: { technical, news, macro },
  synthesis: { verdict, agreement_level, key_tension, reasoning },
  range_5s_pct, sigma_daily_pct, range_coverage,
  duration_ms
}
```
`verdict ∈ {STRONG_BUY_SIGNAL, BUY_SIGNAL, OBSERVE, CAUTION_SIGNAL, STRONG_CAUTION_SIGNAL, SPLIT, INSUFFICIENT_DATA}`  
`agreement_level ∈ {unanimous, majority, split, none}` (`none` only with `INSUFFICIENT_DATA`)  
`agents_degraded` is the list of degraded agent ids in the order technical, news, macro; each position in `round1` and `round2` carries `degraded_reason`. `range_5s_pct`, `sigma_daily_pct` and `range_coverage` (the nominal coverage of the band, `null` when the range is uncalibrated or unavailable) are defined by the `volatility-range` capability (they replace `volatility_range_pct`); the Technical agent's position carries the same three fields. With three live agents the verdict follows the stance mapping below; verdicts for fewer live agents are defined by the `debate-synthesiser` capability.

#### Scenario: All agents agree bullish
- **WHEN** all three Round 2 stances are `bull` and no agent is degraded
- **THEN** `verdict = STRONG_BUY_SIGNAL`, `agreement_level = unanimous`, `agents_degraded = []`

#### Scenario: Two agents agree, one dissents
- **WHEN** two Round 2 stances are `bull` and one is `bear` or `neutral`, all three live
- **THEN** `verdict = BUY_SIGNAL`, `agreement_level = majority`

#### Scenario: Agents split with no majority direction
- **WHEN** Round 2 stances are one of each (`bull`, `neutral`, `bear`)
- **THEN** `verdict = SPLIT`, `agreement_level = split`

#### Scenario: Range fields on the result
- **WHEN** the Technical agent computed a calibrated range
- **THEN** the result carries `range_5s_pct`, `sigma_daily_pct` and `range_coverage`; when it is uncalibrated `range_coverage` is `null`, and on an `INSUFFICIENT_DATA` result all three are `null`

#### Scenario: Two neutral and one directional
- **WHEN** two Round 2 stances are `neutral` and one is `bull` or `bear`, all three live
- **THEN** `verdict = OBSERVE`, `agreement_level = majority` (the directional stance is not enough for a directional verdict)

## ADDED Requirements

### Requirement: Ineligible tickers return INSUFFICIENT_DATA without running agents
Before any agent runs, `POST /tickers/{ticker}/debate` SHALL call `assess_eligibility` (after the existing 404 and 503 checks). When the ticker is not eligible it SHALL return HTTP 200 with `verdict = INSUFFICIENT_DATA`, `agreement_level = none`, `eligibility` (with every reason), `data_as_of`, `data_age_sessions`, empty `round1`, `round2` and `agents_degraded`, null range fields, and empty `synthesis.key_tension` and `synthesis.reasoning`. It SHALL make no LLM call, no market-data fetch, and SHALL NOT write a report file.

#### Scenario: Stale ticker
- **WHEN** the ticker's `age_sessions` is 21
- **THEN** HTTP 200 is returned with `verdict = INSUFFICIENT_DATA` and `eligibility.reasons` containing `stale`

#### Scenario: No LLM or export on refusal
- **WHEN** the ticker is ineligible
- **THEN** no LLM client call is made, no news or macro fetch is made, and no file is written under `reports/`

#### Scenario: Ticker not loaded still 404
- **WHEN** the ticker has no features row
- **THEN** HTTP 404 `{ detail: "Ticker has not been loaded" }` is returned, not a 200

#### Scenario: Several reasons are all returned
- **WHEN** a ticker is delisted, stale and has a hard flag
- **THEN** `eligibility.reasons` lists all three in the fixed order

### Requirement: as_of is the date of the data used
`as_of` and `data_as_of` SHALL be the date of the features row returned by `assess_eligibility`, never the system date and never dependent on whether an agent completed. `data_age_sessions` SHALL be its `age_sessions`. The Technical agent SHALL read the features row dated `as_of`, not the latest row at call time. The engine SHALL NOT fall back to `date.today()`.

#### Scenario: Technical agent fails
- **WHEN** the Technical agent raises in Round 1
- **THEN** `as_of` is still the features row date

#### Scenario: Refresh during a debate
- **WHEN** a newer features row is stored while the debate runs
- **THEN** the Technical agent still reads the row dated `as_of`, and the report filename and title use that date

#### Scenario: System date differs
- **WHEN** the latest features row is 2026-10-02 and the system date is 2026-10-06
- **THEN** `as_of = "2026-10-02"` and `data_age_sessions` reflects the difference

### Requirement: Degraded agents are defined by an untrustworthy stance, not by failed prose
An agent is degraded when its stance, not just its wording, cannot be trusted. `degraded_reason` SHALL be one of: `agent_error` (the agent raised in Round 1), `no_input` (nothing to form a stance from), `llm_failed` (a stance that only the LLM can supply failed or had no recognisable stance line, Round 1), `round2_failed` (see Round 2). Technical: no usable indicator is `no_input`. News: every feed failing, or no headlines, is `no_input`; the LLM raising, or a reply with no recognisable stance line, is `llm_failed`. Macro: no counted signal is `no_input`. An LLM failure that only affects the written bullets of Technical or Macro SHALL NOT degrade the agent, and Technical's fallback bullets SHALL state the computed indicator values rather than claim the data is unavailable.

#### Scenario: News LLM fails
- **WHEN** headlines were fetched but the News LLM call raises
- **THEN** the News position has `degraded_reason: "llm_failed"` and is in `agents_degraded`, and its reasoning says the language-model analysis failed, not that feeds could not be fetched

#### Scenario: News reply without a stance
- **WHEN** the News reply is "Verdict: bear" style text with no recognisable stance line
- **THEN** News is `llm_failed`, not neutral

#### Scenario: All feeds fail
- **WHEN** every news feed fails
- **THEN** News is degraded with `no_input`

#### Scenario: Technical prose fails, stance computed
- **WHEN** the indicators give `bull` but the LLM call raises
- **THEN** the Technical agent stays live with stance `bull` and reasoning bullets listing the computed values

#### Scenario: No technical indicator
- **WHEN** RSI, MACD histogram and Tenkan/Kijun are all null
- **THEN** the Technical agent is degraded with `no_input`
