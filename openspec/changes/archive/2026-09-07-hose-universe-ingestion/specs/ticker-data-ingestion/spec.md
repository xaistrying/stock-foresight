## ADDED Requirements

### Requirement: Quality gate applied before persistence
`load_ticker` SHALL apply the `ohlcv-quality-gate` checks to fetched rows
as part of the load, so quality state is recorded at ingestion time rather
than reconstructed by a later pass.

#### Scenario: Load records quality state
- **WHEN** `load_ticker` completes successfully for any ticker
- **THEN** that ticker's price-limit flags and stale-close fraction have
  been computed and persisted as part of the same operation

#### Scenario: Quality failure does not discard the fetch
- **WHEN** a fetched ticker contains rows failing the price-limit check
- **THEN** the rows are still persisted with their flags, rather than the
  whole load being rejected, so the data remains inspectable

### Requirement: Ingestion is drivable in batch
`load_ticker` SHALL be invocable programmatically for many tickers in
sequence without requiring an HTTP request, so `bulk-ticker-ingestion` can
reuse it rather than duplicating fetch and persistence logic.

#### Scenario: Batch reuses the single-ticker path
- **WHEN** a full-universe ingestion runs
- **THEN** it drives the same `load_ticker` fetch and persistence logic
  used by `POST /tickers/{ticker}/load`, with no second implementation of
  the fetch

#### Scenario: Delisted symbol loads through the same path
- **WHEN** `load_ticker` is called for a delisted symbol whose history is
  still retrievable
- **THEN** it fetches and persists that history through the normal path,
  and the absence of recent sessions is not treated as an error

### Requirement: Feature recomputation cost is bounded at scale
The system SHALL NOT require a full from-earliest-row feature
recomputation of every ticker on every batch ingestion run. Where full
recomputation is required for correctness of a specific column, that
requirement SHALL be satisfied without forcing the whole universe through
it on every run.

#### Scenario: Batch run does not recompute the entire universe
- **WHEN** a batch ingestion run adds or updates a subset of tickers
- **THEN** feature recomputation is performed for the affected tickers,
  not for every ticker in the universe

#### Scenario: Correctness of cumulative columns is preserved
- **WHEN** feature recomputation runs for a ticker under the bounded
  scheme
- **THEN** any column whose definition depends on the ticker's full
  history from its earliest stored row produces the same values it would
  have under unconditional full recomputation
