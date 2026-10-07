## RENAMED Requirements

- FROM: `### Requirement: Serve the fixed set of model-validated tickers`
- TO: `### Requirement: Serve the universe-derived catalog with a legacy training-set marker`

## MODIFIED Requirements

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
