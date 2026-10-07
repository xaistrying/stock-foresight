# Known Issues / Backlog

Real, confirmed issues not yet scheduled into a milestone. Not a wishlist —
only add an item here once it's actually been reproduced, the same standard
M2/M3's design docs hold every other claim to.

---

## `_wilder_smooth` crashes on short OHLCV series

**Found**: M3, task 8.1, while running `pytest backend/tests`.

**Symptom**: `_wilder_smooth` in `backend/app/ml/feature_engineering.py`
raised `IndexError: iloc cannot enlarge its target object` when computing
RSI/ATR against a series shorter than the warm-up period (~15 rows for
period=14). Caught by `recompute_features_for_ticker`'s existing error
handling ("Feature recomputation failed for `<ticker>`") — didn't crash
the caller, but the ticker's `features` rows silently ended up empty.

**Likely trigger in practice**: a newly-listed ticker loaded with very
little trading history — plausible once M5's ticker panel lets users load
arbitrary tickers, including recent IPOs.

**Fix applied**: `_wilder_smooth` now guards `len(values) < period` and
returns an all-NaN `Float64` series (matching length/index) instead of
raising. This is option 1 of the three originally laid out below (null
just the affected column, row stays otherwise intact) — chosen because it
matches the module's existing `near_gap` philosophy: a too-short row is
unreliable regardless and already flagged as such, so a missing indicator
value is consistent with how the rest of the pipeline already treats it.

**Process note**: this was fixed and regression-tested inline, not via the
`/opsx:propose fix-short-series-feature-computation` route this entry
originally called for. The three-way trade-off (null column vs. refuse row
vs. minimum-row threshold) was real, but got resolved ad hoc mid-session
rather than through a formal design decision — worth knowing if the choice
ever needs revisiting, since it wasn't vetted the way M2/M3's other design
decisions were.

**Regression tests**: `test_wilder_smooth_returns_nan_series_when_too_short`
and `test_wilder_smooth_seed_at_exact_boundary_still_works` in
`backend/tests/test_feature_engineering.py`.

**Downstream follow-up** (`hose-universe-ingestion` task 5.4): the null
column this fix produces used to flow onwards unchecked — both
`filter_clean_labeled` and `GET /tickers/{ticker}/prediction` gated on
`near_gap` alone, which a short series does not necessarily set. Both now
require the indicator columns themselves to be non-null, so an all-NaN
indicator row is excluded from training and never serves a prediction,
whatever nulled it.

**Status**: fixed, closed.

---

## `vnstock` auto-writes prompt-injection content into AI-tool config files

**Found**: M3, while investigating why `backend/AGENTS.md` kept reappearing
after every `pytest backend/tests` run.

**Symptom**: `vnstock/__init__.py` (installed package, not this repo's code)
has an unconditional module-level call, `setup_agent(async_mode=True)`, that
fires on every `import vnstock` — including transitively, any time backend
code or tests import `app.services.ticker_ingestion` /
`app.ml.feature_engineering`. This calls into `vnai` (a mandatory dependency
of `vnstock`, pulled in automatically), which writes a file called
"Vnstock Vibe Onboarding" into:

- this project's `AGENTS.md` (both `backend/AGENTS.md` and repo-root
  `AGENTS.md` were seen)
- **six global, cross-project AI-tool config paths in the user's home
  directory**: `~/.clauderc`, `~/.cursorrules`, `~/.windsurfrules`,
  `~/.clinerules`, `~/.github/copilot-instructions.md`,
  `~/.gemini/config/AGENTS.md` — created from scratch if missing, or
  **appended to** if a file already exists there (confirmed via reading
  `vnai/beam/agents.py`'s `setup_agent_environment`).

The written content is addressed directly to AI coding assistants (not
human readers) and instructs them to: silently capture and persist an API
key typed into a prompt (to `~/.vnstock/api_key.json` or via
`setup_api_key(...)`), auto-install packages and create a shared
`~/.venv` without asking, and run agent-generated scripts without
confirmation. Separately, `vnstock/__init__.py`'s own module docstring
contains text aimed at AI assistants urging an unconditional switch to a
paid `vnstock_data` package and invoking an unreviewed
`migrate_to_sponsor()` function against the project root. Some `vnai` code
paths (`vnai/beam/agents.py`) also fetch "skill" content live from
`vnstocks.com/api/skills/...`, base64+XOR-obfuscated, gated on an API key —
so delivered content isn't fixed at install time.

**Confirmed real, not a one-off**: reproduced live — deleting
`backend/AGENTS.md`, then re-running `pytest backend/tests`, causes it to
reappear with a fresh timestamp, byte-identical to the original.

**Fix applied (local only)**: commented out the `setup_agent(async_mode=True)`
call at the bottom of the installed
`backend/.venv/lib/python3.14/site-packages/vnstock/__init__.py`. The
`setup_agent()` function itself is left intact (still callable explicitly);
only the automatic self-invocation on import is disabled. Verified: full
test suite still passes (34/34) and none of the six home-directory files
or either `AGENTS.md` regenerate after the patch.

**Limitation of that first patch (now superseded)**: it lived inside
`.venv`, which is gitignored and not shared between environments, so it was
**silently lost** on any reinstall or `vnstock` upgrade. That regression
actually happened: on **2026-08-11** all six home-directory files reappeared,
byte-identical at 3,641 bytes each, having been removed during the M3
investigation above.

**Durable fix landed** (`hose-universe-ingestion`, task 0.1): the `.venv`
edit is gone — the installed `vnstock/__init__.py` is back to upstream — and
the fix now lives in tracked source as `backend/app/vnstock_guard.py`. Its
`install()` replaces `vnai.beam.agents.setup_agent_environment` and
`async_setup_agent_environment` (and `vnai`'s re-exports of both, which is
the surface `vnstock.core.utils.agents.init_agent_environment` resolves at
call time) with a no-op that writes nothing and returns `False` — a value
vnstock's own wrapper already handles. `import vnai` itself has no
top-level side effects, so importing it to patch it is safe.

Every module in this repo that imports `vnstock` calls `install()` above that
import: `backend/app/services/ticker_universe.py`,
`backend/app/services/ticker_ingestion.py`, and
`backend/scripts/verify_vnstock_tier_limit.py`. For tests,
`backend/tests/conftest.py` installs it once per session — earlier than
`test_ticker_ingestion.py`'s own top-level vnstock import, which is what
originally triggered the writes during collection.

Why a guard module rather than the four options this entry previously listed
(post-install hook, `sitecustomize.py`, vendored fork, version pin): all four
are install-time, so all four can be skipped by a venv built any other way,
which is the exact failure mode that produced the 2026-08-11 regression. A
tracked module on the import path cannot be lost by rebuilding the venv.

**Chosen ordering caveat**: the guard only protects import paths that go
through it, so a *new* module importing `vnstock` without it would silently
reintroduce the writes.
`test_every_vnstock_importer_installs_the_guard_first` scans every non-test
Python file under `backend/` and fails if any imports `vnstock` without
importing `app.vnstock_guard` first, so that regression fails a test rather
than being noticed by `AGENTS.md` reappearing.

**Verified** (task 0.2), against a genuinely fresh venv built from
`backend/requirements.txt` with **unpatched** upstream `vnstock` 4.0.5 /
`vnai` 2.5.5:

- Control, guard *not* installed, `HOME` and cwd redirected into a sandbox:
  all seven files were written (project `AGENTS.md` plus the six home paths),
  confirming the fix is doing real work rather than testing an already-safe
  vendor.
- With the guard installed: none of the seven appear.
- `pytest backend/tests` in the fresh venv: **84 passed**, no `AGENTS.md`
  anywhere in the repo, no files in the sandboxed `HOME`.
- `pip install -r backend/requirements.txt` alone writes none of them —
  the writes require an `import vnstock`, not the install.

Regression tests: `backend/tests/test_vnstock_guard.py` (6 tests), including
an end-to-end subprocess check that imports the real installed `vnstock` and
calls `setup_agent(async_mode=False)` with `HOME` and cwd redirected into
`tmp_path`. The synchronous path is used deliberately: vnstock's import-time
call is a daemon thread that a short-lived process can exit before finishing,
which would make an async-only test pass for the wrong reason.

**Also removed this session** (already-injected files found across the
machine, not just this project): the six home-directory config files
above (all were pure `vnai`-generated content, 3160 bytes, nothing of the
user's own — safe to delete outright), plus both `AGENTS.md` copies in
this repo. Left untouched, deliberately: `~/.agents/skills/hallmark/`
(a real Claude Code skill), `~/AetherForecast/.agents/rules/` (a
different project's own real rules), and `~/vnstock-agent-guide/` (the
actual upstream repo this injection content originated from — legitimate
there).

**Status**: durably fixed in tracked source
(`backend/app/vnstock_guard.py`), verified against a fresh venv with
unpatched upstream `vnstock`, and covered by regression tests.

**Still open, deliberately not folded into the fix:**

1. **The six home-directory files re-injected on 2026-08-11 are still on
   disk** and still contain the prompt-injection content. They are outside
   this repo, in the user's global AI-tool config, so removing them is the
   user's call rather than something this change did unilaterally. All six
   are 3,641 bytes and byte-identical — pure `vnai`-generated content with
   nothing of the user's own appended, the same condition under which the M3
   investigation deleted them outright.
2. **Not reported upstream.** The guard makes this repo safe; it does nothing
   for anyone else installing `vnstock`.
3. **No version pin.** `backend/requirements.txt` still lists `vnstock`
   unpinned. The guard warns (rather than silently succeeding) if a future
   version renames or drops the writer functions it patches, but an upgrade
   that moves the write to a new code path would not be caught. A pin would
   bound that; it also freezes data-source fixes, so it is a trade-off worth
   deciding rather than assuming.

## Uncaught `tenacity.RetryError` for a well-formed ticker with no real data

**Found**: while designing M5's ticker-panel error states, testing
`load_ticker`'s exception handling.

**Symptom**: a well-formed ticker symbol (3-12 characters, passes vnstock's
format validation) that corresponds to no real data raised
`tenacity.RetryError`, not `ValueError` — `load_ticker`'s
`except ValueError` didn't see it, and the request crashed unhandled.

**Confirmed live**: `mkt.equity("ZZZ").ohlcv(...)` raises
`tenacity.RetryError`; `e.last_attempt.exception()` returns the real
underlying `ValueError("Không tìm thấy dữ liệu. Vui lòng kiểm tra lại mã
chứng khoán hoặc thời gian truy xuất.")`. Confirmed separately that a
malformed-symbol `ValueError` (the `invalid_symbol` case) is *not*
wrapped in `RetryError` — it still surfaces as a plain `ValueError`, so
the two cases remain distinguishable after unwrapping.

**Fix applied**: `load_ticker` now catches `(ValueError, RetryError)`
together; when the caught exception is `RetryError`, it unwraps via
`e.last_attempt.exception()` before passing to `_classify_load_error`,
otherwise it passes the exception through directly. `_classify_load_error`
gained a third match, `"Không tìm thấy dữ liệu"` → `status: "no_data"`,
alongside the existing `invalid_symbol` matches.

**Status**: fixed, closed, and now covered by a test —
`test_well_formed_ticker_with_no_data_reports_status_no_data` in
`backend/tests/test_ticker_ingestion.py`. (This entry previously said
"not yet covered"; that's no longer accurate as of this check.)

## Post-pivot review: five security and rule gaps in the debate surface

**Found**: the 2026-10-06 post-pivot review (`docs/DISCUSSION_post_pivot_review.md`),
recorded by `align-rules-and-disclaimer`. Each entry was confirmed by reading
the code on 2026-10-06 and re-checked against the tree on 2026-10-07. None was
exploited or reproduced against a live system. The owner has said the app is
for personal use, which sets the risk level; the entries are here so they are
fixed or accepted deliberately.

### 1. RSS headline text is untrusted input to LLM prompts

**Surface**: `backend/app/services/debate/news_feeds.py`, `news.py`, the
debate prompts, the panel and the exported reports.

**What exists today**: `_clean` strips markup and control characters and caps
titles at 200 and snippets at 160 characters (`TITLE_MAX`, `SNIPPET_MAX`,
`news_feeds.py:58-59`). The News prompt tells the model to ignore instructions
inside headlines (`news.py:50`).

**Not done**: headlines are not fenced as data in the prompt, and their text is
echoed into Round 2, the synthesis, the UI and the report, so an
instruction-shaped headline can steer the model and reach the user.

**Fix**: `harden-debate-runtime` (2026-10-07). Headlines go into the News prompt
inside a fence with every `<` and `>` replaced by a space, so they cannot close
it; the other agents' bullets (which can quote headlines) are fenced in every
Round 2 prompt and in both synthesiser prompts, and so is the News agent's own
Round 1 reasoning. Every prompt says to describe and not to recommend. Model
output is checked by a narrow pattern that replaces a recommendation-style
sentence with a visible placeholder (`prompt_safety.py`).

**Still true**: this is a backstop, not a classifier. Paraphrase, euphemism and
most Vietnamese phrasing pass the output check, a news item relaying a named
broker's call ("BSC recommends buying VCB") is withheld although it is
description, and a fence reduces injection risk without eliminating it.

**Status**: mitigated, not closed.

### 2. The `claude_cli` provider runs a subprocess with the prompt in argv

**Surface**: `backend/app/services/debate/llm_client.py` (`claude_cli`
provider, command built near `:134-158`) and `POST /tickers/{ticker}/debate`.

**What exists today**: the prompt is passed in argv, so it is visible in `ps`
on the machine (the code accepts this as market data). Tools are disabled
(`--tools ""`), user settings and MCP servers are skipped, the working
directory is an empty one, and each call times out after 120 s
(`CLAUDE_CLI_TIMEOUT_SECONDS`).

**Not done**: no retries after a timeout, and no cap on concurrent
`POST /debate` requests, so repeated requests start many subprocesses.

**Fix**: `harden-debate-runtime` (2026-10-07). Every call, for every provider, is
bounded by `DEBATE_LLM_CALL_TIMEOUT_SECONDS` (60 s; the hard-coded 120 s is gone),
a fast failure is retried once and a timeout is not, at most
`DEBATE_MAX_CONCURRENT_RUNS` (2) runs are in flight per process (one more is
HTTP 429), and requests for a ticker already running join that run. The OpenAI and
Anthropic SDK defaults (600 s read timeout, 2 retries; measured on openai 3.24.0
and anthropic 1.11.0) are replaced the same way.

**Still true**: the prompt is visible in `ps` while a call runs (accepted: it is
market data).

**Status**: fixed except the `ps` visibility; the limits are per process (below).

### 3. `pickle.load` of the HAR-RV model file

**Surface**: `backend/app/ml/volatility.py` at HEAD `e77986e` (`pickle.load`
at `:139`, on every call) and `backend/scripts/train_har_rv.py`.

**What existed**: `backend/data/models/har_rv_model.pkl` was gitignored,
written non-atomically, and had no hash or metadata. Anyone who could write
`backend/data/models/` could run code in the server when the file was loaded.

**Fix**: `calibrate-volatility-range` (archived 2026-10-07) stores the model
as `har_rv_model.json`, written atomically and loaded without pickle
(`volatility.py` needs numpy only). Re-checked 2026-10-07: no `pickle` import
remains in `volatility.py`.

**Status**: fixed once the change's commit lands; closed. (Kept as a record of
the review's finding.)

### 4. Ticker, indicator and headline data go to a third-party LLM provider

**Surface**: every debate run (`llm_client.py`).

**What exists today**: the ticker symbol, indicator values, the range, macro
numbers and up to 19 headlines are sent to the configured provider (OpenAI or
Anthropic API, or the user's Claude login through `claude_cli`). No holdings
or personal data are sent.

**Not done**: the vendors' retention and training terms were not reviewed. The
owner has said the app is for personal use; if it is ever shown beyond that,
confirm the wording and the data handling with whoever owns compliance.

**Status**: open; a data-handling note, not a code defect.

### 5. The Macro agent's fixed price-move thresholds do not meet Rule 3

**Surface**: `backend/app/services/debate/macro.py`: the trend helper (slope
beyond 0.05% of the series mean, `:67-69`) and the ticker-versus-VN-Index vote
(relative 20-session return beyond +/-1 point, near `:339`).

**What exists today**: both classify the size of a price move with fixed
numbers. Rule 3 as re-homed ("magnitude thresholds are volatility-relative")
does not cover them. The owner accepted this gap on 2026-10-07 rather than
narrowing the rule's text.

**Not done**: retrofitting volatility-relative thresholds; the effect of the
fixed thresholds on the Macro agent's votes has not been measured. The stale
comment "Rule 3's 0.5" in `macro.py` goes with it.

**Status**: open; owned by whoever next changes the Macro agent.

## `POST /tickers/{ticker}/debate` is unauthenticated and spends the owner's LLM budget

**Found**: applying `harden-debate-runtime` (2026-10-07); owner ruling: no
authentication for a personal localhost app. Reproduced, not assumed: the endpoint
test `test_known_issue_the_debate_endpoint_runs_for_any_caller_with_no_credentials`
(`backend/tests/test_debate_export_api.py`) sends a request with no credentials and
a foreign `Origin` header and gets HTTP 200 and one run.

**What exists today**: anyone who can reach the port can start debate runs, and each
run costs up to 8 LLM calls (an API bill, or the owner's Claude subscription usage
through `claude_cli`). The concurrency cap and the joining of same-ticker requests
guard against accidents (a double click, two tabs, a loop in a test script), not a
hostile caller. CORS restricts browsers only: it stops a page on another origin from
reading the answer, not from causing the run, and `curl` is not affected at all.

**What protects it**: `make up` starts uvicorn on its default `127.0.0.1`, and the
CORS allow-list names only the Vite dev origins. The limits are per process: with
`uvicorn --workers N` every worker would allow its own runs (the Makefile starts one).

**What would invalidate this**: binding to a non-loopback address, putting the app
behind a proxy or a tunnel, running several workers, or any use beyond the owner's
own machine. Add authentication and per-caller rate limits first.

**Not done**: authentication, per-caller limits, shared limits across workers,
server-side cancellation when a client disconnects (an abandoned request still runs
to its end and spends its calls).

**Status**: open; accepted for personal use.

## `backend/data/debate_log.db` is irreplaceable and sits among disposable files

**Found**: applying `debate-outcome-log` (2026-10-07). Not a defect: a hazard of the layout.

**What exists today**: the debate outcome log lives in `backend/data/debate_log.db`,
under `data/*.db`, which the repo treats as generated and reproducible (`app.db`
rebuilds by reloading tickers). The log does not: News and Macro read live data, so
a deleted row cannot be recreated, and the rows are the only record of what the
product said and what the price then did. There is no off-machine copy.

**What to do**: back it up by copying the file, or
`sqlite3 backend/data/debate_log.db ".dump" > debate_log.sql`. Never clean
`backend/data/*.db` blindly (a `rm data/*.db`, a `git clean -x`, a fresh clone's
rebuild script). Deleting `app.db` is safe for the log; deleting the log is not.

**Not done**: an automatic backup or export; it was out of scope.

**Status**: open; a standing caution, not a task.

---

## A long market closure (Tet) makes every ticker read stale

**Found**: `debate-data-guards` design Decision 1; recorded in
`backend/app/services/data_eligibility.py` (`_age_sessions`).

**Symptom**: `age_sessions` counts weekdays since the newest stored session.
During a multi-day closure such as Tet no ticker is refreshed with a new
session, so after 3 weekdays every ticker is "stale" and `/range` and the
debate return `INSUFFICIENT_DATA` until the market reopens and a refresh
stores the next session. Refreshing during the closure does not help.

**Status**: known limitation, accepted by the owner (2026-10-07). Not
reproduced against a real Tet closure yet.

**Upgrade path**: an extra-closures list consulted by `_age_sessions`, so
declared closure days do not count as missing sessions.
