# technical-agent

## Purpose

TBD
## Requirements
### Requirement: Technical Agent reads indicator feature row and computes a stance
The TechnicalAgent SHALL read the ticker's feature row from the database (the row dated `as_of`, as the `debate-engine` capability requires) and derive a `stance ∈ {bull, bear, neutral}` from RSI, MACD histogram, and Ichimoku (Tenkan/Kijun) position (Rule 5 honored: this is a technical proxy, labeled "Technical Signal" in the UI). The agent uses majority vote across the three indicators. The agent computes the stance itself and makes no language-model call.

#### Scenario: Bullish technical picture
- **WHEN** RSI ≥ 55, MACD histogram > 0, and Tenkan > Kijun
- **THEN** stance is `bull` with reasoning listing the RSI, MACD histogram, Tenkan-sen and Kijun-sen values

#### Scenario: Mixed signals
- **WHEN** indicators are split (e.g. RSI bullish, MACD bearish, Ichimoku neutral)
- **THEN** stance is `neutral` with reasoning listing the same values, which show the conflict

#### Scenario: Indicators unavailable (warm-up or quality-gate blackout)
- **WHEN** one or more indicator columns are NULL in the feature row
- **THEN** stance is `neutral` with reasoning `["Indicator data unavailable for this session"]`; available indicators are still evaluated

### Requirement: Technical Agent computes a 5-session volatility range estimate (Rule 1, Rule 2)
The TechnicalAgent SHALL obtain the calibrated 5-session band (`range_5s_pct`, `sigma_daily_pct`, `range_coverage`) from the range service defined by the `volatility-range` capability, for the next 5 TRADING SESSIONS (Rule 1). It MUST NOT re-derive eligibility, bounds or calibration itself. The band is a "typical 5-session move": `range_5s_pct = range_k × √5 × sigma_daily_pct`, shown as a percentage, never a raw log value (Rule 2). `AgentPosition` carries `range_5s_pct`, `sigma_daily_pct` and `range_coverage`. The agent's reasoning bullets SHALL NOT state the band, its coverage or the daily volatility figure: the Verdict panel's range block and the export Summary state the band and its coverage (Rules 1, 2 and 4), and the daily figure is never shown as a 5-session figure.

#### Scenario: Calibrated range on the position
- **WHEN** the range service returns status `ok` with `range_5s_pct` 4.02, `sigma_daily_pct` 1.50 and `range_coverage` 0.68
- **THEN** the returned `AgentPosition` carries all three fields, and no reasoning bullet contains "Typical 5-session move", the coverage phrase or the daily figure

#### Scenario: Uncalibrated ticker
- **WHEN** the range service returns status `uncalibrated` (`range_coverage` null)
- **THEN** the position carries `range_5s_pct` and `sigma_daily_pct` with `range_coverage` null, and no reasoning bullet makes a coverage claim

#### Scenario: No range served
- **WHEN** the range service returns `ineligible`, `range_out_of_bounds` or `model_unavailable`
- **THEN** `range_5s_pct`, `sigma_daily_pct` and `range_coverage` are null and the agent MUST NOT estimate one

#### Scenario: A failing range service does not stop the agent
- **WHEN** the range service raises
- **THEN** the three fields are null and the agent still returns its stance and its values list

### Requirement: Technical Agent reasoning lists the computed indicator values
The TechnicalAgent SHALL produce `reasoning` as one bullet per available indicator value, in this order and with these labels: `RSI: <value>`, `MACD histogram: <value>`, `Ichimoku Tenkan-sen: <value>`, `Ichimoku Kijun-sen: <value>`. Each value is the number the agent computed from the feature row: RSI to one decimal, the MACD histogram to four decimals, Tenkan-sen and Kijun-sen to two. The agent SHALL NOT call a language model for its reasoning, and its bullets are computed values, not model-written text (Rule 5).

#### Scenario: Reasoning lists specific values
- **WHEN** RSI is 62 and MACD histogram is +0.12
- **THEN** reasoning includes `RSI: 62.0` and `MACD histogram: 0.12`

#### Scenario: Only available indicators are listed
- **WHEN** the MACD histogram is NULL and the other indicators are present
- **THEN** reasoning has no MACD bullet and still lists RSI, Tenkan-sen and Kijun-sen

#### Scenario: No model is needed
- **WHEN** the agent runs while every language-model call would raise
- **THEN** it returns its position with the values list and is not degraded

