# ticker-catalog

## Purpose

TBD

## Requirements

### Requirement: Serve the fixed set of model-validated tickers
The system SHALL expose `GET /tickers`, which returns exactly the tickers
in `TRAINING_TICKERS` (`backend/app/ml/training.py`) — the set the model
was trained and backtested on (`docs/MODEL_CARD.md`) — and SHALL NOT
maintain any second, independently-edited list of these tickers anywhere
in the codebase.

#### Scenario: Response contains exactly the training set
- **WHEN** a client requests `GET /tickers`
- **THEN** the system responds `200` with one entry per ticker in
  `TRAINING_TICKERS`, no fewer and no additional tickers

#### Scenario: Training set change requires no second edit
- **WHEN** `TRAINING_TICKERS` is changed in `backend/app/ml/training.py`
  (e.g. a ticker added or removed in a future retrain)
- **THEN** `GET /tickers`'s response set changes accordingly without any
  other file needing to be edited to keep the two in sync

### Requirement: Per-ticker load status from the tickers table
Each entry in `GET /tickers`'s response SHALL include that ticker's
`loaded`, `features_computed`, and `last_loaded_at` status, derived from
the `tickers` table, so a client can distinguish a validated ticker that
has never been loaded from one that has.

#### Scenario: Ticker with no tickers row
- **WHEN** a ticker in `TRAINING_TICKERS` has no corresponding row in the
  `tickers` table (never loaded)
- **THEN** its entry in the response indicates not-loaded (e.g.
  `loaded: false`) and `features_computed` and `last_loaded_at` are null
  rather than the request failing

#### Scenario: Ticker with a tickers row
- **WHEN** a ticker in `TRAINING_TICKERS` has a corresponding row in the
  `tickers` table
- **THEN** its entry reflects that row's `features_computed` and
  `last_loaded_at` values

### Requirement: Read-only, no side effects
`GET /tickers` SHALL NOT call `load_ticker`, trigger any `vnstock`
request, or write to any table. It only reads `TRAINING_TICKERS` and the
existing `tickers` table.

#### Scenario: Request does not trigger ingestion
- **WHEN** a client requests `GET /tickers`
- **THEN** no external `vnstock` call is made and no row in `ohlcv`,
  `tickers`, or `features` is written as a result of this request
</content>
