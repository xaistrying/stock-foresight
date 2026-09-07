## ADDED Requirements

### Requirement: Universe derived from the exchange listing
The system SHALL construct its ticker universe from
`Listing().symbols_by_exchange()`, retaining only rows whose `type` is
`STOCK`, and SHALL NOT treat covered warrants, ETFs, bonds, futures, or
unit trusts as tickers.

#### Scenario: Non-stock instrument types are excluded
- **WHEN** the universe is constructed from a listing response containing
  rows of type `CW`, `ETF`, `BOND`, `FU`, `UNIT_TRUST`, and `DEBENTURE`
- **THEN** none of those rows appear in the universe, and only `STOCK`
  rows are retained

#### Scenario: HOSE stock count is plausible
- **WHEN** the universe is constructed with the exchange filter set to
  HOSE
- **THEN** the resulting count is on the order of several hundred symbols,
  and a count of zero or a count exceeding the listing's total `STOCK`
  rows SHALL be treated as a construction failure rather than persisted

### Requirement: Delisted symbols are part of the universe
The system SHALL include symbols whose listing status is delisted, so that
a universe reconstructed as of a past date contains companies that existed
then but do not exist now.

#### Scenario: Delisted symbol is ingested with its history
- **WHEN** the universe includes a delisted symbol for which the data
  source returns OHLCV history
- **THEN** that symbol's rows are persisted like any other ticker's, and
  its universe entry records that it is delisted

#### Scenario: Point-in-time universe excludes symbols not yet listed
- **WHEN** the universe is reconstructed as of a date `D`
- **THEN** it contains exactly the symbols whose observed session range
  includes or precedes `D`, and excludes symbols whose first observed
  session is after `D`

#### Scenario: Point-in-time universe includes symbols later delisted
- **WHEN** the universe is reconstructed as of a date `D` and a symbol was
  trading at `D` but delisted afterwards
- **THEN** that symbol is present in the reconstructed universe

### Requirement: Exchange membership never silently claims to be dated
Symbols migrate between exchanges, so a recorded exchange is a claim about
a point in time. The system SHALL therefore mark every exchange it records
as either verified dated membership or an unverified current-state
fallback, and SHALL NOT present the latter as the former.

Dated membership is not obtainable from the listing API, which returns
current state only and gives delisted rows no exchange field at all
(design Decisions 2 and 3). Every membership this change records is
consequently a fallback, marked as one via
`ticker_universe.exchange_is_unverified_fallback`, and the hard gate is
built to need no exchange at all so that the one tier which actually
excludes data does not rest on an unverifiable claim.

An earlier draft of this requirement asked instead that `ACB` resolve to
HNX for dates before its HOSE listing. That scenario can never pass
against the available data, and keeping it would have left the spec
describing a system nobody can build from this API.

#### Scenario: Recorded exchange is marked as an unverified fallback
- **WHEN** a symbol's exchange is taken from the current listing and used
  to evaluate a date that may predate its listing there
- **THEN** the recorded membership is marked as an unverified fallback, and
  any flag derived from it carries that marking

#### Scenario: The excluding tier does not depend on membership
- **WHEN** the hard gate evaluates a row for a symbol whose historical
  exchange is unknown, including a delisted symbol with no exchange at all
- **THEN** the evaluation still happens, because it uses the widest limit
  any Vietnamese exchange allows and so needs no membership claim

#### Scenario: Current-state fallback is explicit
- **WHEN** no dated membership information is available for a symbol and
  date
- **THEN** the system records that the membership is an unverified
  fallback rather than silently asserting the current exchange as
  historical fact

### Requirement: Industry classification is persisted
The system SHALL persist each symbol's `icb_code2` industry classification
from the listing, so sector grouping is available without a second
network call.

#### Scenario: Industry code stored with the universe entry
- **WHEN** a symbol is added to the universe from a listing row carrying
  `icb_code2`
- **THEN** that code is persisted with the universe entry

#### Scenario: Missing industry code does not block ingestion
- **WHEN** a listing row has no `icb_code2` value
- **THEN** the symbol is still added to the universe with a null industry
  code, and ingestion proceeds

### Requirement: Observed session range is recorded per symbol
The system SHALL record the first and last observed session date for each
symbol from its ingested OHLCV, so universe reconstruction and
minimum-history filtering do not require scanning `ohlcv`.

#### Scenario: Range recorded after ingestion
- **WHEN** a symbol's OHLCV rows are persisted
- **THEN** its universe entry's first and last observed session dates are
  updated to match the persisted rows

#### Scenario: Symbol with too little history is flagged
- **WHEN** a symbol's observed session count falls below the configured
  minimum-history threshold
- **THEN** its universe entry is flagged as below-minimum-history rather
  than being deleted, so the exclusion is visible and reversible
