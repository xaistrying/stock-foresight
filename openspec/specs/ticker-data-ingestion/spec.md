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
  (no retry, backoff, or queuing logic in this change) and the request
  fails without crashing the process

### Requirement: OHLCV and tickers schema
The system SHALL persist ingested data in a SQLite `ohlcv` table
(`ticker`, `date`, `open`, `high`, `low`, `close`, `volume`, primary key
`(ticker, date)`) and a `tickers` table (`ticker` primary key,
`available_since`, `possibly_truncated_by_tier`, `last_loaded_at`).

#### Scenario: Row shape matches schema
- **WHEN** a row is written to `ohlcv` for a given ticker and date
- **THEN** the row has non-null `open`, `high`, `low`, `close` (REAL) and
  `volume` (INTEGER), keyed uniquely by `(ticker, date)`

#### Scenario: Date stored without time-of-day
- **WHEN** vnstock returns a timestamp with the 07:00:00 time-of-day quirk
- **THEN** the system strips the time component and stores `date` as a
  date-only ISO TEXT value

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
