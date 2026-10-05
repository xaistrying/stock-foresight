## ADDED Requirements

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
The TechnicalAgent SHALL compute a HAR-RV volatility range estimate using a linear model trained on trailing close-to-close volatility (5-session, 20-session, 60-session windows). The output `volatility_range_pct` is the predicted ±% range for the next 5 TRADING SESSIONS (Rule 1). It MUST be displayed as a percentage in the UI, never as a raw log value (Rule 2).

#### Scenario: Volatility range computed successfully
- **WHEN** at least 60 sessions of OHLCV history exist for the ticker
- **THEN** `volatility_range_pct` is a positive float representing the ±% expected range, e.g. `2.1` means ±2.1%

#### Scenario: Insufficient history for volatility estimate
- **WHEN** fewer than 60 sessions of OHLCV history exist
- **THEN** `volatility_range_pct` is `null` and the reasoning bullet notes "Insufficient history for volatility estimate"

### Requirement: Technical Agent reasoning is 3–5 structured bullets
The TechnicalAgent SHALL produce `reasoning` as a list of 3–5 plain-language bullet strings. Each bullet MUST reference a specific indicator value or comparison, not a generic statement. The LLM prompt provides the computed indicator values; the LLM translates them into readable bullets.

#### Scenario: Reasoning references specific values
- **WHEN** RSI is 62 and MACD histogram is +0.12
- **THEN** reasoning includes a bullet citing RSI at 62 (above 55) and a bullet citing MACD histogram positive
