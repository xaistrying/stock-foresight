## ADDED Requirements

### Requirement: Serve a bounded trailing OHLCV window
The system SHALL expose `GET /tickers/{ticker}/history`, which returns
the most recent 750 sessions of OHLCV data for the ticker from the
`ohlcv` table, ordered oldest to newest. The window size (750) SHALL be a
fixed backend constant, not a client-supplied parameter, in this version.
(Widened from an original 300-session window post-ship — see design.md
Decision 2.)

#### Scenario: Ticker with more than 750 stored sessions
- **WHEN** a client requests `GET /tickers/{ticker}/history` for a ticker
  with more than 750 rows in `ohlcv`
- **THEN** the system responds `200` with exactly the 750
  chronologically most recent rows, ordered oldest to newest

#### Scenario: Ticker with fewer than 750 stored sessions
- **WHEN** a client requests `GET /tickers/{ticker}/history` for a ticker
  with fewer than 750 rows in `ohlcv`
- **THEN** the system responds `200` with all available rows for that
  ticker, ordered oldest to newest, without treating the shortfall as an
  error

### Requirement: Response is pure OHLCV, no indicators, no near_gap
Each row in the response SHALL contain only `date`, `open`, `high`,
`low`, `close`, and `volume`. The system SHALL NOT include any indicator
column (`tenkan_sen`, `rsi`, `macd_line`, etc.) or the `near_gap` flag
from the `features` table in this endpoint's response.

#### Scenario: Row shape excludes indicators and near_gap
- **WHEN** the system responds to `GET /tickers/{ticker}/history`
- **THEN** no row in the response body contains an indicator column or a
  `near_gap` field, regardless of whether the corresponding `features`
  row exists or has `near_gap = 1`

### Requirement: Never-loaded ticker returns 404
The system SHALL respond `404` when the ticker has no rows in `ohlcv`,
and SHALL NOT trigger `load_ticker` or any `vnstock` request as a side
effect of this endpoint.

#### Scenario: Ticker with zero ohlcv rows
- **WHEN** a client requests `GET /tickers/{ticker}/history` for a
  ticker with no rows in `ohlcv`
- **THEN** the system responds `404` and does not call `load_ticker` or
  make any external `vnstock` request

### Requirement: Endpoint is not restricted to the fixed ticker set
`GET /tickers/{ticker}/history` SHALL serve history for any ticker with
data in `ohlcv`, not only tickers in `TRAINING_TICKERS`. Restricting
which tickers are chartable is a frontend/`ticker-catalog` concern, not
a constraint this endpoint enforces itself.

#### Scenario: History served for a loaded ticker outside the training set
- **WHEN** a client requests `GET /tickers/{ticker}/history` for a ticker
  that has been loaded via `POST /tickers/{ticker}/load` but is not in
  `TRAINING_TICKERS`
- **THEN** the system responds `200` with that ticker's OHLCV history,
  identically to a request for a ticker in `TRAINING_TICKERS`
