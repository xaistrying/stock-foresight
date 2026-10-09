## MODIFIED Requirements

### Requirement: Debate engine runs three agents in parallel for Round 1
The engine SHALL invoke TechnicalAgent, NewsAgent, and MacroAgent concurrently (asyncio) in one round, named Round 1 in the result (`round1`); there is no second round. Each agent returns a `AgentPosition` object: `{ agent_id, stance, reasoning, degraded_reason }` where `stance ∈ {bull, bear, neutral}`, `reasoning` is a list of bullet strings and `degraded_reason` is `null` for a live agent or one of the codes defined by the degraded-agent requirement. The Technical agent's position additionally carries the range fields defined by the `volatility-range` capability. Only the News agent calls a language model (to read the headlines and give its stance and bullets); the Technical and Macro stances and bullets are computed. An agent that raises, or that reports it could not form a stance, is **degraded**: it SHALL NOT be given a neutral vote.

#### Scenario: All three agents complete Round 1
- **WHEN** `POST /tickers/{ticker}/debate` is called for an eligible ticker
- **THEN** all three agents are invoked concurrently, all three positions are collected in `round1`, and the verdict is computed from them with no further agent or language-model call

#### Scenario: One agent fails in Round 1
- **WHEN** one agent raises an exception or times out during Round 1
- **THEN** its position has `stance: "neutral"`, `reasoning: ["Agent unavailable — analysis could not be completed."]` and `degraded_reason: "agent_error"`, it is listed in `agents_degraded`, and the debate proceeds with the two live agents

#### Scenario: Two agents fail in Round 1
- **WHEN** two agents are degraded after Round 1
- **THEN** the result is `INSUFFICIENT_DATA`

#### Scenario: Only News calls a language model
- **WHEN** a run completes for an eligible ticker
- **THEN** the only language-model call made is the News agent's, and the Technical and Macro agents construct no language-model client

### Requirement: Debate engine produces a structured `DebateResult` object
After the vote, the engine SHALL return a `DebateResult`:
```
{
  ticker, as_of, data_as_of, data_age_sessions,
  verdict, agreement_level,
  eligibility: { eligible, reasons },
  agents_degraded,
  round1: { technical, news, macro },
  range_5s_pct, sigma_daily_pct, range_coverage,
  duration_ms
}
```
The result has no `round2` and no `synthesis` (no key tension and no synthesis text).  
`verdict ∈ {STRONG_BUY_SIGNAL, BUY_SIGNAL, OBSERVE, CAUTION_SIGNAL, STRONG_CAUTION_SIGNAL, SPLIT, INSUFFICIENT_DATA}`  
`agreement_level ∈ {unanimous, majority, split, none}` (`none` only with `INSUFFICIENT_DATA`)  
`agents_degraded` is the list of degraded agent ids in the order technical, news, macro; each position in `round1` carries `degraded_reason`. `range_5s_pct`, `sigma_daily_pct` and `range_coverage` (the nominal coverage of the band, `null` when the range is uncalibrated or unavailable) are defined by the `volatility-range` capability (they replace `volatility_range_pct`); the Technical agent's position carries the same three fields. With three live agents the verdict follows the stance mapping below; verdicts for fewer live agents are defined by the `debate-synthesiser` capability.

#### Scenario: All agents agree bullish
- **WHEN** all three Round 1 stances are `bull` and no agent is degraded
- **THEN** `verdict = STRONG_BUY_SIGNAL`, `agreement_level = unanimous`, `agents_degraded = []`

#### Scenario: Two agents agree, one dissents
- **WHEN** two Round 1 stances are `bull` and one is `bear` or `neutral`, all three live
- **THEN** `verdict = BUY_SIGNAL`, `agreement_level = majority`

#### Scenario: Agents split with no majority direction
- **WHEN** Round 1 stances are one of each (`bull`, `neutral`, `bear`)
- **THEN** `verdict = SPLIT`, `agreement_level = split`

#### Scenario: Range fields on the result
- **WHEN** the Technical agent computed a calibrated range
- **THEN** the result carries `range_5s_pct`, `sigma_daily_pct` and `range_coverage`; when it is uncalibrated `range_coverage` is `null`, and on an `INSUFFICIENT_DATA` result all three are `null`

#### Scenario: Two neutral and one directional
- **WHEN** two Round 1 stances are `neutral` and one is `bull` or `bear`, all three live
- **THEN** `verdict = OBSERVE`, `agreement_level = majority` (the directional stance is not enough for a directional verdict)

#### Scenario: No second round and no synthesis in the result
- **WHEN** a result is serialised for a completed run
- **THEN** it has a `round1` object and no `round2` key and no `synthesis` key

### Requirement: Debate endpoint is `POST /tickers/{ticker}/debate`
The API SHALL expose `POST /tickers/{ticker}/debate` returning a `DebateResult` JSON. The endpoint requires the ticker to be loaded (features exist); returns HTTP 404 if not loaded, HTTP 503 if feature computation failed.

#### Scenario: Ticker not loaded
- **WHEN** `POST /tickers/{ticker}/debate` is called for a ticker with no loaded features
- **THEN** HTTP 404 is returned with `{ detail: "Ticker has not been loaded" }`

#### Scenario: Analysis completes successfully
- **WHEN** `POST /tickers/{ticker}/debate` is called for a loaded ticker
- **THEN** HTTP 200 is returned with a complete `DebateResult` object including the `round1` positions, and with no `round2` and no `synthesis`

### Requirement: Ineligible tickers return INSUFFICIENT_DATA without running agents
Before any agent runs, `POST /tickers/{ticker}/debate` SHALL call `assess_eligibility` (after the existing 404 and 503 checks). When the ticker is not eligible it SHALL return HTTP 200 with `verdict = INSUFFICIENT_DATA`, `agreement_level = none`, `eligibility` (with every reason), `data_as_of`, `data_age_sessions`, empty `round1` and `agents_degraded`, and null range fields. It SHALL make no LLM call, no market-data fetch, and SHALL NOT write a report file.

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

### Requirement: Degraded agents are defined by an untrustworthy stance, not by failed prose
An agent is degraded when its stance, not just its wording, cannot be trusted. `degraded_reason` SHALL be one of: `agent_error` (the agent raised), `no_input` (nothing to form a stance from), `llm_failed` (a stance that only the LLM can supply failed or had no recognisable stance line). Technical: no usable indicator is `no_input`. News: every feed failing, or no headlines, is `no_input`; the LLM raising, or a reply with no recognisable stance line, is `llm_failed`. Macro: no counted signal is `no_input`. The Technical and Macro agents make no language-model call, so neither can be `llm_failed`, and each states its computed values as its reasoning.

#### Scenario: News LLM fails
- **WHEN** headlines were fetched but the News LLM call raises
- **THEN** the News position has `degraded_reason: "llm_failed"` and is in `agents_degraded`, and its reasoning says the language-model analysis failed, not that feeds could not be fetched

#### Scenario: News reply without a stance
- **WHEN** the News reply is "Verdict: bear" style text with no recognisable stance line
- **THEN** News is `llm_failed`, not neutral

#### Scenario: All feeds fail
- **WHEN** every news feed fails
- **THEN** News is degraded with `no_input`

#### Scenario: Technical stance computed with no model
- **WHEN** the indicators give `bull`
- **THEN** the Technical agent is live with stance `bull` and reasoning bullets listing the computed values, and no language-model call was made

#### Scenario: No technical indicator
- **WHEN** RSI, MACD histogram and Tenkan/Kijun are all null
- **THEN** the Technical agent is degraded with `no_input`

## REMOVED Requirements

### Requirement: Debate engine runs a response round (Round 2) in parallel
**Reason**: Round 2 asks each agent to revise its stance after reading the others' bullets, which are written from the same data (the 2026-10-08 SAB report shows Macro citing News and News citing Macro). It costs three model calls per run and adds no evidence. The owner chose a pure removal as step 1 of `docs/DISCUSSION_describe_not_vote_redesign.md`.
**Migration**: The vote is taken over the Round 1 positions (see `debate-synthesiser`). The `round2` key and the `round2_failed` degraded reason are removed from the result, the response and the panel; the `r2_*` log columns are kept and written NULL (see `debate-outcome-log`).
