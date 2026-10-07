## ADDED Requirements

### Requirement: The direction prediction endpoints are retired
The system SHALL NOT serve `GET /tickers/{ticker}/prediction` or `GET /tickers/{ticker}/insight`, and SHALL NOT load any XGBoost model at application startup. This capability is retired; it is kept as a stub so the retirement stays on record. The 5-session range is served by `GET /tickers/{ticker}/range` (`volatility-range`) and analysis by `POST /tickers/{ticker}/debate`.

#### Scenario: Retired routes answer 404
- **WHEN** a client requests `GET /tickers/{ticker}/prediction` or `GET /tickers/{ticker}/insight`
- **THEN** the system responds `404`

#### Scenario: Startup needs no model artifact
- **WHEN** the application starts and `backend/data/models/` holds no file
- **THEN** startup succeeds and `GET /tickers` answers `200`

## REMOVED Requirements

### Requirement: Serve a prediction from the persisted model and persisted features
**Reason**: The XGBoost direction model is retired (pooled out-of-fold hit-rate 47.8%, corr ~0.01; `docs/DISCUSSION_model_direction.md`) and the endpoint is deleted.
**Migration**: Use `GET /tickers/{ticker}/range` for the 5-session range and `POST /tickers/{ticker}/debate` for analysis. Nothing in the dashboard calls the removed endpoint after this change.

### Requirement: Ticker with no persisted features returns 404
**Reason**: The endpoint is deleted. The never-loaded 404 is kept by `GET /tickers/{ticker}/range` (`calibrate-volatility-range`) and `POST /tickers/{ticker}/debate` (`debate-data-guards`); the feature-row reader that supports it keeps a unit test.
**Migration**: Use `GET /tickers/{ticker}/range` for the 5-session range and `POST /tickers/{ticker}/debate` for analysis. Nothing in the dashboard calls the removed endpoint after this change.

### Requirement: Failed feature computation surfaces as a server error
**Reason**: The endpoint is deleted. The failed-features 5xx is kept by `/range` and `/debate`; the reader keeps a unit test.
**Migration**: Use `GET /tickers/{ticker}/range` for the 5-session range and `POST /tickers/{ticker}/debate` for analysis. Nothing in the dashboard calls the removed endpoint after this change.

### Requirement: Latest row near_gap refuses prediction without walking back
**Reason**: The endpoint is deleted. The no-walk-back rule is kept by the feature-row reader (`get_latest_features_row` returns the newest row only) and the near-gap refusal moves to `assess_eligibility` (`debate-data-guards`).
**Migration**: Use `GET /tickers/{ticker}/range` for the 5-session range and `POST /tickers/{ticker}/debate` for analysis. Nothing in the dashboard calls the removed endpoint after this change.

### Requirement: Response excludes AI-insight-panel fields
**Reason**: The endpoint is deleted.
**Migration**: Use `GET /tickers/{ticker}/range` for the 5-session range and `POST /tickers/{ticker}/debate` for analysis. Nothing in the dashboard calls the removed endpoint after this change.

### Requirement: Model loaded once at startup; missing or corrupt artifact fails startup
**Reason**: No model is loaded at startup. A missing model file must not stop the application from starting (the opposite of this requirement); the HAR model is loaded by the range service.
**Migration**: Use `GET /tickers/{ticker}/range` for the 5-session range and `POST /tickers/{ticker}/debate` for analysis. Nothing in the dashboard calls the removed endpoint after this change.

### Requirement: Null indicator columns on the latest row refuse prediction
**Reason**: The endpoint is deleted. The null-indicator refusal moves to `assess_eligibility`'s `indicators_missing` reason (`debate-data-guards`).
**Migration**: Use `GET /tickers/{ticker}/range` for the 5-session range and `POST /tickers/{ticker}/debate` for analysis. Nothing in the dashboard calls the removed endpoint after this change.

### Requirement: Advice is never derived from missing indicator values
**Reason**: `GET /tickers/{ticker}/insight` is deleted together with Advice.
**Migration**: Use `GET /tickers/{ticker}/range` for the 5-session range and `POST /tickers/{ticker}/debate` for analysis. Nothing in the dashboard calls the removed endpoint after this change.

### Requirement: Prediction endpoint returns volatility range in addition to model output
**Reason**: The endpoint is deleted. The range is served by `GET /tickers/{ticker}/range`, and the per-session figure this field carried (`volatility_range_pct`) is superseded by `range_5s_pct` (`calibrate-volatility-range`).
**Migration**: Use `GET /tickers/{ticker}/range` for the 5-session range and `POST /tickers/{ticker}/debate` for analysis. Nothing in the dashboard calls the removed endpoint after this change.
