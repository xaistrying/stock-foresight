## MODIFIED Requirements

### Requirement: OHLCV and tickers schema
The system SHALL persist ingested data in a SQLite `ohlcv` table
(`ticker`, `date`, `open`, `high`, `low`, `close`, `volume`, primary key
`(ticker, date)`) and a `tickers` table (`ticker` primary key,
`available_since`, `possibly_truncated_by_tier`, `last_loaded_at`,
`features_computed`). `features_computed` is `1` when the most recent load's
feature recomputation succeeded, `0` when it was attempted and failed, and
`NULL` when its outcome cannot be determined — either because no load has
ever been attempted for the ticker, or because the ticker's only load
attempt(s) predate this column's addition (backfilled to `NULL` by the
`ALTER TABLE` migration, with outcome unknown for those rows).

#### Scenario: Row shape matches schema
- **WHEN** a row is written to `ohlcv` for a given ticker and date
- **THEN** the row has non-null `open`, `high`, `low`, `close` (REAL) and
  `volume` (INTEGER), keyed uniquely by `(ticker, date)`

#### Scenario: Date stored without time-of-day
- **WHEN** vnstock returns a timestamp with the 07:00:00 time-of-day quirk
- **THEN** the system strips the time component and stores `date` as a
  date-only ISO TEXT value

#### Scenario: features_computed persisted on every load
- **WHEN** `load_ticker` completes (first load or reload), regardless of
  whether `recompute_features_for_ticker` succeeded or raised
- **THEN** the ticker's `tickers` row has `features_computed` set to `1` on
  success or `0` on failure — never left at its prior value or unset after a
  load has been attempted

#### Scenario: features_computed distinguishes a known failure from unknown provenance
- **WHEN** a ticker's only load attempt(s) predate this column's addition
  (backfilled by the `ALTER TABLE` migration)
- **THEN** `features_computed` is `NULL` for that ticker's row — distinct
  from `0` (a load under the current schema was attempted and failed) and
  distinct from having no `tickers` row at all (never loaded — a separate
  case with no row to query, handled before this column is ever read)
