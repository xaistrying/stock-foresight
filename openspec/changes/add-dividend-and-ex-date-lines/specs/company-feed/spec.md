## MODIFIED Requirements

### Requirement: The snapshot runs only by hand
Snapshotting SHALL be started only by `backend/scripts/snapshot_company_feed.py`, run manually. No debate post-run hook, API route, ticker load or Refresh path, application startup hook, background task or scheduler SHALL call the snapshot, and nothing in `backend/app/` outside the company feed package SHALL import the snapshot, the fetch module or any module of the package other than the store module. The one exception to "nothing outside the package imports the package" is the weekly brief's single adapter, `backend/app/services/brief/feed_source.py`, which SHALL import the store module's read helpers only (see "Stored items can be read back with their provenance"). `--dry-run` SHALL fetch and report what would be stored and write nothing.

#### Scenario: No other caller
- **WHEN** the modules under `backend/app/` outside `company_feed` are scanned for references to the package
- **THEN** the only file found is `backend/app/services/brief/feed_source.py`, and its imports from the package are the store module and nothing else

#### Scenario: The brief cannot start a snapshot
- **WHEN** the brief's run module is imported in a fresh process, and separately its adapter alone
- **THEN** `app.services.company_feed.fetch` and `app.services.company_feed.snapshot` are in neither process's `sys.modules`, and `vnstock` is not in the adapter-only process (the brief's own refresh path, which wraps the price loader, loads `vnstock`, so that module is not asserted absent from the whole brief)

#### Scenario: A second brief file references the feed
- **WHEN** any file under `backend/app/` other than the adapter and `backend/app/db/company_feed_log.py` contains `company_feed`, or any file outside `tests/` other than the adapter and `scripts/snapshot_company_feed.py` imports `services.company_feed`
- **THEN** `test_company_feed_isolation.py` fails and names the file

#### Scenario: Dry run writes nothing
- **WHEN** the script runs with `--dry-run`
- **THEN** `company_feed_log.db` is not created or changed and the summary lists what would have been stored

### Requirement: Stored items can be read back with their provenance
The company feed SHALL provide `latest_items(ticker, kind, since=None)`, returning one row per `item_id` (its latest version) newest published first, each with `first_seen_at` and `from_first_fetch` (true when the item arrived in the first successful fetch for that ticker and kind, so a consumer can treat it as history, not as known on its date); and `last_fetch(ticker, kind)`, returning the latest fetch row and the time of the latest `ok` or `empty` fetch. Both SHALL open the log read-only, and a missing log file SHALL read as never fetched, not as an error. There SHALL be no API route and no UI for them. Outside the snapshot script and the tests, the only reader of these helpers SHALL be the weekly brief's one adapter, `backend/app/services/brief/feed_source.py`, and no helper SHALL be added to the package for it.

#### Scenario: Latest version only
- **WHEN** an item has two stored versions
- **THEN** `latest_items` returns the later one once, with `first_seen_at` of the earlier

#### Scenario: Backfill is marked
- **WHEN** a ticker's first fetch stored 50 items and a later fetch stored 2 more
- **THEN** the 50 have `from_first_fetch = true` and the 2 have `false`

#### Scenario: Never fetched
- **WHEN** the log file does not exist
- **THEN** `latest_items` returns an empty list and `last_fetch` returns none

#### Scenario: None found is not never fetched
- **WHEN** the latest fetch for a ticker and kind is `empty`
- **THEN** `last_fetch` reports a successful fetch time, which a caller can tell apart from a missing or failed fetch

#### Scenario: The brief reads through the helpers only
- **WHEN** the adapter reads a ticker's events
- **THEN** it does so through `latest_items` and `last_fetch`, the log is opened read-only, and no row of `company_feed_item` or `company_feed_fetch` is written, updated or deleted

### Requirement: The company feed makes no model call and shows nothing
The company feed SHALL make no language-model call and SHALL NOT itself display, export or return any stored text to a user. The only stored values that reach a user are event dates and numbers (ex-date, record date, payout date, per-share amount, exercise ratio, publication date) and an issue class (an enumeration derived inside the weekly brief's one adapter from keywords in the stored title, so that only the enumeration value leaves the adapter), shown by the weekly brief; no stored title, snippet, source name or link SHALL be displayed, carried out of the adapter or exported until a later change shows them, and Rules 1 to 6 are neither engaged nor changed by the feed itself. Whatever displays these titles SHALL label them by provenance (Rule 5), show the disclaimer (Rule 6) and fence them in any prompt, and whatever displays the dates and numbers SHALL label them by their source and state when the feed was last fetched.

#### Scenario: No model client is used
- **WHEN** a snapshot run is traced
- **THEN** no `LLMClient` or provider SDK is constructed or called

#### Scenario: No route exposes the log
- **WHEN** the application's routes are listed
- **THEN** none reads `company_feed_log.db`

#### Scenario: No stored text reaches the brief
- **WHEN** the brief's adapter builds an event from a stored row
- **THEN** the event carries no title, snippet or other string from the row except the event code; for an issue event it carries the issue class enumeration derived from the title, and the title itself is not kept
