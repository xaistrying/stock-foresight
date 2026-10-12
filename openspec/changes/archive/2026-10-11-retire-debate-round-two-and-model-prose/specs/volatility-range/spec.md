## MODIFIED Requirements

### Requirement: Debate result and agent positions carry the calibrated range fields
`AgentPosition` (Technical agent only), `DebateResult` and the `POST /tickers/{ticker}/debate` JSON SHALL carry `range_5s_pct`, `sigma_daily_pct` and `range_coverage` in place of `volatility_range_pct`, which SHALL be removed with no deprecated alias. All three are null when the range service does not serve a band. `GET /tickers/{ticker}/prediction` SHALL NOT return `volatility_range_pct` either.

#### Scenario: Debate response shape
- **WHEN** a debate completes for a ticker with status `ok`
- **THEN** the JSON has `range_5s_pct`, `sigma_daily_pct` and `range_coverage` at the top level and in `round1.technical`, has no `round2` key, and has no `volatility_range_pct` key anywhere

#### Scenario: No band served
- **WHEN** the range status is `range_out_of_bounds` or `model_unavailable`
- **THEN** the three fields are null and the debate still completes
