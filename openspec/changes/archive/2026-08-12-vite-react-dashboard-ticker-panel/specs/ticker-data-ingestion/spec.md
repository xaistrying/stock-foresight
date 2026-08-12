## MODIFIED Requirements

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
