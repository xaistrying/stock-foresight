## MODIFIED Requirements

### Requirement: Serve a prediction from the persisted model and persisted features
The system SHALL expose `GET /tickers/{ticker}/prediction`, which computes a
prediction using the already-loaded XGBoost booster and the ticker's most
recently persisted `features` row. The system SHALL NOT recompute any
indicator column from `ohlcv` within this endpoint's request handling, and
SHALL NOT trigger ticker loading (`POST /tickers/{ticker}/load` or its
underlying `load_ticker`) as a side effect of this endpoint.

#### Scenario: Prediction served from a clean latest row
- **WHEN** a client requests `GET /tickers/{ticker}/prediction` for a ticker
  whose most recent `features` row has `near_gap = 0` and no null indicator
  column
- **THEN** the system responds `200` with `status: "ok"` and a
  `predicted_log_return` field computed by the loaded model against that
  row's stored indicator columns

#### Scenario: No live recomputation of indicators
- **WHEN** the system serves any prediction under this endpoint
- **THEN** the feature values fed to the model come exclusively from the
  ticker's persisted `features` row and no indicator is recalculated from
  `ohlcv` during the request

## ADDED Requirements

### Requirement: Null indicator columns on the latest row refuse prediction
The system SHALL respond `200` with `status: "indicators_unavailable"` and
SHALL NOT include a `predicted_log_return` when the ticker's most recent
`features` row has any null indicator column, whatever nulled it — a
quality-gate blackout over a price discontinuity
(`ohlcv-quality-gate`), a series too short to seed an indicator, or any
future cause. The system SHALL NOT substitute an older complete row to
produce a prediction, matching how the `near_gap` refusal already behaves.

This check SHALL read the indicator columns themselves rather than any
flag column, so it cannot drift out of sync with the actual nulls, and
SHALL be independent of `near_gap`, which describes gaps in trading
sessions and carries no claim about price discontinuities.

#### Scenario: Latest row has null indicators and a clear calendar-gap flag
- **WHEN** a ticker's most recent `features` row has `near_gap = 0` and one
  or more null indicator columns
- **THEN** the system responds `200` with
  `status: "indicators_unavailable"` and no `predicted_log_return` field,
  rather than a number computed from the missing values

#### Scenario: One null indicator is enough to refuse
- **WHEN** a ticker's most recent `features` row has exactly one null
  indicator column and the rest populated
- **THEN** the system still refuses, because the model treats a missing
  input as missing rather than erroring, so the endpoint is what must
  refuse

#### Scenario: No walking back to an older complete row
- **WHEN** a ticker's most recent `features` row has null indicator columns
  but an older row for the same ticker is complete
- **THEN** the system still responds `status: "indicators_unavailable"` and
  does not serve a prediction derived from the older row

### Requirement: Advice is never derived from missing indicator values
`GET /tickers/{ticker}/insight` SHALL NOT serve `advice_text` when the
ticker's most recent `features` row has any null indicator column, because
Advice is computed from the model's output and would otherwise carry Rule 3
directional wording derived entirely from missing values. Confidence and
Sentiment SHALL still be reported, as neither reads the model's output.

#### Scenario: Insight refuses Advice on a null-indicator row
- **WHEN** a client requests `GET /tickers/{ticker}/insight` for a ticker
  whose most recent `features` row has null indicator columns
- **THEN** the response carries `advice_text: null` with a note naming the
  reason, alongside the ticker's Confidence and Sentiment values
