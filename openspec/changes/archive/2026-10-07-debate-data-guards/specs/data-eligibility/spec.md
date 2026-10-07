## ADDED Requirements

### Requirement: assess_eligibility reports whether a loaded ticker's data can support a debate or range
The backend SHALL provide `assess_eligibility(ticker, now=None)` returning `{ eligible: bool, reasons: list[str], as_of: str | null, age_sessions: int | null }`. `as_of` is the date of the ticker's latest `features` row; when the ticker has no `features` row, `as_of` and `age_sessions` are `null` and `reasons` is `["insufficient_history"]`. `reasons` SHALL list every reason that applies, in the fixed order `delisted`, `insufficient_history`, `stale`, `near_gap`, `hard_quality_flag`, `indicators_missing`, and `eligible` SHALL be true exactly when `reasons` is empty. The service SHALL read the database itself and MUST NOT depend on the prediction API module. The optional `now` is a timezone-aware clock for tests.

#### Scenario: Healthy current ticker
- **WHEN** a listed ticker has at least 65 priced sessions, all four indicators on its latest row, no hard flag in its last 78 sessions, at most 2 missing market sessions in its last 65, and its newest session is within 3 sessions of the previous weekday
- **THEN** `eligible` is true, `reasons` is empty, `as_of` is its latest features date and `age_sessions` is an integer

#### Scenario: Several reasons at once
- **WHEN** a ticker is delisted and its data is 21 sessions old
- **THEN** `reasons` contains `delisted` and `stale`, in that order, and `eligible` is false

#### Scenario: No features row
- **WHEN** the ticker has no `features` row
- **THEN** `eligible` is false, `reasons` is `["insufficient_history"]`, and `as_of` and `age_sessions` are `null`

### Requirement: Delisted and short-history tickers are ineligible
A ticker is `delisted` when `ticker_universe.listing_status` is `delisted`; a ticker with no universe row SHALL NOT be flagged for this reason. A ticker is `insufficient_history` when it has fewer than `MIN_SESSIONS` priced (`close > 0`) `ohlcv` rows, where `MIN_SESSIONS` is the constant defined for the volatility model (65).

#### Scenario: Delisted ticker
- **WHEN** `listing_status` is `delisted`
- **THEN** `reasons` contains `delisted`

#### Scenario: Ticker missing from the universe table
- **WHEN** no `ticker_universe` row exists for the ticker
- **THEN** `delisted` is not reported

#### Scenario: Short history
- **WHEN** the ticker has 64 priced sessions
- **THEN** `reasons` contains `insufficient_history`; with 65 it does not

#### Scenario: Zero closes are not priced sessions
- **WHEN** a ticker has 70 stored rows of which 10 have `close = 0`
- **THEN** it has 60 priced sessions and `insufficient_history` is reported

### Requirement: Data age is counted in sessions without a market calendar
`age_sessions` SHALL equal the number of distinct session dates stored in `ohlcv` for any ticker that fall after the ticker's `as_of`, plus the number of weekdays after the newest stored session date up to and including the previous weekday in Vietnam time (UTC+7), counting zero when there are none. Today's session SHALL NOT be expected. A ticker is `stale` when `age_sessions` exceeds `MAX_AGE_SESSIONS` (3). A weekday on which no ticker has a row, on or before the newest stored session, SHALL NOT be counted (a market holiday).

#### Scenario: Up to date after a weekend
- **WHEN** a ticker's `as_of` is Friday, no later session is stored for any ticker, and the clock reads Monday 10:00 Vietnam time
- **THEN** `age_sessions` is 0 and `stale` is not reported

#### Scenario: Behind by stored sessions
- **WHEN** a ticker's `as_of` is 2026-09-07 and other tickers hold 21 distinct session dates after it
- **THEN** `age_sessions` is at least 21 and `stale` is reported

#### Scenario: Holiday inside the stored range is not counted
- **WHEN** a ticker's `as_of` is the Friday before a Monday-Tuesday market closure, other tickers hold rows for the following Wednesday, and the clock reads that Wednesday evening
- **THEN** `age_sessions` is 1 (the Wednesday), not 3

#### Scenario: A stale database is not read as fresh
- **WHEN** no ticker has been refreshed for 15 weekdays and the clock reads today
- **THEN** every ticker's `age_sessions` is at least 14 and `stale` is reported; the age is not measured against the newest stored session alone

#### Scenario: Long closure with nothing stored beyond it (known limitation)
- **WHEN** the market is closed for 5 weekdays, no ticker has a stored session after the closure began, and the clock reads the 5th weekday of the closure (the 4th weekday expects only the first 3 sessions, so `age_sessions` is 3 and `stale` is not reported)
- **THEN** `age_sessions` is 4 and `stale` is reported until a refresh stores the first session after the closure

#### Scenario: Boundary
- **WHEN** `age_sessions` is 3
- **THEN** `stale` is not reported; at 4 it is

### Requirement: Missing market sessions and hard quality flags make a ticker ineligible
A ticker is `near_gap` when more than `MAX_MISSING_SESSIONS` (2) market sessions are absent from its own priced series within the span of its last 65 priced sessions, where a market session is a date on which at least one stored ticker has a row. The stored `features.near_gap` column SHALL NOT be used for this reason: it counts any gap above 5 calendar days, including market holidays. A ticker is `hard_quality_flag` when `ohlcv_quality_flags` holds a row with `flag_tier = 'hard'` dated within the ticker's last 78 priced sessions (the indicator blackout length).

#### Scenario: Holiday gap is not a gap
- **WHEN** a ticker's last 65 sessions straddle a 6-calendar-day market closure and no other session is missing
- **THEN** `near_gap` is not reported

#### Scenario: Thinly traded ticker with omitted sessions
- **WHEN** 6 market sessions are absent from a ticker's last 65
- **THEN** `near_gap` is reported

#### Scenario: Tolerated omission
- **WHEN** exactly 2 market sessions are absent
- **THEN** `near_gap` is not reported; at 3 it is

#### Scenario: Hard flag inside the window
- **WHEN** a hard-tier flag (either `price_limit` or `invalid_close`) is dated within the last 78 priced sessions
- **THEN** `hard_quality_flag` is reported

#### Scenario: Hard flag outside the window
- **WHEN** the only hard flag is older than the last 78 priced sessions
- **THEN** `hard_quality_flag` is not reported

#### Scenario: Soft flags do not count
- **WHEN** the only flags in the window have `flag_tier = 'soft'`
- **THEN** `hard_quality_flag` is not reported

### Requirement: All four technical indicators must be present on the as_of row
The service SHALL report `indicators_missing` when any of `rsi`, `macd_histogram`, `tenkan_sen` or `kijun_sen` is null on its `as_of` features row.

#### Scenario: One indicator null
- **WHEN** `macd_histogram` is null on the latest row
- **THEN** `indicators_missing` is reported

#### Scenario: Indicators the agent does not read
- **WHEN** only `senkou_span_b` is null
- **THEN** `indicators_missing` is not reported
