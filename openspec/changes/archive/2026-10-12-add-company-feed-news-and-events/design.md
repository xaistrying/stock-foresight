## Context

Step 2a of `docs/DISCUSSION_describe_not_vote_redesign.md` ("Settled for step 1", "Decided 2026-10-09" items 3 to 6, "Proposal breakdown"). Facts this design stands on, with where each comes from.

- **What the vendor gives** (measured 2026-10-09 on SAB, VPB, VCB, VHM, SSI, HPG; this proposal made no vendor call): VCI `news()` returns 50 items covering 4 months (VPB, SSI) to 16 months (SAB), with `ticker` (always `None`), `news_title`, `news_source`, `news_full_content` and `public_date`; body, source, link and author are empty in every row checked. VCI `events()` returns at most 50 rows (42 for VHM), dated history from about 8 months to about 9 years, with `event_code`, `value_per_share`, `exercise_ratio`, `exright_date`, `record_date`, `payout_date`; director-deal rows can crowd the cap (SSI: 35 of 50).
- **The cap is structural.** In the installed 4.0.5, `news()` and `events()` take no arguments; the explorer fetches page 0 with `size=50` (`vnstock/explorer/vci/company.py`, `_fetch_news`, `_fetch_events`). Paging exists only on those private methods, which the project's vnstock skill does not wrap.
- **RSS** (`news_feeds.py`): three feeds, 130 items in about four days when measured 2026-10-08; `fetch_headlines` returns formatted, ticker-filtered lines and discards the rest, so nothing of the feeds is kept.
- **The guard.** `app.vnstock_guard.install()` must precede any vnstock import, and `test_every_vnstock_importer_installs_the_guard_first` (`backend/tests/test_vnstock_guard.py:107`) scans `backend/` for violations. Existing importers do it in the same way: `ticker_ingestion.py:9-14`, `ticker_universe.py:14-18`, `debate/macro.py:22-29`, `scripts/verify_vnstock_tier_limit.py:44-48`.
- **vnai's rate limiter exits the process.** It calls `sys.exit(...)` from a context manager's `__exit__` (`vnai/beam/quota.py`, `CleanErrorContext`), a `SystemExit` that `except Exception` misses. `bulk_ingestion.py:62-70, 136` documents the first full ingestion dying at symbol 12 of 634 because of it, and `macro.py:142-150` (`_soft_fail`) notes that raised in a worker thread it "reaches the event loop through `asyncio.to_thread` and ends the server". `macro.py:32` imports `_is_rate_limit_exit` from `bulk_ingestion` ("one definition of vnai's exit"). The guest-tier counter is in process memory (`Guardian.usage_counters`); the guest limit is 20 requests a minute (`bulk_ingestion.py:46-53`, `ingest_universe.py` docstring).
- **The outcome-log pattern** (`debate-outcome-log`; `app/db/debate_log.py`, `outcome_log.py`): its own SQLite file created on first write by its own init, the writer raises, the caller decides it must neither fail the request nor be silent (ERROR log with traceback, a visible null). `backend/.gitignore:39` (`data/*.db*`) already ignores a new `*.db` file; `backend/tests/conftest.py:48` (`_temporary_debate_log`) is how tests keep off the real file.
- **Decisions already made by the owner**, not reopened here: personal use only; no API key; exact pin of `vnstock==4.0.5` and `vnai==2.5.5` (`vnstock` 4.0.5 requires only `vnai>=2.5.2`, so the pair is consistent; both are what the venv holds); no News-agent feed; a separate log file; original-language titles, no translation, no model call.

## Goals / Non-Goals

**Goals:**
- Fetch VCI company news and events for chosen tickers, clean the text, store it, and keep a growing, de-duplicated record with the time each item was first seen.
- Snapshot the RSS items now, since they cannot be backfilled.
- Fail visibly and never take the server or a run down; survive vnai's rate limit.
- Leave a data layer P2b (readings) and S2 (event windows) can read without touching the vendor.
- Pin the vendor library so a silent upgrade cannot move the AI-config write path.

**Non-Goals:** feeding or changing the News agent (decision 5); any UI, API route or export; readings, a coverage table or "last item" display (P2b); matching titles to tickers or sectors, `[ticker]` aliases (P2b); relevance classification of any kind; fundamentals (P4); the event-window study (S2); an API key; translation or any model gist; paging past 50 items; a scheduler; a nightly basket (P6); editing `news_feeds.py`, `bulk_ingestion.py`, `macro.py`, the debate code or any existing spec.

## Decisions

### 1. Trigger: a manual script, `backend/scripts/snapshot_company_feed.py`, and nothing else

**Recommendation.** One entry point, run by hand (cron-able; this change installs no scheduler). It takes `--tickers SAB,VPB` and/or `--from-debate-log` (the distinct tickers in `debate_log`, opened read-only), plus `--tickers-per-minute`, `--no-rss` and `--dry-run`. With neither ticker option it exits with a usage error. The logic lives in `company_feed/snapshot.py` so a later change can call it from elsewhere.

**Why not a post-run hook of `POST /debate`** (`runner.register_post_run_hook`, `runner.py:85`):
- A vnai rate-limit `SystemExit` raised in a hook's worker thread would end the server (see Context); `_run_hooks` (`runner.py:250-274`) catches only `Exception`. The script can catch it per call, exactly as `ingest_symbol` does.
- Hooks run in the response path under `DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS`, default 10 s (`llm_client.py:59`); two paced vendor calls plus the library's own retry backoff and a 60 s rate-limit wait do not fit.
- It would snapshot only tickers the owner analyses (4 distinct ticker-days in the log today) and never an ineligible one, which abstains before the runner (`api/debate.py`), so the clock would tick rarely and unevenly.
- It couples a data layer to the code P1 is rewriting and P3 retires.

**Why not ticker Refresh or load.** `load_ticker` is called once per symbol by `bulk_ingestion` (634 symbols); a snapshot inside it adds two vendor requests to the two it already spends (`REQUESTS_PER_SYMBOL = 2`). Hooking only the API route instead edits `ticker-manual-refresh` behaviour, adds latency to Refresh, runs in the server process (same `SystemExit` hazard) and again snapshots only what the owner happens to refresh.

**Cost of the script** (stated plainly): the clock ticks only when someone runs it. Mitigation: the summary prints, per ticker and kind, how long ago the previous successful fetch was, and warns on a possible gap (Decision 6), so a lapse is visible rather than silent. **Cadence recommendation, not a requirement**: daily after the close, because the RSS window is about four days (a gap beyond that loses items for good); the VCI items tolerate longer (the 50 news items span 4 months or more for every measured ticker, and SSI's 50 event rows reach back about 8 months), so a weekly run would still catch everything the measured tickers produce and the gap warning (Decision 6) covers the rest. **Revisit** when P2b ships a reading: it may add a trigger on the load or Refresh path, with the `SystemExit` guard of Decision 7.

### 2. Where it lives and how it is layered

`backend/app/services/company_feed/`, a package outside `services/debate/`: not under the code P1 and P3 rework, and not inside the News agent's module.

- `fetch.py`: the only module that imports vnstock (guard first, Decision 3). Returns frames and raises classified errors (rate limit, unexpected frame, other).
- `rss.py`: the RSS wrapper (Decision 9); no vnstock, so the one vnstock importer stays single-purpose.
- `normalise.py`: pure (pandas only, no vnstock): clean, identity, hashes, frame to records, JSON-safe values. Testable without the vendor.
- `store.py`: insert fetch rows and new items, read helpers (Decision 12). Also free of vnstock, directly and transitively.
- `snapshot.py`: orchestration: pacing, rate-limit handling, per-fetch failure handling, the run summary. The fetch functions are passed in (the script wires the real ones), so tests inject stubs and the clock and `sleep`, as `bulk_ingestion` does.
- `backend/app/db/company_feed_log.py`: path constant `COMPANY_FEED_LOG_DB_PATH`, connection, `CREATE TABLE IF NOT EXISTS`, init on first write. Mirrors `debate_log.py`; `schema.py` and `init_db` do not know it.

Imports from existing modules, by name and without editing them: `news_feeds._clean`, `_fetch_feed`, `FEEDS`, `HEADERS`, `TIMEOUT`, `MAX_REDIRECTS`; `bulk_ingestion._is_rate_limit_exit`, `RATE_LIMIT_WAIT_SECONDS`, `MAX_RATE_LIMIT_WAITS`, `DEFAULT_SYMBOLS_PER_MINUTE`; `connection.open_readonly`. Private names are imported on purpose: renaming or promoting them would edit shared files in the middle of P1. A test imports each name, so a rename elsewhere fails here, loudly (Decision 14).

### 3. Vendor access: the Unified UI, source set explicitly, one guarded importer

The project's vnstock skill says to use the Unified UI (`from vnstock.ui import Reference`; `Reference().company(symbol).news()` and `.events()`) unless a method exists only in the Legacy API. These two are wrapped. So `fetch.py` calls `Reference().company(symbol).news(source="vci")` and `.events(source="vci")`. The `source` is passed every time because `CompanyReference.news` defaults to `"kbs"` (`vnstock/ui/domains/reference/company.py`), and KBS data was found unusable for financial statements; the measurements in the note are VCI's. In the installed 4.0.5 the dispatch instantiates `Company(source="vci", symbol=...)` and calls its `news()`, the same call the note's probes made, so the frames should be identical; the first apply task confirms it and falls back to the Legacy `Company(source="vci", ...)`, which the skill allows when a source must be pinned.

`fetch.py` opens with `from app.vnstock_guard import install as _install_vnstock_guard` then `_install_vnstock_guard()`, then its vnstock imports, as `ticker_ingestion.py` does. No other module in the package imports vnstock, and the scan test stays green. No API call is hand-rolled: nothing here uses `_fetch_news`, a URL or `requests`.

### 4. Snapshot schema (new, nothing in `config.yaml` covers it)

Two append-only tables in `backend/data/company_feed_log.db`.

`company_feed_fetch` (one row per fetch attempt):

| Column | Meaning |
|---|---|
| `id` | INTEGER PK AUTOINCREMENT |
| `ticker` | TEXT NOT NULL; `''` for an RSS feed (feed-level, no ticker) |
| `source` | TEXT NOT NULL; `vci`, or the feed URL |
| `kind` | TEXT NOT NULL; `news`, `events` or `rss` |
| `fetched_at` | TEXT NOT NULL; UTC ISO-8601 with offset |
| `status` | TEXT NOT NULL; `ok`, `empty`, `rate_limited`, `error` |
| `items_returned`, `items_new` | INTEGER; what the vendor returned, how many were new versions |
| `error_class` | TEXT; exception class name only, no message |
| `vnstock_version` | TEXT; installed version string, NULL for RSS |

`company_feed_item` (one row per distinct item version):

| Column | Meaning |
|---|---|
| `id` | INTEGER PK AUTOINCREMENT |
| `fetch_id` | INTEGER NOT NULL, the fetch that first saw this version |
| `ticker`, `source`, `kind` | as above |
| `item_id` | TEXT NOT NULL; first 16 hex of the SHA-256 of the identity fields |
| `content_hash` | TEXT NOT NULL; SHA-256 (64 hex) of every stored field |
| `fetched_at` | TEXT NOT NULL; when this version was first seen |
| `published_at` | TEXT; the item's own date as the source gave it, ISO-8601, no timezone shifting; for RSS, UTC |
| `title` | TEXT; cleaned, original language; NULL only if the frame has no title column for that kind |
| `fields` | TEXT NOT NULL; JSON of the other stored scalar columns (events: `event_code`, `value_per_share`, `exercise_ratio`, the dates; RSS: the cleaned `snippet`) |
| | `UNIQUE (ticker, source, kind, item_id, content_hash)` |

Identity and versions. `item_id` hashes only what identifies the item (kind, ticker, source, the published date, the title, and for events the event code), so a field a vendor can revise later (a payout date announced after the ex-date) changes `content_hash` but not `item_id`: it arrives as a new version of the same item, never as a duplicate event. The exact identity columns per kind are fixed in the first apply task from a live frame; the spec states the rule, not the column names, because the events title column is not among the measured names. A row is inserted with `INSERT OR IGNORE`, so a second run, or two overlapping runs, change nothing.

`fetched_at` is when this log first saw an item, not when it was announced. Items in a ticker's and kind's first successful fetch are history; only later ones carry a real "known by" time. S2 must not treat the first fetch's items as known on their dates (look-ahead). The read helpers expose this (Decision 12).

Not stored, on purpose: the body (`news_full_content`), exception messages (vnai's rate-limit text is long and promotional), environment values, anything credential-shaped.

### 5. Text handling: reuse `_clean`, keep the language, cap, drop bodies

Every string that enters a row passes `news_feeds._clean(text, limit)`: entities decoded then markup stripped, whitespace collapsed, NFC-normalised, every Unicode control and format character removed (zero-width, bidi, the invisible "tag" block), then capped. This is the function the RSS headlines already go through, so company titles get the same treatment as the text `KNOWN_ISSUES.md` #1 worries about. The log is not a prompt, so the debate's 200-character prompt budget (`TITLE_MAX`, `news_feeds.py:58`) is not borrowed: titles are capped at 500 (`COMPANY_TITLE_MAX`) and other string fields at 200 (`COMPANY_FIELD_MAX`), both new and operational: a bound against a hostile oversized value, not a design target. RSS items come through `_fetch_feed`, which already applies `TITLE_MAX` and `SNIPPET_MAX` in `_parse_feed`; they are stored as that function returns them, i.e. as the News agent would have seen them.

"Stored as fetched" therefore means: not translated, not summarised, not re-worded; markup, control characters and length are the only changes. The cleaned form is the only form kept, so no later reader can pick up a raw string by mistake. Trade-off: if the cleaning ever proves lossy for a legitimate title, the original is gone; `content_hash` at least makes a changed frame visible. A column holding the body (`news_full_content`) is dropped; if the vendor starts filling it, a warning says so once per run and a bump decides what to do. Non-scalar cells are skipped and counted. NaN, NaT and numpy scalars become `null` and plain Python types, so `json.dumps(..., allow_nan=False)` (as `runner._merge` uses) cannot fail on events' NaN-filled string columns.

No model call, no translation, nothing displayed: when P2b shows these titles it must apply Rule 5 labels and the Rule 6 disclaimer, and any prompt that includes them must fence them (`prompt_safety.fence`).

### 6. The 50-item cap: accumulate, say when it bites, do not paginate

History is partial and cannot be completed through the public API; the log accumulates forward. A fetch that returns 50 items records that (`items_returned = 50` is the cap, a fact in the row). Two signals follow from the rows alone:

- First fetch of a ticker and kind with 50 returned: the visible history is a window, older items exist unseen. Expected, recorded, not an error.
- A later fetch of a ticker and kind that already has a successful fetch, returning 50 items of which all 50 are new: items were probably missed between runs. The script logs a WARNING (`possible gap`) and prints it in the summary. Derivable from the two columns plus the earlier fetch, so no column is needed.

Pagination (`page=` on the private `_fetch_news` and `_fetch_events`) is not used: it would bypass the wrapper the skill and the `tasks` rule in `openspec/config.yaml` point to, and the note says it was "not tried". If the gap warning shows real loss, a later change can ask for a sanctioned route. A failed write is self-healing within the window: the next run's frame still holds the items.

### 7. Rate limit (new constants, operational; Rule 3 does not apply)

- Pace below the guest limit. Default `--tickers-per-minute 8` = `DEFAULT_SYMBOLS_PER_MINUTE` (`bulk_ingestion.py:60`): two vendor requests a ticker is 16 a minute against 20, the same margin the ingestion run uses since vnai counts a wall-clock minute. RSS fetches are plain HTTP to three news sites and are not counted by vnai.
- Survive a hit. Per call: catch `SystemExit`; if `_is_rate_limit_exit` says it is vnai's limiter, wait `RATE_LIMIT_WAIT_SECONDS` (60 s) and retry that call, up to `MAX_RATE_LIMIT_WAITS` (5); after that record `rate_limited`, stop the run, list the tickers not attempted, exit non-zero. Any other `SystemExit` is re-raised, as in `ingest_symbol` and `macro._soft_fail`. Also catch `vnstock.core.exceptions.RateLimitError` (what `ticker_ingestion.py:13` catches) and treat it the same. `tenacity.RetryError` is unwrapped to its last exception first (the `Company` methods are wrapped in `@retry`), as `load_ticker` does.
- The project skill names `from vnstock.core.quota import RateLimitExceeded`. In 4.0.5 there is no `quota` module under `vnstock`; `RateLimitExceeded` exists only in `vnai/beam/quota.py` and surfaces as the `SystemExit` above. Nothing here imports it; a task records the discrepancy for the owner (the skill file is outside this change).
- RSS first, then tickers, so the time-critical, unmetered part is done if a rate limit stops the rest.
- No API key (decision 3). Nothing here sets, reads, stores or documents a key. The script checks only that `VNSTOCK_API_KEY` is unset and `~/.vnstock/api_key.json` is absent (existence only, never opened) and, if either is present, prints and logs a WARNING that vnai's key-gated paths, whose coverage by the guard is unverified, are in play. It does not refuse: a registered key is the owner's call, and refusing would block a legitimate setup. In the installed vnai a key also makes `Guardian._sync_to_backend` post the key, a device id and a usage count to the vendor's server, one more reason to leave it off. Reasoned from reading the installed source, not tested.

### 8. Failures: non-fatal, never silent (the `debate-outcome-log` pattern)

Per fetch, not per run. A fetch that raises, or returns a frame without the required columns, gets a `company_feed_fetch` row with `status = 'error'` and the exception class name, an ERROR log with the traceback naming ticker and kind, and the run continues with the next. A returned empty frame is `status = 'empty'`, which is a normal answer for a quiet ticker and is not an error; a non-empty frame lacking a required column is an error (`UnexpectedFrame`), so a vendor change after a bump cannot masquerade as "nothing found". If the insert itself fails, the failure is logged at ERROR with the traceback, counted, and the run continues (the items return in the next frame). The summary lists every failure; the exit code is 0 only when every fetch is `ok` or `empty` and every write succeeded, 1 otherwise, 2 for a usage error. The writer functions raise; `snapshot.py` is the caller that decides none of this stops the run, as `outcome_log.py`'s docstring describes for its caller. Unlike the debate log there is no response to carry a null id, so the visible signals are the exit code, the summary, the persisted `status` and the log.

### 9. RSS items are snapshotted too

Yes, recommended and included. The note's own premise: the feeds hold about four days and cannot be backfilled, and this clock is what lets a later change replay what the News agent could have seen. From `rss.py`, through the existing `_fetch_feed(client, url)` for each of `FEEDS` (bounded time, bounded size, `defusedxml`, redirect limit; no new HTTP code), stored as `kind = 'rss'`, `source` = the feed URL, `ticker = ''`, `published_at` in UTC, `title` and the cleaned `snippet` in `fields` (the snippet is kept because `_select` matches the symbol in it). Identity: kind, source, published date and title. One fetch row per feed; one feed failing does not stop the others, all three failing is three `error` rows and a non-zero exit. The items are not filtered by ticker or age: that is `_select`'s job and stays the News agent's. The News agent and `fetch_headlines` are untouched; this is a second reader of the same feeds, a few GETs a day.

### 10. Retention: keep everything, delete nothing

No pruning, no TTL, no delete code. Append-only, de-duplicated, small. Estimate, not measured: RSS at most about 130 items per four days is under 12,000 new rows a year; VCI adds a few items a week per ticker; at roughly half a kilobyte a row the file stays in single-digit megabytes a year, and `company_feed_fetch` adds about two rows per ticker per run. Because history cannot be re-fetched, the file is irreplaceable once it grows: `docs/KNOWN_ISSUES.md`'s backup note is extended to it (task), with the same `.backup` recipe taken for `debate_log.db`. It sits in `data/*.db*`, so the existing warning applies: never `rm data/*.db` or `git clean -x` blindly.

### 11. The pin, and how a bump is done

`backend/requirements.txt` gets `vnstock==4.0.5` and `vnai==2.5.5` (`vnai` is transitive and was unpinned; it is the component that wrote the injected files). A comment above them records the procedure. A bump is deliberate and is not done by `pip install -U`:
1. Change both pins together in a branch (`vnstock` requires `vnai>=2.5.2`; check the new metadata).
2. Build a fresh venv from `requirements.txt` and run `test_vnstock_guard.py`, including the sandboxed-`HOME` subprocess test, and the control without the guard (all seven files written) to prove the guard still bites, the way `KNOWN_ISSUES.md` task 0.2 did.
3. Read the new `vnai/beam/agents.py` and `vnstock/__init__.py` for any new write path the guard's `_WRITER_TARGETS` do not name.
4. Run `snapshot_company_feed.py --dry-run` on one ticker; the required-columns check turns a changed frame into an error.
5. Record the date, versions and result in `docs/KNOWN_ISSUES.md`.
It is not known whether 4.0.5 is the latest release (`pip index` could not list versions in this environment); the pin is to what is installed and tested. A test reads `requirements.txt` and fails if either line is not an exact `==` pin.

### 12. What the data layer lets P2b and S2 read

Two read functions in `store.py`, no endpoint, opened `mode=ro` through `open_readonly`: `latest_items(ticker, kind, since=None)` returns one row per `item_id` (its latest version), newest published first, each with `first_seen_at` and `from_first_fetch` (true when the item arrived in that ticker's first successful fetch, so a consumer can treat it as history); and `last_fetch(ticker, kind)` returns the latest fetch row and the time of the latest `ok` or `empty` one. A missing file reads as "never fetched", not an error. This is what lets a later coverage line tell "none found" (an `ok` or `empty` fetch, no item) from "not fetched" and "fetch failed", which the `DISCUSSION_calendar_staleness.md` question and P2b's "last item" dates both need.

### 13. Constants and which rule they implement

| Constant | Value | Rule |
|---|---|---|
| `COMPANY_TITLE_MAX` / `COMPANY_FIELD_MAX` | 500 / 200 characters | new, operational: bound on a hostile value; no domain rule |
| `VENDOR_ITEM_CAP` | 50 | the vendor's page size, measured 2026-10-09; not a choice |
| pacing | 8 tickers a minute | reuses `DEFAULT_SYMBOLS_PER_MINUTE`; operational |
| rate-limit wait / retries | 60 s / 5 | reuses `bulk_ingestion` constants; operational |
| retention | none | new |

None is a threshold on the size of a price move, so Rule 3 is not engaged; no score or label is defined. Rules 1, 2, 4, 5, 6 are not touched (proposal, Impact).

### 14. Coordination with P1 and S1

- **P1** edits the debate code, the `debate-*`, `macro-agent`, `news-agent`, `technical-agent` specs, `api/debate.py`, the runner and `openspec/config.yaml` context. This change edits none of those and its spec is a new capability, so no delta collides at archive. The names it imports are listed in Decision 2; P1 does not need to touch them, and a test here fails if anyone does. Textual overlap to watch: `backend/tests/conftest.py` (one added fixture), `docs/KNOWN_ISSUES.md` (different sections), both at apply time.
- **S1** may fetch the VN-Index through the vendor. Not shared: the vnai counter is per process. Unknown: whether VCI limits by address. Run S1's fetch and the snapshot one at a time. Both must install the guard first, which the repo test enforces.
- **P2b** reads through Decision 12, owns title-to-ticker matching and the display. **S2** reads events through the same functions and must respect `from_first_fetch`.

## Risks / Trade-offs

- [The clock only ticks when the script runs] -> the summary prints the age of the previous successful fetch and warns on a possible gap; a daily run after the close is recommended; a cron entry is the owner's choice.
- [RSS items missed beyond about four days] -> run at least every few days; unrecoverable by nature, which is why it is logged now.
- [History stays partial: 50 items per call, no paging] -> recorded per fetch (`items_returned`), gap warning, deferred paging (Decision 6). S2 can use history for a subset of tickers only.
- [A vendor frame changes] -> required-columns check turns it into an `error` row; the exact pin means it changes only on a deliberate bump.
- [Third-party text in a long-lived store] -> cleaned on the way in, inert (never rendered, never prompted in this change); fencing is required of any later consumer.
- [A `SystemExit` ends the process] -> handled per call in a script, which is why there is no hook; if P2b adds a server-side trigger it must keep the same guard.
- [Private-name imports from `news_feeds` and `bulk_ingestion`] -> a test imports each; the cost of a rename is a failing test, not a silent break.
- [Storing a copy of vendor titles] -> personal use only (decision 3); the file is gitignored and not to be shared; VCI's own terms were not found.
- [Requests carry the symbols the owner watches to the vendor] -> as ingestion already does; nothing else is sent. No key, no personal data.
- [The project vnstock skill is stale on the rate-limit exception path] -> not relied on here; recorded for the owner.

## Migration Plan

New file, new package, new script, two pins. `app.db` and `debate_log.db` are untouched; no migration. Apply: pin and verify the venv already matches (`pip freeze`), build the package behind tests that never touch the real files, one live `--dry-run` on one ticker to confirm the frame, then the first real run for the chosen tickers (this first run is the backfill of what the 50-item windows still hold). Back up `company_feed_log.db` with `sqlite3 ... ".backup ..."` after the first run and add it to `KNOWN_ISSUES.md`. Rollback: delete the script and package and revert the pins; keep the log file, since it cannot be rebuilt. Nothing user-visible changes, so there is no flag.

## Open Questions

- **Is the Unified UI call identical to the measured Legacy call?** Resolved 2026-10-09 (task 4.1, one live frame, SAB): yes. `Reference().company("SAB").news(source="vci")` and `.events(source="vci")` returned frames equal to `Company(source="vci", symbol="SAB").news()` and `.events()` (`DataFrame.equals` true, same columns, same dtypes, 50 rows each). `fetch.py` stays on the Unified UI.
- **Events identity and title columns.** Resolved (task 4.1): the events frame has a title, `event_title_vi` (Vietnamese; `event_title_en` is the vendor's own English variant and is not stored). The news frame's 21 columns are `id`, `news_id`, `language`, `news_category_code`, `icb_code`, `com_group_code`, `ticker`, `news_title`, `friendly_title`, `news_sub_title`, `friendly_sub_title`, `news_short_content`, `news_full_content`, `news_image_url`, `news_small_image_url`, `news_source`, `news_source_link`, `news_author`, `news_keyword`, `friendly_keyword`, `public_date`; the events frame's 22 are `id`, `event_name_vi`, `event_name_en`, `ticker`, `event_code`, `event_title_vi`, `event_title_en`, `display_date1`, `display_date2`, `public_date`, `record_date`, `exright_date`, `payout_date`, `value_per_share`, `exercise_ratio`, `category`, `issue_date`, `listing_date`, `start_date`, `end_date`, `action_type_vi`, `action_type_en`. Fixed in `normalise.py`: news requires `news_title` and `public_date`; events require `event_code`, `event_title_vi` and `public_date`; identity is kind, ticker, source, `public_date`, the title and, for events, `event_code`; the stored `fields` are the date, value and category columns listed in `EVENTS_SPEC` and `news_source`, `news_source_link`, `news_author` for news. The vendor's own `id` and `news_id` are not stored or hashed (the spec's identity rule does not name them, and an id the vendor regenerates would turn every run into a new version). In the 50 rows checked, `news_full_content`, `news_short_content`, `news_source`, `news_source_link` and `news_author` were all empty, `ticker` was empty in every news row, and `news_title` had 49 distinct values.
- **Date format of `public_date` and its timezone.** Resolved for the format, open for the timezone (task 4.1): `public_date` is ISO-8601 without an offset, `YYYY-MM-DDTHH:MM:SS` (a time of day for news, midnight for events); events also carry `record_date` and `exright_date` as `YYYY-MM-DD` and `payout_date` as `YYYY-MM-DDT00:00:00`. The timezone is not stated by the vendor (Vietnam local time is likely, not verified). Stored as given after ISO normalisation, nothing converted; P2b decides how to display it.
- **Paging past 50.** Deferred. Recommendation: do not, until gap warnings show real loss.
- **Who runs the script and how often.** Recommendation: the owner runs it daily after the close, or adds a cron line; this change ships no scheduler. The owner should know that until it runs the clock does not tick.
- **Which tickers.** Recommendation: `--from-debate-log` plus an explicit `--tickers` list; a broader basket belongs to P6. Not decided by the note.
- **Key detected: warn or refuse.** Recommendation: warn (Decision 7). Flagged because decision 3 says "no API key" and the script cannot prevent vnai from using one it finds.
- **Is accumulating a local copy of VCI titles within VCI's terms?** Decision 3 covers the library licence for personal use; VCI's own terms were not found. Not legal advice; ask whoever owns licensing before any work, paid or shared use.
