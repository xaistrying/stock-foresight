# ticker-prediction

## Purpose

TBD

## Requirements

### Requirement: Serve a prediction from the persisted model and persisted features
The system SHALL expose `GET /tickers/{ticker}/prediction`, which computes a
prediction using the already-loaded XGBoost booster and the ticker's most
recently persisted `features` row. The system SHALL NOT recompute any
indicator column from `ohlcv` within this endpoint's request handling, and
SHALL NOT trigger ticker loading (`POST /tickers/{ticker}/load` or its
underlying `load_ticker`) as a side effect of this endpoint.

#### Scenario: Prediction served from a clean latest row
- **WHEN** a client requests `GET /tickers/{ticker}/prediction` for a ticker
  whose most recent `features` row has `near_gap = 0`
- **THEN** the system responds `200` with `status: "ok"` and a
  `predicted_log_return` field computed by the loaded model against that
  row's stored indicator columns

#### Scenario: No live recomputation of indicators
- **WHEN** the system serves any prediction under this endpoint
- **THEN** the feature values fed to the model come exclusively from the
  ticker's persisted `features` row and no indicator is recalculated from
  `ohlcv` during the request

### Requirement: Ticker with no persisted features returns 404
The system SHALL respond `404` when a ticker has no `features` rows at all,
and SHALL NOT attempt to load the ticker inline as part of handling this
request.

#### Scenario: Never-loaded ticker
- **WHEN** a client requests `GET /tickers/{ticker}/prediction` for a ticker
  with zero rows in the `features` table
- **THEN** the system responds `404` and does not call `load_ticker` or make
  any external `vnstock` request

### Requirement: Failed feature computation surfaces as a server error
The system SHALL respond with a `5xx` status when the ticker has been loaded
but its most recent feature-recomputation attempt failed
(`features_computed = 0` from the ingestion path), distinguishing this
unexpected-fault case from the routine `near_gap` data-availability case.
This check SHALL be evaluated before checking whether any `features` row
exists for the ticker, so a fault is never masked by `features` rows left
over from an earlier, successful load.

#### Scenario: Prior feature recomputation failure
- **WHEN** a client requests a prediction for a ticker whose most recent
  `load_ticker` call recorded `features_computed = 0`
- **THEN** the system responds with a `5xx` status rather than `200` or `404`

#### Scenario: Fault is not masked by stale rows from an earlier successful load
- **WHEN** a ticker was loaded successfully once (leaving `features` rows in
  place), then reloaded and its feature recomputation failed on that later
  attempt (`features_computed` now `0`)
- **THEN** the system responds with a `5xx` status rather than serving a
  prediction from the earlier load's now-stale `features` rows

#### Scenario: NULL features_computed does not trigger the fault path
- **WHEN** a client requests a prediction for a ticker whose `tickers` row
  exists and has `features_computed = NULL` (loaded only before this
  column existed, backfilled by migration) — a genuinely never-loaded
  ticker has no `tickers` row at all and is handled by the 404 requirement
  above, not this one
- **THEN** the system does not respond `5xx` on that basis alone, and
  instead evaluates the ticker's `features` rows as normal (404 if none
  exist, or the near_gap/ok branches otherwise)

### Requirement: Latest row near_gap refuses prediction without walking back
The system SHALL respond `200` with `status: "near_gap"` and SHALL NOT
include a `predicted_log_return` field when the ticker's most recent
`features` row has `near_gap = 1`. The system SHALL NOT substitute an older
`near_gap = 0` row to produce a prediction in this case.

#### Scenario: Latest row is near_gap
- **WHEN** a client requests a prediction for a ticker whose most recent
  `features` row has `near_gap = 1`
- **THEN** the system responds `200` with `status: "near_gap"` and the
  response body contains no `predicted_log_return` field

#### Scenario: No walk-back to an older clean row
- **WHEN** the ticker's most recent `features` row has `near_gap = 1` but an
  older row for the same ticker has `near_gap = 0`
- **THEN** the system still responds with `status: "near_gap"` and does not
  return a `predicted_log_return` derived from the older row

### Requirement: Response excludes AI-insight-panel fields
The system SHALL NOT include `confidence_score`, `sentiment_proxy`,
`advice_text`, or any other field from the AI insight panel response contract
in this endpoint's response, regardless of response `status`.

#### Scenario: Ok response has no confidence or sentiment fields
- **WHEN** the system responds with `status: "ok"` and a
  `predicted_log_return`
- **THEN** the response body contains no `confidence_score`,
  `sentiment_proxy`, or `advice_text` field

### Requirement: Model loaded once at startup; missing or corrupt artifact fails startup
The system SHALL load the persisted XGBoost booster once during application
startup (in the FastAPI lifespan handler) and store it for reuse across
requests. If the model artifact is missing or fails to load, the system
SHALL fail application startup rather than allow the application to start and
fail on a subsequent request.

#### Scenario: Application starts successfully with a valid model artifact
- **WHEN** the application starts and the persisted model file is present and
  valid
- **THEN** the model is loaded once during startup and is available to serve
  prediction requests without being reloaded per-request

#### Scenario: Missing model artifact fails startup
- **WHEN** the application starts and the persisted model file is missing or
  cannot be parsed
- **THEN** application startup fails and no request is served
