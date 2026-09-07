## ADDED Requirements

### Requirement: Price-limit violation detection
The system SHALL evaluate each fetched OHLCV row's session-over-session
close change against the daily price limit of the exchange the symbol
traded on at that date, and SHALL flag rows whose change exceeds that
limit. The limits are HOSE ±7%, HNX ±10%, and UPCOM ±15%.

#### Scenario: Violation is flagged, not silently accepted
- **WHEN** a symbol on HOSE has a session-over-session close change
  exceeding ±7% beyond the configured tolerance
- **THEN** that row is flagged as a price-limit violation

#### Scenario: Limit is resolved against the historical exchange
- **WHEN** a row belongs to a date on which the symbol traded on HNX,
  and the symbol currently trades on HOSE
- **THEN** the row is evaluated against HNX's ±10% limit, not HOSE's ±7%

#### Scenario: Legitimate pre-migration moves are not flagged
- **WHEN** `ACB`, `VIB`, or `VND` rows from before their HOSE listing show
  changes within their then-exchange's wider limit
- **THEN** those rows are not flagged as violations

#### Scenario: A genuine bad row is flagged
- **WHEN** the `VHM` session dated 2018-08-14, a single-session close step
  from 60.30 to 30.23 (a −0.69 log return), is evaluated
- **THEN** it is flagged as a price-limit violation

### Requirement: A close that is not a price is flagged, not skipped
The system SHALL flag any row whose close is not a positive finite number
as hard, independently of the computed return, and SHALL record the reason
separately from a price-limit breach.

A zero close makes the returns either side of it infinite rather than
merely large, so a gate that tests the return for finiteness before
comparing it against a limit skips exactly the most corrupt row shape in
the data. `VKP` carries one such close, found by the first batch dry run.

#### Scenario: Zero close is hard-flagged
- **WHEN** a stored session's close is `0.0`
- **THEN** that row is hard-flagged with a reason distinguishing it from a
  price-limit breach, rather than being passed over because its return is
  not finite

#### Scenario: Reasons are recorded separately
- **WHEN** flags are counted for a run
- **THEN** price-limit breaches, invalid closes, and post-halt resumptions
  are countable apart from one another, because they call for different
  responses and conflating them would skew the trigger for reconsidering
  detect-and-repair

### Requirement: A price limit is not applied across a trading halt
The system SHALL NOT treat a move across a gap longer than 30 calendar
days as a price-limit breach, because the daily limit applies
session-over-session against a reference price that a long halt resets.
Such a move SHALL be recorded for review rather than excluded.

Ordinary market closures are unaffected: the limit remains fully in force
across a weekend or Tet's ~10 days, so the first session back is still
limited against the last close before it.

#### Scenario: Resumption after a long halt is recorded, not excluded
- **WHEN** a symbol resumes trading after more than 30 calendar days and
  its first session back moves beyond the widest limit
- **THEN** the row is soft-flagged as a resumption, so neither the return
  nor the following 78 sessions of indicators are discarded

#### Scenario: A holiday keeps the limit in force
- **WHEN** two consecutive stored sessions straddle a ~10-day holiday and
  the close halves across them
- **THEN** the row is hard-flagged as a price-limit breach exactly as it
  would be on consecutive days

### Requirement: Flagged rows are excluded from modelling inputs
The system SHALL ensure rows flagged as price-limit violations do not
silently enter volatility or feature computation, because a single
spurious extreme return distorts every window containing it.

#### Scenario: Flagged row does not corrupt downstream computation
- **WHEN** feature or volatility computation runs over a ticker
  containing a flagged row
- **THEN** the flagged row's return is excluded or neutralised rather than
  contributing its raw value

#### Scenario: Indicator columns spanning a flagged session are nulled
- **WHEN** an indicator whose lookback window spans a hard-flagged session
  is computed for a session following that flag
- **THEN** that indicator value is null for the length of the longest
  indicator lookback after the flagged session, because a hard-flagged step
  is a persistent level shift and any window spanning it blends two
  different price scales

#### Scenario: Sessions beyond the lookback are unaffected
- **WHEN** a session falls further after a hard-flagged session than the
  longest indicator lookback
- **THEN** its indicator values are computed normally, since no window
  reaching back to it spans the flagged step

#### Scenario: Blacked-out rows do not reach model training
- **WHEN** the training row filter selects clean, labelled rows and some
  rows have had their indicator columns nulled by a hard-flag blackout
- **THEN** those rows are excluded, rather than entering training as
  all-missing feature vectors carrying valid labels

#### Scenario: A prediction is never served from missing features
- **WHEN** a prediction is requested for a ticker whose most recent
  features row has null indicator columns, for any reason
- **THEN** the system reports that no prediction is available for that
  ticker instead of computing one from the missing values

#### Scenario: Exclusion does not depend on the calendar-gap flag
- **WHEN** a row's indicator columns are null but its calendar-gap flag is
  clear
- **THEN** it is still excluded from training and from serving, because the
  calendar-gap flag describes gaps in trading sessions and carries no claim
  about price discontinuities

#### Scenario: Flag is persisted and inspectable
- **WHEN** a row is flagged
- **THEN** the flag is persisted and queryable per ticker and date, so the
  set of affected rows can be reviewed without recomputing the gate

### Requirement: Stale-price and illiquidity measurement
The system SHALL compute, per symbol, the fraction of sessions where the
close equals the previous session's close exactly, and SHALL record it on
the universe entry as a liquidity measure.

#### Scenario: Stale fraction computed and stored
- **WHEN** a symbol's OHLCV history is ingested
- **THEN** its stale-close fraction is computed over its full stored
  history and persisted

#### Scenario: A refetch that returns less history does not narrow the measurement
- **WHEN** a symbol is reloaded and the source returns a narrower window
  than is already stored, as the community tier's sliding ~8-year window
  does
- **THEN** the gate still evaluates the full stored history, so flags on
  sessions outside the new window survive the reload and the stale-close
  fraction is not recomputed over a partial series

#### Scenario: Illiquid symbol is flagged for exclusion
- **WHEN** a symbol's stale-close fraction exceeds the configured
  threshold
- **THEN** the symbol is flagged as failing the liquidity filter, and the
  measured value is retained so the threshold can be revisited without
  re-ingesting

#### Scenario: Filter is enforced, not advisory
- **WHEN** a consumer requests the modelling universe
- **THEN** symbols failing the liquidity filter are excluded from it by
  default, rather than merely carrying a warning

### Requirement: Quality gate runs before persistence decisions
The system SHALL apply the quality gate as part of ingestion, so that
quality state is available at the time data enters the database rather
than being reconstructed later.

#### Scenario: Gate results available immediately after load
- **WHEN** a symbol is ingested
- **THEN** its price-limit flags and stale-close fraction are available
  without a separate follow-up pass
