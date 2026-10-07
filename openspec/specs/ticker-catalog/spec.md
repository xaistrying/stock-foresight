# ticker-catalog

## Purpose

TBD

## Requirements

### Requirement: Serve the universe-derived catalog with a legacy training-set marker
The system SHALL expose `GET /tickers`, which returns the tickers in the
ingested universe (`ticker-universe`) that pass the universe's default
filters, and SHALL NOT maintain any second, independently-edited list of
tickers anywhere in the codebase. Each entry SHALL carry the boolean
`in_training_set`, true exactly for the members of `TRAINING_TICKERS`
(`backend/app/ml/training.py`): the nine tickers the retired XGBoost
direction model was trained and backtested on. The field is a legacy marker
kept so the API shape does not change; it SHALL NOT be read as a claim that
any served output is validated on those tickers, and no served model depends
on the set.

Every `TRAINING_TICKERS` member SHALL appear in the response, first and in
their declared order, whether or not it passes those filters, and whether or
not the universe holds a row for it; the remaining entries follow
alphabetically. Their universe-sourced fields are null when the universe has
no row.

#### Scenario: A training ticker excluded by a filter is still served
- **WHEN** a `TRAINING_TICKERS` member is flagged as failing the liquidity
  or minimum-history filter
- **THEN** it still appears in `GET /tickers`, marked `in_training_set`

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
- **THEN** the marking and the ordering in `GET /tickers`'s response change
  accordingly without any other file needing to be edited to keep the two
  in sync

#### Scenario: Universe change requires no second edit
- **WHEN** the ingested universe changes
- **THEN** `GET /tickers`'s response set changes accordingly without any
  hand-maintained ticker list needing to be edited

#### Scenario: The catalog does not depend on a model artifact
- **WHEN** `GET /tickers` is requested on an installation with no file under
  `backend/data/models/`
- **THEN** the system responds `200` with the same entries it would serve
  with a model file present

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

### Requirement: Catalog entries carry an eligibility summary computed in one pass
Each entry in `GET /tickers`'s response SHALL include `eligibility`, an object `{eligible, reasons, as_of, age_sessions}` equal, field for field and in the same fixed reason order, to what `assess_eligibility(ticker)` (`data-eligibility`) returns for that ticker at the time of the request, so a client can say why a ticker cannot be analysed without one request per ticker. `eligibility` SHALL be null for an entry that is not loaded (no `tickers` row), and SHALL be present, never omitted. The entries of one response SHALL be computed in a single batched pass: the distinct stored session dates SHALL be read once for the whole response, not once per ticker. `assess_eligibility` SHALL be a single-ticker call of the same batched code, so the two cannot differ. The field is additive: no existing field of an entry changes.

#### Scenario: Summary equals the single-ticker assessment
- **WHEN** `GET /tickers` is requested and, for every loaded entry, `assess_eligibility(entry.ticker, now)` is evaluated with the same clock
- **THEN** each entry's `eligibility` equals that result, including the order of `reasons`

#### Scenario: Several reasons keep their fixed order
- **WHEN** a catalog ticker is delisted and its data is 21 sessions old
- **THEN** its `eligibility.reasons` is `["delisted", "stale"]`, `eligible` is false and `age_sessions` is 21

#### Scenario: Not-loaded ticker has a null summary
- **WHEN** a catalog entry has `loaded: false`
- **THEN** its `eligibility` is null and the response is still `200`

#### Scenario: Ticker with no features row
- **WHEN** a loaded ticker has no `features` row
- **THEN** its `eligibility` is `{eligible: false, reasons: ["insufficient_history"], as_of: null, age_sessions: null}`

#### Scenario: One scan of session dates for the whole catalog
- **WHEN** `GET /tickers` is requested for a catalog of 208 loaded tickers and the database statements issued are counted
- **THEN** the distinct-session-dates read is issued exactly once, and no statement is issued once per ticker for it

#### Scenario: Still read-only
- **WHEN** `GET /tickers` is requested
- **THEN** no `vnstock` call is made and no table is written, as before
