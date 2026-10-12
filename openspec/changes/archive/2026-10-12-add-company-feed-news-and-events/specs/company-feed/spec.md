## ADDED Requirements

### Requirement: VCI company news and events are fetched per ticker through the project's vnstock wrapper
The system SHALL fetch, for each requested ticker, the VCI company news and the VCI corporate events through `vnstock`'s Unified UI company reference (`news` and `events`), passing `source="vci"` explicitly on every call because the wrapper's own default is a different source. It SHALL record `vci` as the stored `source`. It SHALL NOT call a vendor URL, a private vnstock method (including the paged `_fetch_*` methods) or any API the wrapper already covers. A call returns at most 50 items; history before that window is not retrievable, and the log SHALL NOT claim to hold it.

#### Scenario: Source is set explicitly
- **WHEN** news and events are fetched for `SAB`
- **THEN** both calls pass `source="vci"` and every stored row for them has `source = 'vci'`

#### Scenario: Both kinds are fetched
- **WHEN** a ticker is snapshotted
- **THEN** one fetch of kind `news` and one of kind `events` are made and each is recorded

#### Scenario: The vendor cap is a recorded fact
- **WHEN** a call returns 50 items
- **THEN** its fetch row has `items_returned = 50` and no claim is made that earlier items do not exist

### Requirement: Vendor access goes through the guard, from one module
Only the fetch module of the company feed SHALL contain a `vnstock` import, and it SHALL call `app.vnstock_guard.install()` before that import. The normalise and store modules SHALL import no `vnstock` module, directly or through another repository module, so they can be tested and used without the vendor library.

#### Scenario: The repository guard test stays green
- **WHEN** `test_every_vnstock_importer_installs_the_guard_first` runs after the change
- **THEN** it passes, and the fetch module appears in its scan with the guard import first

#### Scenario: Only the fetch module imports the vendor
- **WHEN** the files of the company feed package are scanned for `import vnstock` and `from vnstock` statements
- **THEN** only the fetch module has one

#### Scenario: Pure modules do not need the vendor
- **WHEN** the normalise and store modules are imported in a process where `vnstock` is blocked from importing
- **THEN** both imports succeed

### Requirement: Stored text is cleaned, bounded and in its original language
Every string stored from a vendor frame or a feed SHALL pass through the existing `_clean` function of `backend/app/services/debate/news_feeds.py` (entities decoded then markup stripped, whitespace collapsed, NFC normalisation, every Unicode control and format character removed) and SHALL then be capped: titles at 500 characters, other string fields at 200. Titles SHALL keep their original language: nothing SHALL translate, summarise or re-word them, and no language-model call SHALL be made. A column that holds an item's body text SHALL NOT be stored, and a non-empty value in one SHALL be reported once per run as a warning. A cell that is not a scalar SHALL be skipped and counted. NaN, NaT and numpy scalars SHALL be stored as `null` and plain Python values, so every `fields` value is valid JSON without `NaN`.

#### Scenario: Markup and invisible characters are removed
- **WHEN** a title arrives as `"<b>SAB:</b> Th​ông báo &amp; kết quả"` with a zero-width character inside
- **THEN** the stored title is `"SAB: Thông báo & kết quả"` with no tag, no zero-width character and the Vietnamese diacritics intact

#### Scenario: Composed and decomposed forms agree
- **WHEN** the same Vietnamese title arrives once in composed and once in decomposed Unicode form
- **THEN** both are stored as the same NFC text and yield the same item id

#### Scenario: The language is not changed
- **WHEN** a title is Vietnamese
- **THEN** the stored title is Vietnamese, and no model or translation function is called

#### Scenario: Oversized text is bounded
- **WHEN** a title is 5,000 characters long
- **THEN** the stored title is at most 500 characters

#### Scenario: A body column is dropped
- **WHEN** a news frame carries a non-empty `news_full_content`
- **THEN** that text is not stored anywhere in the log and a warning names the column once for the run

#### Scenario: Events with missing values store valid JSON
- **WHEN** an events frame has NaN in `exright_date` for some rows
- **THEN** the stored `fields` for those rows hold `null` for it and parse with a strict JSON parser

### Requirement: Items are stored once per version, keyed for de-duplication
The system SHALL store each item in a table `company_feed_item` with `ticker`, `source`, `kind` (`news`, `events` or `rss`), `item_id`, `content_hash`, `fetched_at`, `published_at`, `title`, `fields` (JSON) and the id of the fetch that first saw it. `item_id` SHALL be derived only from the fields that identify the item (kind, ticker, source, the published date, the title and, for events, the event code). `content_hash` SHALL be derived from every stored field. A row SHALL be inserted only when no row exists with the same `(ticker, source, kind, item_id, content_hash)`; `fetched_at` SHALL be the time the version was first seen, UTC with an explicit offset. `company_feed_item` rows SHALL never be updated or deleted by the company feed.

#### Scenario: A repeated item is not stored twice
- **WHEN** the same ticker is snapshotted twice and the vendor returns the same 50 items both times
- **THEN** the item table holds 50 rows for it, and the second fetch row has `items_returned = 50` and `items_new = 0`

#### Scenario: A revised item becomes a new version
- **WHEN** an event's `payout_date` changes from empty to a date between two runs
- **THEN** a new row exists with the same `item_id` and a different `content_hash`, and the earlier row is unchanged

#### Scenario: Overlapping runs are harmless
- **WHEN** two snapshot runs write the same items at the same time
- **THEN** no duplicate row exists and neither run fails because of the other

#### Scenario: `fetched_at` is the first sighting
- **WHEN** an item is returned by the vendor in three successive runs
- **THEN** its single row carries the time of the first run

### Requirement: Every fetch is recorded, including empty and failed ones
The system SHALL store one row in `company_feed_fetch` per fetch attempt, with `ticker` (empty for an RSS feed), `source`, `kind`, `fetched_at`, `status`, `items_returned`, `items_new`, `error_class` and `vnstock_version`. `status` SHALL be `ok` when items were returned, `empty` when the vendor returned no items, `rate_limited` when the rate limit stopped the fetch, and `error` otherwise. An empty result SHALL NOT be an error. A non-empty frame that lacks a column the company feed requires for its kind SHALL be an `error` with `error_class = 'UnexpectedFrame'`, not an empty result. `error_class` SHALL hold the exception class name only, never its message.

#### Scenario: A quiet ticker is empty, not an error
- **WHEN** the vendor returns an empty frame for a ticker's events
- **THEN** a fetch row exists with `status = 'empty'`, `items_returned = 0` and no `error_class`

#### Scenario: A changed frame is an error
- **WHEN** a non-empty news frame has no title column
- **THEN** a fetch row exists with `status = 'error'` and `error_class = 'UnexpectedFrame'`, and no item row is written

#### Scenario: An exception message is not stored
- **WHEN** a fetch raises an exception whose message contains a long promotional text
- **THEN** the fetch row holds the class name and none of the message

### Requirement: A failed fetch or write is non-fatal and never silent
A fetch that raises SHALL NOT stop the run: it SHALL be logged at ERROR with its traceback naming the ticker and kind, recorded as an `error` fetch row, and the run SHALL continue with the next fetch. A failure to write SHALL be logged at ERROR with its traceback, counted, and SHALL NOT stop the run. The run summary SHALL list every failure, and the process exit code SHALL be 0 only when every fetch ended `ok` or `empty` and every write succeeded, 1 otherwise, and 2 for a usage error. A `SystemExit` that is not vnai's rate limit SHALL be re-raised.

#### Scenario: One ticker fails
- **WHEN** the fetch for the second of three tickers raises `ValueError`
- **THEN** the first and third tickers are fetched and stored, the second has an `error` fetch row and an ERROR log with a traceback, and the exit code is 1

#### Scenario: The insert fails
- **WHEN** the insert for one fetch raises because the file is locked
- **THEN** an ERROR with a traceback is logged, the run continues, the summary counts one write failure, and the exit code is 1

#### Scenario: A genuine exit is honoured
- **WHEN** a fetch raises `SystemExit` with a message that is not a rate-limit message
- **THEN** the exception propagates and the run ends

#### Scenario: Nothing to fetch
- **WHEN** the script is started with neither `--tickers` nor `--from-debate-log`
- **THEN** it makes no request, writes nothing and exits with code 2

### Requirement: The vendor rate limit is paced under and survived
The snapshot SHALL pace vendor fetches at no more than 8 tickers a minute by default (two vendor requests per ticker), settable with `--tickers-per-minute`. It SHALL NOT let vnai's rate-limit `SystemExit` end the process: when a call raises a `SystemExit` that the repository's `_is_rate_limit_exit` identifies as vnai's limiter, or `vnstock.core.exceptions.RateLimitError`, it SHALL wait 60 seconds and retry that call, at most 5 times; after that it SHALL record the fetch as `rate_limited`, stop the run, list the tickers not attempted, and exit non-zero. A `tenacity.RetryError` SHALL be unwrapped to its last exception before classification. RSS fetches are not vendor-metered and SHALL run first.

#### Scenario: Pacing
- **WHEN** 24 tickers are requested with the default pacing
- **THEN** no more than 8 tickers are started in any 60-second window

#### Scenario: A rate-limit exit is waited out
- **WHEN** a call raises `SystemExit("Rate limit exceeded. ... Process terminated.")` once and then succeeds
- **THEN** the run waits 60 seconds, retries that call, stores its items and records `ok`

#### Scenario: Persistent rate limit stops the run
- **WHEN** the same call hits the limit six times
- **THEN** its fetch row has `status = 'rate_limited'`, the remaining tickers are listed as not attempted, and the exit code is non-zero

#### Scenario: Wrapped errors are classified
- **WHEN** the wrapper raises `tenacity.RetryError` whose last attempt raised `ValueError`
- **THEN** the fetch is recorded as `error` with `error_class = 'ValueError'`

### Requirement: No API key is used, stored or required
The company feed SHALL run on the vendor's guest tier. It SHALL NOT set, read, store, log or document an API key, and SHALL store no environment value. If `VNSTOCK_API_KEY` is set or `~/.vnstock/api_key.json` exists, the script SHALL print and log a warning that vnai's key-gated paths are in play, checking existence only and never opening the file, and SHALL still run.

#### Scenario: No key
- **WHEN** neither the environment variable nor the key file exists
- **THEN** the run proceeds with no warning about a key

#### Scenario: A key is present
- **WHEN** `VNSTOCK_API_KEY` is set in the environment
- **THEN** the run prints a warning that names the variable but not its value, and the value appears in no log line, summary or row

#### Scenario: No credential in the log file
- **WHEN** a run completes
- **THEN** no column of `company_feed_fetch` or `company_feed_item` holds an environment value

### Requirement: RSS items are snapshotted into the same log
The snapshot SHALL, once per run and unless `--no-rss` is given, fetch each feed in `news_feeds.FEEDS` through the existing bounded fetch of `news_feeds.py` (no new HTTP code) and store every returned item with `kind = 'rss'`, `source` the feed URL, `ticker = ''`, `published_at` in UTC, `title`, and the cleaned snippet in `fields`. The items SHALL NOT be filtered by ticker, sector or age. One fetch row SHALL be written per feed. One feed failing SHALL NOT stop the others. The News agent, `fetch_headlines` and the debate runner SHALL NOT be changed or read the log.

#### Scenario: All three feeds are stored
- **WHEN** the three feeds return 60, 50 and 20 items
- **THEN** 130 `rss` item rows exist (fewer if some repeat an earlier run) and three fetch rows with `ticker = ''`

#### Scenario: One feed is down
- **WHEN** one of three feeds raises a timeout
- **THEN** its fetch row is an `error`, the other two feeds are stored, and the exit code is 1

#### Scenario: The snippet is kept, the identity ignores it
- **WHEN** a feed edits an item's snippet between runs and leaves its title and date alone
- **THEN** a new version row exists with the same `item_id`

#### Scenario: News agent unchanged
- **WHEN** the company feed has stored RSS items
- **THEN** `fetch_headlines` returns the same lines as before, from live feeds, and nothing reads the log

### Requirement: The log lives in its own file and never touches `app.db` or `debate_log.db`
The system SHALL keep the tables `company_feed_item` and `company_feed_fetch` in `backend/data/company_feed_log.db`, created with `CREATE TABLE IF NOT EXISTS` by the module's own init function on the first write. `app.db`'s `init_db` SHALL NOT create, alter or drop them, the company feed SHALL NOT alter any `app.db` or `debate_log.db` table, and `debate_log.db` SHALL NOT hold company feed text. The file SHALL be gitignored. Tests SHALL NOT create or write the real file.

#### Scenario: First write creates the file
- **WHEN** `company_feed_log.db` does not exist and a snapshot stores an item
- **THEN** the file is created with both tables and one item row, and `app.db` and `debate_log.db` are unchanged

#### Scenario: Re-initialising a populated log
- **WHEN** the init function runs against a log that already holds rows
- **THEN** the rows are unchanged and no error is raised

#### Scenario: Rebuilding app.db
- **WHEN** `app.db` is deleted and rebuilt
- **THEN** `company_feed_log.db` and its rows are unaffected

#### Scenario: Tests do not write to the real log
- **WHEN** the backend test suite runs
- **THEN** `backend/data/company_feed_log.db` is neither created nor changed by it

### Requirement: The snapshot runs only by hand
Snapshotting SHALL be started only by `backend/scripts/snapshot_company_feed.py`, run manually. No debate post-run hook, API route, ticker load or Refresh path, application startup hook, background task or scheduler SHALL call the snapshot, and nothing in `backend/app/` outside the company feed package SHALL import it. `--dry-run` SHALL fetch and report what would be stored and write nothing.

#### Scenario: No other caller
- **WHEN** the modules under `backend/app/` outside `company_feed` are scanned for imports of the package
- **THEN** none is found

#### Scenario: Dry run writes nothing
- **WHEN** the script runs with `--dry-run`
- **THEN** `company_feed_log.db` is not created or changed and the summary lists what would have been stored

### Requirement: The run report makes a lapse or a possible gap visible
Because the snapshot clock ticks only when the script runs, the run summary SHALL state, for each ticker and kind, the age of the previous successful fetch (or that there was none). When a fetch returns 50 items, all of them new, for a ticker and kind that already had a successful fetch, the run SHALL log a warning `possible gap` naming the ticker and kind, because items were probably missed between runs, and the summary SHALL repeat it. A first fetch that returns 50 items SHALL NOT be reported as a gap.

#### Scenario: A lapse is visible
- **WHEN** a ticker's previous successful news fetch was 9 days ago
- **THEN** the summary states that age for that ticker and kind

#### Scenario: A possible gap is reported
- **WHEN** a ticker that already has a successful fetch returns 50 items and all 50 are new
- **THEN** the run logs a warning `possible gap` naming the ticker and kind, and the summary repeats it

#### Scenario: A first fetch is not a gap
- **WHEN** a ticker is fetched for the first time and returns 50 items
- **THEN** no `possible gap` warning is logged

### Requirement: Stored items can be read back with their provenance
The company feed SHALL provide `latest_items(ticker, kind, since=None)`, returning one row per `item_id` (its latest version) newest published first, each with `first_seen_at` and `from_first_fetch` (true when the item arrived in the first successful fetch for that ticker and kind, so a consumer can treat it as history, not as known on its date); and `last_fetch(ticker, kind)`, returning the latest fetch row and the time of the latest `ok` or `empty` fetch. Both SHALL open the log read-only, and a missing log file SHALL read as never fetched, not as an error. There SHALL be no API route and no UI for them.

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

### Requirement: `vnstock` and `vnai` are pinned exactly
`backend/requirements.txt` SHALL list `vnstock==4.0.5` and `vnai==2.5.5` as exact pins, with a comment stating how a bump is done: both pins changed together, a fresh virtual environment built from the file, the guard tests including the sandboxed-`HOME` test and the control run without the guard, a read of the new `vnai` and `vnstock` code for new write paths, a one-ticker dry run of the snapshot, and the result recorded in `docs/KNOWN_ISSUES.md`.

#### Scenario: Exact pins
- **WHEN** `backend/requirements.txt` is read
- **THEN** it contains the lines `vnstock==4.0.5` and `vnai==2.5.5` and no other `vnstock` or `vnai` requirement

#### Scenario: A loose pin fails a test
- **WHEN** either line is changed to `>=`, `~=` or no version
- **THEN** the pin test fails

### Requirement: The company feed makes no model call and shows nothing
The company feed SHALL make no language-model call and SHALL NOT display, export or return any stored text to a user, so Rules 1 to 6 are neither engaged nor changed by it. Whatever later displays these titles SHALL label them by provenance (Rule 5), show the disclaimer (Rule 6) and fence them in any prompt.

#### Scenario: No model client is used
- **WHEN** a snapshot run is traced
- **THEN** no `LLMClient` or provider SDK is constructed or called

#### Scenario: No route exposes the log
- **WHEN** the application's routes are listed
- **THEN** none reads `company_feed_log.db`
