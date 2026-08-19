## MODIFIED Requirements

### Requirement: Ticker panel shows the fixed set plus search for any real ticker
The dashboard's ticker panel SHALL render one selectable **entry** (a chip
for the fixed Watchlist, a list row for any other ticker) per ticker
returned by `GET /tickers` (the 9 `TRAINING_TICKERS`) plus every
successfully-loaded searched-in ticker. The 9 `TRAINING_TICKERS` SHALL
always be visible as the fixed **Watchlist**, regardless of any filter or
search input state. The panel SHALL also provide a search action that
resolves a user-entered ticker symbol; if that ticker is not yet loaded,
the search action SHALL trigger `POST /tickers/{ticker}/load` the same way
selecting an unloaded entry would, and the ticker SHALL join the
selectable searched-in list once loaded successfully. The same input MAY
also live-filter the searched-in list's visible entries as the user types,
provided this filtering never hides or otherwise affects the Watchlist.

#### Scenario: Panel renders the fixed set as chips
- **WHEN** the dashboard loads
- **THEN** the ticker panel shows one selectable chip per ticker in the
  Watchlist (the 9 tickers returned by `GET /tickers`), always visible
  regardless of search or filter state

#### Scenario: Searching an unloaded ticker triggers a load
- **WHEN** a user searches a ticker symbol that has no rows in `ohlcv`
  yet
- **THEN** the dashboard calls `POST /tickers/{ticker}/load` for that
  symbol, and the ticker becomes selectable once the load succeeds

#### Scenario: Searching an already-loaded ticker selects it directly
- **WHEN** a user searches a ticker symbol that already has data loaded
  (whether a Watchlist entry or a previously searched-in ticker)
- **THEN** the dashboard selects it directly without issuing a new
  `/load` request

#### Scenario: A searched-in ticker persists as a selectable entry
- **WHEN** a searched ticker outside `TRAINING_TICKERS` has loaded
  successfully at least once
- **THEN** it remains selectable in the ticker panel's searched-in list for
  the rest of the session, alongside the Watchlist

#### Scenario: Filter narrows the searched-in list only
- **WHEN** a user types a substring into the ticker panel's search input
  without submitting
- **THEN** the searched-in list's visible entries narrow to those whose
  symbol contains the typed substring, and the count of visible entries is
  announced to screen readers via an `aria-live` region

#### Scenario: Fixed Watchlist remains visible regardless of filter input
- **WHEN** a user types a substring into the ticker panel's search input
  that matches none of the 9 `TRAINING_TICKERS`
- **THEN** all 9 Watchlist entries remain visible and selectable; only the
  searched-in list's visible entries change
