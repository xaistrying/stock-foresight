# ticker-prediction

## Purpose

TBD

## Requirements

### Requirement: The direction prediction endpoints are retired
The system SHALL NOT serve `GET /tickers/{ticker}/prediction` or `GET /tickers/{ticker}/insight`, and SHALL NOT load any XGBoost model at application startup. This capability is retired; it is kept as a stub so the retirement stays on record. The 5-session range is served by `GET /tickers/{ticker}/range` (`volatility-range`) and analysis by `POST /tickers/{ticker}/debate`.

#### Scenario: Retired routes answer 404
- **WHEN** a client requests `GET /tickers/{ticker}/prediction` or `GET /tickers/{ticker}/insight`
- **THEN** the system responds `404`

#### Scenario: Startup needs no model artifact
- **WHEN** the application starts and `backend/data/models/` holds no file
- **THEN** startup succeeds and `GET /tickers` answers `200`
