## ADDED Requirements

### Requirement: Refresh action available for any loaded ticker
The ticker panel SHALL provide a "Refresh" action for every ticker that
is already loaded (whether one of the fixed `TRAINING_TICKERS` chips or
a previously searched-in ticker), which calls `POST
/tickers/{ticker}/load` for that ticker. The action SHALL be available
regardless of the ticker's current freshness state (Fresh, Stale, or
Loading-not-yet-settled), since freshness reflects internal
prediction/data consistency, not calendar recency, and hiding the action
based on freshness would leave a calendar-stale-but-Fresh ticker with no
corrective action.

#### Scenario: Refresh is offered for a Fresh ticker
- **WHEN** a ticker is loaded and its freshness state is Fresh
- **THEN** the ticker panel still shows an enabled Refresh action for it

#### Scenario: Refresh is offered for a Stale ticker
- **WHEN** a ticker is loaded and its freshness state is Stale
- **THEN** the ticker panel shows an enabled Refresh action for it

#### Scenario: Refresh is not offered for a never-loaded ticker
- **WHEN** a ticker in the fixed set has never been loaded (no row in
  `ohlcv`)
- **THEN** the ticker panel does not show a Refresh action for it — the
  existing load-on-click behavior remains the only way to fetch it the
  first time

#### Scenario: Triggering refresh calls the existing load endpoint
- **WHEN** a user activates the Refresh action for a loaded ticker
- **THEN** the dashboard calls `POST /tickers/{ticker}/load` for that
  ticker, identically to the request the app would make for a first-time
  load

### Requirement: Refresh is disabled while a load is already in flight
The Refresh action for a given ticker SHALL be disabled whenever that
same ticker already has a `/load` request in flight — whether that
request was started by the refresh action itself, the original
load-on-first-select flow, or a search-triggered load — so a user cannot
issue overlapping `/load` requests for the same ticker.

#### Scenario: Refresh is disabled during its own in-flight request
- **WHEN** a user activates Refresh for a ticker
- **THEN** the Refresh action becomes disabled until that request
  settles (success or failure)

#### Scenario: Refresh is disabled during a concurrent load from another entry point
- **WHEN** a ticker's `/load` request is in flight because it was just
  searched-in for the first time
- **THEN** that ticker's Refresh action (if shown) is disabled for the
  same duration, rather than allowing a second concurrent `/load` call
  for the same ticker

### Requirement: Successful refresh invalidates the same dependent data as an initial load
When a Refresh action's `/load` request completes with `status: "ok"`,
the dashboard SHALL invalidate and refetch that ticker's catalog entry,
history, prediction, and AI insight data, identically to what already
happens after a first-time load, so the chart, prediction display, and
AI insight panel reflect the newly fetched data without requiring a page
reload or reselecting the ticker.

#### Scenario: Chart reflects refreshed data automatically
- **WHEN** a Refresh action's `/load` request completes with `status:
  "ok"` for the currently selected ticker
- **THEN** the chart panel's candles update to reflect the newly fetched
  history without the user needing to reselect the ticker

#### Scenario: Prediction and insight panel reflect refreshed data automatically
- **WHEN** a Refresh action's `/load` request completes with `status:
  "ok"` for the currently selected ticker
- **THEN** the prediction display and AI insight panel update to reflect
  the newly computed prediction and insight for that ticker

#### Scenario: Non-ok refresh result does not silently discard the previous data
- **WHEN** a Refresh action's `/load` request completes with a status
  other than `"ok"` (`rate_limited`, `invalid_symbol`, or `no_data`)
- **THEN** the dashboard does not invalidate the ticker's existing
  history, prediction, or insight data, and the previously displayed
  chart/prediction/insight for that ticker remains visible and unchanged

### Requirement: Refresh failure is reported distinctly, reusing existing status messages
When a Refresh action's `/load` request does not complete with `status:
"ok"`, the dashboard SHALL report the outcome using the same
per-status messages already defined for the load flow (rate-limited,
invalid symbol, no data, or a generic network/error message), so a
refresh failure is never silently swallowed or shown as a generic
"something went wrong" for a status that has a more specific message
available.

#### Scenario: Rate-limited refresh reuses the existing rate-limited message
- **WHEN** a Refresh action's `/load` request completes with `status:
  "rate_limited"`
- **THEN** the dashboard shows the same rate-limited message already
  shown for a first-time load hitting the same status

#### Scenario: Refresh network failure is visible
- **WHEN** a Refresh action's `/load` request fails outright (network
  error, no response)
- **THEN** the dashboard shows an error indication for that ticker
  rather than leaving the Refresh action silently re-enabled with no
  feedback

### Requirement: Last-loaded time is visible for any loaded ticker
The ticker panel SHALL display each loaded ticker's `last_loaded_at`
(already returned by `GET /tickers`) in a human-readable relative form
(e.g. "Loaded 14d ago"), visible without requiring the user to trigger a
refresh or open a separate view, so the Refresh action has a legible
reason attached to it rather than appearing as an unexplained control.

#### Scenario: Last-loaded time shown for a loaded ticker
- **WHEN** a ticker has a non-null `last_loaded_at` from `GET /tickers`
- **THEN** the ticker panel displays a relative-time rendering of that
  value for the ticker

#### Scenario: Last-loaded time absent for a never-loaded ticker
- **WHEN** a ticker has a null `last_loaded_at` (never loaded)
- **THEN** the ticker panel displays no last-loaded time for it, and
  shows the existing "Not loaded" treatment instead

#### Scenario: Last-loaded time updates after a successful refresh
- **WHEN** a Refresh action completes with `status: "ok"` for a ticker
- **THEN** the displayed last-loaded time for that ticker updates to
  reflect the new `last_loaded_at` value from the refetched catalog data
