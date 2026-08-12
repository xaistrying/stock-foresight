# ticker-data-ingestion

## Purpose

TBD

## Requirements

### Requirement: On-demand ticker load endpoint
The system SHALL expose `POST /tickers/{ticker}/load`, which triggers
`load_ticker(ticker)` and works identically whether the ticker has never
been loaded before or is being reloaded.

#### Scenario: First load of a new ticker
- **WHEN** `POST /tickers/{ticker}/load` is called for a ticker with no
  existing rows in `ohlcv` or `tickers`
- **THEN** the system fetches OHLCV history, writes rows to `ohlcv`, and
  writes a new row to `tickers`

#### Scenario: Reload of an already-loaded ticker
- **WHEN** `POST /tickers/{ticker}/load` is called for a ticker that
  already has rows in `ohlcv` and a row in `tickers`
- **THEN** the system re-fetches OHLCV history and upserts both `ohlcv` and
  `tickers` without creating duplicate rows or requiring a separate
  refresh endpoint

### Requirement: Single-call OHLCV fetch
The system SHALL fetch a ticker's OHLCV history via exactly one call to
`mkt.equity(ticker).ohlcv(start="2000-01-01", end=today, count=5000,
source="vci")` per load request, with no chunking or walk-back beyond
this single call.

#### Scenario: Fetch parameters are always explicit
- **WHEN** the system calls the vnstock OHLCV API for any ticker
- **THEN** `count` is explicitly passed as 5000 (never omitted), `start` is
  the fixed constant `"2000-01-01"`, `end` is the current date, and
  `source` is `"vci"`

#### Scenario: Community tier caps returned history
- **WHEN** a ticker's true listing date is more than ~8 years before `end`
- **THEN** the fetch returns only the most recent ~8 years of sessions
  (`max(end - 8y, real_start)`), and the system does not attempt any
  further call to retrieve earlier history

#### Scenario: Rate limit is caught, not handled
- **WHEN** the vnstock fetch raises `RateLimitError`
- **THEN** the system catches the exception via try/except as scaffolding
  (no retry, backoff, or queuing logic in this change), returns a
  response with `status: "rate_limited"`, and the request fails without
  crashing the process

#### Scenario: Malformed symbol raises ValueError, caught and classified
- **WHEN** the vnstock fetch raises `ValueError` with a message matching
  the project's known symbol-validation errors (e.g. "Invalid symbol.
  Your symbol format is not recognized!" or "Symbol must be between 3
  and 12 characters long.")
- **THEN** the system catches it, returns a response with
  `status: "invalid_symbol"`, and does not write any row to `ohlcv`

#### Scenario: Unrecognized ValueError is not misclassified
- **WHEN** the vnstock fetch raises a `ValueError` whose message does
  not match any known symbol-validation or no-data error
- **THEN** the system re-raises it rather than returning a classified
  `status` for an unrelated failure

#### Scenario: Well-formed ticker with no real data raises RetryError, unwrapped and classified
- **WHEN** the vnstock fetch raises `tenacity.RetryError` wrapping a
  "no data found" `ValueError` (`e.last_attempt.exception()`) for a
  well-formed but nonexistent/delisted ticker
- **THEN** the system unwraps the `RetryError` via
  `e.last_attempt.exception()`, classifies the underlying `ValueError`
  the same way as any directly-raised `ValueError`, returns
  `status: "no_data"`, and does not write any row to `ohlcv`

#### Scenario: Malformed-symbol ValueError is not wrapped in RetryError
- **WHEN** the vnstock fetch raises a `ValueError` for a malformed
  symbol (format/length rejected before any retried network call)
- **THEN** the exception is a plain `ValueError`, not a `RetryError`,
  and the system classifies it directly without an unwrap step

### Requirement: Load response reports an explicit outcome status
The `POST /tickers/{ticker}/load` response SHALL include a `status`
field with exactly one of four values: `"ok"` (rows were fetched and
written), `"rate_limited"` (the vnstock fetch was rate-limited),
`"invalid_symbol"` (the vnstock fetch rejected the symbol's format), or
`"no_data"` (the symbol is well-formed but corresponds to no real data).
A client SHALL be able to determine which of these four outcomes
occurred from this field alone, without inferring it from which other
fields are null.

#### Scenario: Successful load reports status ok
- **WHEN** `POST /tickers/{ticker}/load` fetches at least one row and
  writes it to `ohlcv`
- **THEN** the response has `status: "ok"`

#### Scenario: Rate-limited load reports status rate_limited
- **WHEN** the vnstock fetch for a load request raises `RateLimitError`
- **THEN** the response has `status: "rate_limited"`, and
  `rows_loaded: 0`

#### Scenario: Malformed-symbol load reports status invalid_symbol
- **WHEN** the vnstock fetch for a load request raises a `ValueError`
  matching a known symbol-validation message
- **THEN** the response has `status: "invalid_symbol"`, and
  `rows_loaded: 0`

#### Scenario: Well-formed-but-empty load reports status no_data
- **WHEN** the vnstock fetch for a load request raises (directly, or
  via `RetryError`) a `ValueError` matching the known no-data message
- **THEN** the response has `status: "no_data"`, and `rows_loaded: 0`

#### Scenario: All four statuses are distinguishable from each other
- **WHEN** a client receives a `POST /tickers/{ticker}/load` response
  with `rows_loaded: 0`
- **THEN** the `status` field alone tells the client which of
  `rate_limited` (retry later may help), `invalid_symbol` (the ticker
  string itself is malformed), or `no_data` (a well-formed symbol with
  no real data — retrying is unlikely to help) occurred, without
  inspecting `available_since` or any other field

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

### Requirement: Upsert semantics on every load
The system SHALL upsert into both `ohlcv` and `tickers` on every call to
`load_ticker`, using `ON CONFLICT(ticker, date) DO UPDATE` for `ohlcv` and
an equivalent upsert for `tickers`, on both first load and every reload.

#### Scenario: Reload corrects a previously stored row
- **WHEN** a reload fetches a row for a `(ticker, date)` that already
  exists in `ohlcv` with different values
- **THEN** the existing row is updated in place (`DO UPDATE`), not
  duplicated

#### Scenario: Tickers row is refreshed every load
- **WHEN** `load_ticker` completes successfully, first load or reload
- **THEN** the `tickers` row for that ticker has `last_loaded_at` set to
  the current load time, and `available_since` /
  `possibly_truncated_by_tier` recomputed from the just-fetched data

### Requirement: Gap detection is advisory, not blocking
The system SHALL check for gaps greater than 5 calendar days between
consecutive stored sessions for a ticker and log them, without failing the
ingestion.

#### Scenario: Gap larger than 5 days is logged
- **WHEN** two consecutive stored sessions for a ticker are more than 5
  calendar days apart
- **THEN** the system logs the gap as a likely fetch-issue signal and
  continues; the load request still succeeds

#### Scenario: Gap does not block ingestion
- **WHEN** a gap is detected during a load
- **THEN** all successfully fetched rows are still written to `ohlcv`, and
  the endpoint does not return an error solely because of the gap

### Requirement: Tier-truncation labeling
The system SHALL derive `tickers.available_since` as the minimum `date`
from the just-completed load, and `tickers.possibly_truncated_by_tier` as
`1` when `abs(available_since - (end - 8y)) <= 30 days`, else `0`. This
label SHALL NOT gate, block, or filter any write to `ohlcv`.

#### Scenario: Truncation flag set near the tier boundary
- **WHEN** a ticker's `available_since` from the load falls within 30 days
  of `end` minus 8 years
- **THEN** `tickers.possibly_truncated_by_tier` is set to `1` for that
  ticker

#### Scenario: Truncation flag does not affect ohlcv writes
- **WHEN** `possibly_truncated_by_tier` evaluates to `1` for a ticker
- **THEN** every row fetched for that ticker is still written to `ohlcv`
  exactly as it would be if the flag were `0`

### Requirement: Data dictionary documentation
The system SHALL document the `ohlcv`/`tickers` schema, the 07:00:00
time-of-day quirk, the `available_since` ambiguity, the
`possibly_truncated_by_tier` calibration caveat, and the
count-truncates-from-end fetch behavior in `docs/DATA_DICTIONARY.md`.

#### Scenario: Data dictionary exists after this change
- **WHEN** this change is implemented
- **THEN** `docs/DATA_DICTIONARY.md` exists and describes both table
  schemas and the quirks/ambiguities listed above
