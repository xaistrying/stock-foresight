# bulk-ticker-ingestion

## Purpose

Defines batch ingestion of the full ticker universe outside the HTTP
request lifecycle: rate-limit handling, resumability, and per-run
summaries.

## Requirements

### Requirement: Batch ingestion outside the request lifecycle
The system SHALL provide an entry point that ingests the full universe
without being driven by an HTTP request, because ingesting hundreds of
symbols under rate limiting far exceeds any reasonable request timeout.

#### Scenario: Batch run is invocable independently
- **WHEN** an operator starts a full-universe ingestion
- **THEN** it runs to completion without an HTTP request being held open,
  and without requiring the API server to be running

#### Scenario: Existing per-ticker endpoint is unchanged
- **WHEN** `POST /tickers/{ticker}/load` is called for a single ticker
- **THEN** it behaves as it does today, and is not replaced by the batch
  path

### Requirement: Rate-limit aware and resumable
The system SHALL handle the data source's rate limiting during a batch run
and SHALL be resumable, so an interrupted run does not require re-fetching
everything already ingested.

#### Scenario: Rate limit pauses rather than aborts the run
- **WHEN** the data source signals a rate limit mid-run
- **THEN** the run waits and continues rather than terminating the whole
  batch

#### Scenario: Resumed run skips completed symbols
- **WHEN** a batch run is restarted after an interruption
- **THEN** symbols already successfully ingested in the prior run are not
  re-fetched by default

#### Scenario: Per-symbol failure does not abort the batch
- **WHEN** one symbol fails to ingest for any reason
- **THEN** the failure is recorded against that symbol and the run
  continues with the remaining symbols

### Requirement: Run produces an inspectable summary
The system SHALL record, per batch run, which symbols succeeded, which
failed and why, and which were excluded by the quality gate.

#### Scenario: Summary distinguishes failure from exclusion
- **WHEN** a batch run completes
- **THEN** its summary separates symbols that failed to fetch from symbols
  that fetched successfully but failed the liquidity or minimum-history
  filters

#### Scenario: Summary is durable
- **WHEN** a batch run completes
- **THEN** its summary persists beyond the process that produced it
