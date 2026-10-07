# technical-agent

## Purpose

TBD

## Requirements

### Requirement: Technical Agent reads indicator feature row and computes a stance
The TechnicalAgent SHALL read the ticker's latest feature row from the database (same row used by the existing insight endpoint) and derive a `stance ∈ {bull, bear, neutral}` from RSI, MACD histogram, and Ichimoku (Tenkan/Kijun) position — the same signals as the existing `_compute_sentiment` function in `backend/app/api/insight.py` (Rule 5 honored: this is a technical proxy, labeled "Technical Signal" in the UI). The agent uses majority vote across the three indicators.

#### Scenario: Bullish technical picture
- **WHEN** RSI ≥ 55, MACD histogram > 0, and Tenkan > Kijun
- **THEN** stance is `bull` with reasoning citing all three indicators

#### Scenario: Mixed signals
- **WHEN** indicators are split (e.g. RSI bullish, MACD bearish, Ichimoku neutral)
- **THEN** stance is `neutral` with reasoning citing the conflicting signals

#### Scenario: Indicators unavailable (warm-up or quality-gate blackout)
- **WHEN** one or more indicator columns are NULL in the feature row
- **THEN** stance is `neutral` with reasoning `["Indicator data unavailable for this session"]`; available indicators are still evaluated

### Requirement: Technical Agent computes a 5-session volatility range estimate (Rule 1, Rule 2)
The TechnicalAgent SHALL obtain the calibrated 5-session band (`range_5s_pct`, `sigma_daily_pct`, `range_coverage`) from the range service defined by the `volatility-range` capability, for the next 5 TRADING SESSIONS (Rule 1). It MUST NOT re-derive eligibility, bounds or calibration itself. The band is a "typical 5-session move": `range_5s_pct = range_k × √5 × sigma_daily_pct`, shown as a percentage, never a raw log value (Rule 2). The Technical prompt SHALL state it as `Typical 5-session move: ±X% (about 2 in 3 of past 5-session moves stayed within this band; daily volatility forecast Y%)` (the coverage phrase derived from `range_coverage`), SHALL instruct the model that the figure is a size, not a direction, a ceiling or a prediction, and SHALL NOT call it "expected". `AgentPosition` carries `range_5s_pct`, `sigma_daily_pct` and `range_coverage`.

#### Scenario: Calibrated range in the prompt
- **WHEN** the range service returns status `ok` with `range_5s_pct` 4.02, `sigma_daily_pct` 1.50 and `range_coverage` 0.68
- **THEN** the prompt contains "Typical 5-session move: ±4.0%" with the "about 2 in 3" clause and "daily volatility forecast 1.50%", and the returned `AgentPosition` carries all three fields

#### Scenario: Uncalibrated ticker
- **WHEN** the range service returns status `uncalibrated` (`range_coverage` null)
- **THEN** the prompt states the band with "coverage not established for this stock" and makes no coverage claim

#### Scenario: No range served
- **WHEN** the range service returns `ineligible`, `range_out_of_bounds` or `model_unavailable`
- **THEN** `range_5s_pct`, `sigma_daily_pct` and `range_coverage` are null, the prompt line reads "Typical 5-session move: unavailable", and the agent MUST NOT estimate one

### Requirement: Technical Agent reasoning is 3–5 structured bullets
The TechnicalAgent SHALL produce `reasoning` as a list of 3–5 plain-language bullet strings. Each bullet MUST reference a specific indicator value or comparison, not a generic statement. The LLM prompt provides the computed indicator values; the LLM translates them into readable bullets.

#### Scenario: Reasoning references specific values
- **WHEN** RSI is 62 and MACD histogram is +0.12
- **THEN** reasoning includes a bullet citing RSI at 62 (above 55) and a bullet citing MACD histogram positive
