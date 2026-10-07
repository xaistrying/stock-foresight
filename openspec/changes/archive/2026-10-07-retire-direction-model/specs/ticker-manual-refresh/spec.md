## ADDED Requirements

### Requirement: Refresh action available for every loaded ticker
The ticker panel SHALL provide a "Refresh" action for every ticker that
is already loaded (whether a Watchlist chip or a previously searched-in
ticker), which calls `POST /tickers/{ticker}/load` for that ticker. The
action SHALL be available regardless of how old the ticker's data is, since
the panel carries no freshness state and hiding the action would leave a
calendar-old ticker with no corrective action.

#### Scenario: Refresh is offered for every loaded ticker
- **WHEN** a ticker is loaded, whatever its `last_loaded_at`
- **THEN** the ticker panel shows an enabled Refresh action for it

#### Scenario: Refresh is not offered for a never-loaded ticker
- **WHEN** a ticker in the catalog has never been loaded (no row in
  `ohlcv`)
- **THEN** the ticker panel does not show a Refresh action for it — the
  existing load-on-search behavior remains the only way to fetch it the
  first time

#### Scenario: Triggering refresh calls the existing load endpoint
- **WHEN** a user activates the Refresh action for a loaded ticker
- **THEN** the dashboard calls `POST /tickers/{ticker}/load` for that
  ticker, identically to the request the app would make for a first-time
  load

### Requirement: Successful refresh invalidates history, catalog and range
When a Refresh action's `/load` request completes with `status: "ok"`,
the dashboard SHALL invalidate and refetch that ticker's catalog entry,
history and range data, identically to what already happens after a
first-time load, so the chart, the range display and the chip's last-loaded
time reflect the newly fetched data without requiring a page reload or
reselecting the ticker. The dashboard SHALL NOT invalidate or fetch any
other per-ticker endpoint as part of a refresh.

#### Scenario: Chart reflects refreshed data automatically
- **WHEN** a Refresh action's `/load` request completes with `status:
  "ok"` for the currently selected ticker
- **THEN** the chart panel's candles update to reflect the newly fetched
  history without the user needing to reselect the ticker

#### Scenario: Range display reflects refreshed data automatically
- **WHEN** a Refresh action's `/load` request completes with `status:
  "ok"` for the currently selected ticker
- **THEN** the range display and the chart's range band update to the
  newly computed range for that ticker

#### Scenario: Refreshing an unselected ticker fetches nothing beyond the catalog
- **WHEN** a Refresh action completes with `status: "ok"` for a ticker that
  is not selected
- **THEN** the catalog is refetched and no `/range` or `/history` request is
  issued until that ticker is selected

#### Scenario: Non-ok refresh result does not silently discard the previous data
- **WHEN** a Refresh action's `/load` request completes with a status
  other than `"ok"` (`rate_limited`, `invalid_symbol`, or `no_data`)
- **THEN** the dashboard does not invalidate the ticker's existing
  history or range data, and the previously displayed chart and range
  for that ticker remain visible and unchanged

## REMOVED Requirements

### Requirement: Refresh action available for any loaded ticker
**Reason**: Its text and two scenarios (Fresh and Stale tickers) depend on the freshness state, which is removed with the dot.
**Migration**: "Refresh action available for every loaded ticker".

### Requirement: Successful refresh invalidates the same dependent data as an initial load
**Reason**: It names the prediction and AI insight data, whose endpoints and panels are deleted.
**Migration**: "Successful refresh invalidates history, catalog and range".
