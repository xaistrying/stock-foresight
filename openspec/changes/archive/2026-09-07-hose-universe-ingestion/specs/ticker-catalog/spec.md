## MODIFIED Requirements

### Requirement: Serve the fixed set of model-validated tickers
The system SHALL expose `GET /tickers`, which returns the tickers in the
ingested universe (`ticker-universe`) that pass the universe's default
filters, and SHALL NOT maintain any second, independently-edited list of
tickers anywhere in the codebase. Each entry SHALL indicate whether that
ticker is part of `TRAINING_TICKERS` (`backend/app/ml/training.py`) — the
set the model was trained and backtested on (`docs/MODEL_CARD.md`) — so a
client can distinguish a ticker the system knows about from one the model
was actually validated on. These two sets are no longer identical.

Every `TRAINING_TICKERS` member SHALL appear in the response whether or
not it passes those filters, and whether or not the universe holds a row
for it. The model was trained on those tickers, so a client must be able
to show and predict them; dropping one because a re-tuned liquidity
threshold crossed its measured value would leave a dashboard silently
inconsistent with the model it serves. Their universe-sourced fields are
null when the universe has no row.

#### Scenario: A training ticker excluded by a filter is still served
- **WHEN** a `TRAINING_TICKERS` member is flagged as failing the liquidity
  or minimum-history filter
- **THEN** it still appears in `GET /tickers`, marked as part of the
  training set

#### Scenario: A training ticker absent from the universe is still served
- **WHEN** a `TRAINING_TICKERS` member has no `ticker_universe` row at all
- **THEN** it still appears, with its exchange, industry classification and
  listing status null rather than the entry being omitted

#### Scenario: Response is derived from the universe
- **WHEN** a client requests `GET /tickers`
- **THEN** the system responds `200` with one entry per universe ticker
  passing the default filters, and no ticker absent from the universe
  appears in the response

#### Scenario: Training membership is marked per entry
- **WHEN** a client requests `GET /tickers`
- **THEN** each entry indicates whether that ticker is in
  `TRAINING_TICKERS`, and the tickers so marked are exactly the members of
  `TRAINING_TICKERS`

#### Scenario: Training set change requires no second edit
- **WHEN** `TRAINING_TICKERS` is changed in `backend/app/ml/training.py`
  (e.g. a ticker added or removed in a future retrain)
- **THEN** the training-membership marking in `GET /tickers`'s response
  changes accordingly without any other file needing to be edited to keep
  the two in sync

#### Scenario: Universe change requires no second edit
- **WHEN** the ingested universe changes
- **THEN** `GET /tickers`'s response set changes accordingly without any
  hand-maintained ticker list needing to be edited

### Requirement: Per-ticker load status from the tickers table
Each entry in `GET /tickers`'s response SHALL include that ticker's
`loaded`, `features_computed`, and `last_loaded_at` status, derived from
the `tickers` table, so a client can distinguish a universe ticker that
has never been loaded from one that has.

#### Scenario: Ticker with no tickers row
- **WHEN** a ticker in the universe has no corresponding row in the
  `tickers` table (never loaded)
- **THEN** its entry in the response indicates not-loaded (e.g.
  `loaded: false`) and `features_computed` and `last_loaded_at` are null
  rather than the request failing

#### Scenario: Ticker with a tickers row
- **WHEN** a ticker in the universe has a corresponding row in the
  `tickers` table
- **THEN** its entry reflects that row's `features_computed` and
  `last_loaded_at` values

### Requirement: Read-only, no side effects
`GET /tickers` SHALL NOT call `load_ticker`, trigger any `vnstock`
request, or write to any table. It only reads the universe, the
`TRAINING_TICKERS` constant, and the existing `tickers` table.

#### Scenario: Request does not trigger ingestion
- **WHEN** a client requests `GET /tickers`
- **THEN** no external `vnstock` call is made and no row in `ohlcv`,
  `tickers`, `features`, or the universe table is written as a result of
  this request

#### Scenario: Large universe does not trigger fetches
- **WHEN** a client requests `GET /tickers` while the universe contains
  hundreds of symbols, many of them never loaded
- **THEN** the response is served entirely from stored state, with no
  external call made for the unloaded symbols

## ADDED Requirements

### Requirement: Catalog entries carry universe metadata
Each entry in `GET /tickers`'s response SHALL include the ticker's
exchange, industry classification, and listing status from the universe,
so a client can group or filter without a second request.

#### Scenario: Metadata present on each entry
- **WHEN** a client requests `GET /tickers`
- **THEN** each entry includes exchange, industry classification, and
  listing status, with null used where the universe has no value rather
  than the field being omitted

#### Scenario: Delisted tickers are distinguishable
- **WHEN** the universe contains delisted symbols and a client requests
  `GET /tickers`
- **THEN** those entries are marked as delisted, so a client can exclude
  them from a tradeable list without inferring it from date ranges
