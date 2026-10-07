## 1. Baseline (before any code change)

- [x] 1.1 Create `backend/scripts/measure_debate_runtime.py` (design Decision 13): stubbed `LLMClient.chat` with a configurable per-call sleep that records start/end and a stage tag per call, stubbed headline and market fetches, a stub volatility function that blocks 0.5 s, a background event-loop-lag probe; prints JSON with call count, per-stage durations, synthesis-stage max-vs-sum, max loop lag, and the installed `openai` / `anthropic` default timeout and `max_retries`. It uses only `DebateEngine().run(ticker)` so it runs on the unchanged tree. No real LLM, network or vnstock call. (debate-runtime: Independent synthesiser calls run concurrently; Blocking work does not run on the event loop)
- [x] 1.2 Run it on the unchanged tree (`e77986e` plus siblings that landed) and record the output in this file's section 8 notes: expect 8 calls, 4 sequential stages, synthesis stage about the sum of its two calls, loop lag about 0.5 s, SDK defaults 600 s / 2 retries. Anything that differs from the proposal's claims is written down here and design.md Context is corrected before continuing. (reproduces the review's call-count and stage-structure claims; the review's 41 s run and 2.8 s cold load are marked "reported, not reproduced")
- [x] 1.3 Create `backend/scripts/probe_advice_language.py` from the design Decision 9 probe: loads the pattern class from `prompt_safety` once it exists (until then an inline copy), runs it over `reports/*.md` bullets (skips if the directory is empty) and over the hand-written positive and negative sample lists; prints counts. Record the baseline "naive word hits 52, pattern hits 0 over 428 lines of 6 reports" if the reports are still the same. (debate-runtime: Recommendation-style wording is withheld)

## 2. LLM client: ceilings, retries, reuse, configuration

- [x] 2.1 Tests in `test_llm_client.py`: a hung fake `claude` is cut off at `DEBATE_LLM_CALL_TIMEOUT_SECONDS` with "timed out" and its process group is gone; a timeout is not retried; a fast non-zero exit is retried once and the second attempt's text returned; at most two attempts; no retry for a missing binary; two `chat` calls build the SDK client once (stub the SDK module); update the two existing tests that patch `CLAUDE_CLI_TIMEOUT_SECONDS` (`:285`, `:301`). (debate-runtime: Every LLM call has an explicit time ceiling; LLM retries are limited and deliberate; SDK clients are created once per process)
- [x] 2.2 Tests for `check_debate_config()` / `DebateConfigError`: invalid `DEBATE_LLM_EFFORT`, unknown provider, non-numeric or non-positive `DEBATE_MAX_TOKENS_PER_CALL`, `DEBATE_LLM_CALL_TIMEOUT_SECONDS`, `DEBATE_RUN_TIMEOUT_SECONDS`, `DEBATE_MAX_CONCURRENT_RUNS`, `DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS`; missing `OPENAI_API_KEY`; missing `claude` on PATH; the message names the variable and never contains a (fake) key value set in the test; `LLMClient()` with a bad value raises `DebateConfigError`. (debate-runtime: Invalid LLM configuration is reported before a run starts)
- [x] 2.3 Implement in `llm_client.py`: `DEBATE_LLM_CALL_TIMEOUT_SECONDS` (default 60) enforced with `asyncio.timeout` around `chat` for all providers; `LLMCallTimeout(RuntimeError)`; remove the hard-coded `CLAUDE_CLI_TIMEOUT_SECONDS` (keep a module constant for the default); per-attempt `httpx.Timeout(call_timeout, connect=5.0)` and `max_retries=1` for the SDK clients; one 1 s retry for fast non-timeout `claude_cli` failures; WARNING log per retry and final failure (provider, attempt, elapsed; no prompt, no credentials). (debate-runtime: ceiling; retries)
- [x] 2.4 Implement cached SDK clients (one per provider and settings) and `close_llm_clients()`; call it from `lifespan` shutdown (after `yield`) in `app/main.py`, leaving the XGBoost load lines to `retire-direction-model`. (debate-runtime: SDK clients are created once per process)
- [x] 2.5 Implement `DebateConfigError(ValueError)` and `check_debate_config()` per design Decision 5 (presence checks only, names not values); make `LLMClient.__init__` raise `DebateConfigError`. (debate-runtime: Invalid LLM configuration)

## 3. Runner: de-duplication, cap, budget, progress, logging

- [x] 3.1 Tests for a new `runner` (stubbed engine): two requests for one ticker start one run and both get the same result; the same error is shared; the third distinct ticker over the cap is rejected immediately with `DebateBusy` (no engine call); joiners do not count against the cap; a slot is freed after success, failure and timeout; an abandoned (cancelled) caller does not cancel the run and the run's export still happens; a run past `DEBATE_RUN_TIMEOUT_SECONDS` raises `DebateTimeout` and is removed from the registry. (debate-runtime: Concurrent requests for one ticker share a single run; cap; A run does not depend on the requesting connection; A debate run has a time budget)
- [x] 3.1a Tests for post-run hooks: called once for three joined requests with `joined == 3`; called after the export with the same `report_file` as the response; called in registration order; a raising hook logs ERROR, later hooks still run, response unchanged (HTTP 200, `report_saved` unchanged); a hook's returned dict is merged into the response for every joined request (one hook call); a colliding key (for example `verdict`, `report_saved`, or a key from an earlier hook) is refused with an ERROR and the existing value kept; a non-dict or non-JSON-safe return is ignored with an ERROR; a failed or timed-out hook adds no fields; a hook past `DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS` is abandoned and logged; not called for a timed-out or failed run; the slot is held until hooks finish; the run log line reports `hook_failures`; the ERROR record contains no result text. (debate-runtime: Post-run hooks run once per run)
- [x] 3.2 Tests for the stage log line: one INFO line per run with `round1_ms`, `round2_ms`, `synthesis_ms`, `total_ms`, provider, model, status ("ok" / "timeout" / "error"); the line contains no prompt text or credential. (debate-runtime: Each run logs its stage durations)
- [x] 3.3 Add the optional `on_stage` callback to `DebateEngine.run` (`engine.py:83`), called with `round1`, `round2`, `synthesis`. Do not add fields to `DebateResult`.
- [x] 3.4 Create `app/services/debate/runner.py`: registry (`ticker -> Task` plus stage and start time), join via `asyncio.shield`, cap check and insert with no `await` between them, `asyncio.timeout(DEBATE_RUN_TIMEOUT_SECONDS)` inside the task, export inside the task via `asyncio.to_thread` returning `(result, report_file | None)`, stage log line, the `RunContext` dataclass and `register_post_run_hook` per design Decision 14 (a hook may return a dict of extra JSON-safe fields merged once per run into the serialised result, no overwriting of existing keys; hooks run after the export, before release, once per run, each bounded by `DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS`, failures logged at ERROR and counted in the log line), and a `ponytail:` comment on the per-process ceiling. Retrieve a finished task's exception so no "never retrieved" warning is logged. (debate-runtime: sections above)
- [x] 3.5 Endpoint tests in `test_debate_export_api.py` (stubbed runner or engine): 429 with `Retry-After` and `code` "debate_busy"; 504 with `code` "debate_timeout"; 503 with `code` "debate_not_configured" and no run started; 404 / 503 ticker checks still come first; response carries `report_saved` and `report_file` (true / name on success, false / null when the export raises, HTTP 200); `GET /tickers/{ticker}/debate/progress` while running, when idle, and for an unknown ticker (HTTP 200, `running` false). (debate-runtime: Run progress is reported; The response states whether the report was saved)
- [x] 3.6 Rework `app/api/debate.py`: ticker checks (in `asyncio.to_thread`), `check_debate_config()` mapped to 503 with a string `detail` plus `code`, `runner` call mapped to 429 / 504, `report_saved` / `report_file` merged into the serialised result, and the progress route. Merge with `debate-data-guards` and `calibrate-volatility-range` changes to `_serialise_result` rather than overwriting them.

## 4. Latency, prompts and output checks

- [x] 4.1 Tests for `prompt_safety`: `fence` removes `<` and `>` and the end marker appears once for a hostile input; `withhold_advice` withholds every positive sample (including "We advise investors to sell", "Investors should consider selling", "Buy the dip", "Nên mua cổ phiếu này") and keeps every negative sample (including "the small magnitude suggests the selling pressure is mild", "A sell-off in large caps weighed on the index", "Selling by foreigners dominates the session", "Buy-side demand rose", "Áp lực chốt lời gia tăng"); a test that runs it over `reports/*.md` when present and expects zero withheld bullets. (debate-runtime: Recommendation-style wording is withheld; Untrusted text is fenced)
- [x] 4.2 Tests for prompts: News Round 1 headlines inside the fence only, hostile headline cannot close it, existing untrusted / do-not-recommend wording kept; Technical, News and Macro Round 2 prompts fence the other agents' bullets; Technical and Macro Round 1 prompts carry the describe-only line; synthesiser prompts contain stance counts and not the verdict enum name (parametrise over all six values). (news-agent: News Agent prompts fence headlines as untrusted data; debate-runtime: Prompts ask for description, not recommendation)
- [x] 4.3 Tests for the engine seam and synthesiser: a withheld Round 1 bullet appears as the placeholder in the Round 2 prompt and the stance is unchanged; blank, short and refusal replies give `key_tension` None; a failed call gives None, never "Unable to generate key tension analysis."; the summary falls back to the deterministic verdict line on the same tests; the two synthesiser calls overlap in time (each stub sleeps 0.3 s, stage under 0.5 s); one failing call leaves the other intact. (debate-runtime: Unusable synthesis text is reported as unavailable; Independent synthesiser calls run concurrently)
- [x] 4.4 Implement `app/services/debate/prompt_safety.py` (`fence`, `DESCRIBE_ONLY`, `withhold_advice`, placeholder constant) with the pattern class from design Decision 9, and apply it: fences and `DESCRIBE_ONLY` in the prompts listed in design Decision 8 (`technical.py`, `macro.py`, `news.py`, `synthesiser.py`); `withhold_advice` on every returned position in `_safe_run` (`engine.py:138`) and on synthesis text.
- [x] 4.5 Synthesiser (`synthesiser.py`): `asyncio.gather` the two calls (`:115-118`); stance-count text in the prompts; usable-text check (blank, under 20 characters, refusal opening) giving `key_tension = None` and the existing deterministic summary fallback; make `SynthesisResult.key_tension` `str | None`; serialise it. Coordinate field types with `debate-data-guards`.
- [x] 4.6 Move blocking calls to `asyncio.to_thread`: Technical feature-row read and volatility call (`technical.py:110,119`, whatever function `calibrate-volatility-range` leaves there), Macro ticker closes (`macro.py:302`), News sector lookup (`news.py:72`). (debate-runtime: Blocking work does not run on the event loop)
- [x] 4.7 Export (`export.py`): print "Key tension unavailable: the synthesiser returned no usable text." when `key_tension` is None; test it. Do not touch label or disclaimer strings (`align-rules-and-disclaimer`). (debate-runtime: Unusable synthesis text)

## 5. Frontend: client and hooks

- [x] 5.1 Tests in `api/tickers.test.js` / a new `api/client.test.js`: `request` forwards an `AbortSignal`; a timeout abort becomes an `ApiError` with `timedOut` true (not the network-error text); a 429 / 503 / 504 body keeps `status` and `body.code`; `runDebateAnalysis` passes a signal with the configurable limit (default 200 000 ms; tests pass a short one). Guard `AbortSignal.timeout` for environments without it. (debate-panel-ui: stops waiting after a client time limit)
- [x] 5.2 Implement `client.js` signal support and the `timedOut` flag; `tickers.js`: `runDebateAnalysis(ticker, { signal })` and `getDebateProgress(ticker)`.
- [x] 5.3 Tests for `useDebateAnalysis` (keyed by ticker, result stored per ticker in the query cache with completion time, pending state and start time readable per ticker after a remount, a ticker switch does not abort) and `useDebateProgress` (polls every 2 s only while enabled, keeps the last value on error). (debate-panel-ui: keeps the last result per ticker; shows the running stage)
- [x] 5.4 Implement `hooks/useDebateAnalysis.js` (mutation key `['debate', ticker]`, `onSuccess` stores `['debate-result', ticker]` with `gcTime: Infinity`) and `hooks/useDebateProgress.js`.

## 6. Frontend: DebatePanel

- [x] 6.1 Rewrite the `DebatePanel.test.jsx` mocks for the new hook shapes and add tests with fake timers: stage label follows the progress value and elapsed seconds advance; a poll failure keeps the label; kept result for another ticker survives a switch and shows "Analysed HH:MM"; a failed re-run keeps the old result with the error above it; each of 404, 429 `debate_busy`, 503 `debate_not_configured` (server message shown), 504 `debate_timeout`, client `timedOut`, and a generic failure with `detail`; the disclaimer is visible in the running state and in every failure state; "Report saved" appears only when `report_saved` is true and uses `report_file`; a null `key_tension` shows "Key tension unavailable"; "Market Sentiment" never appears. (debate-panel-ui: all added requirements; Rule 6 disclaimer)
- [x] 6.2 Implement in `DebatePanel.jsx`: remove `mutation.reset()` during render (`:153`), the dead `startTime` state and the "4-8s" comment (`:163-164`); staged running state with elapsed time; kept-result display with its time; error mapping; conditional report line (`:123`); unavailable key-tension text. Keep the disclaimer element unconditional.
- [x] 6.3 `App.jsx`: render `<DebatePanel key={selectedTicker} ticker={selectedTicker} />`; adjust `App.test.jsx` only where it depends on the old hook shape.

## 7. Docs

- [x] 7.1 README: document `DEBATE_LLM_CALL_TIMEOUT_SECONDS`, `DEBATE_RUN_TIMEOUT_SECONDS`, `DEBATE_MAX_CONCURRENT_RUNS`; state that the per-stage log line is in `.run/backend.log` under `make up`; keep "about 45-50 s on `claude_cli`" labelled as one measurement, and state that API-provider latency is not measured until a run log exists.
- [x] 7.2 `docs/KNOWN_ISSUES.md`: add the entry from design Decision 12 (unauthenticated `/debate` spends the owner's LLM budget; protection assumes a loopback bind; limits are per process; CORS is browser-only). Reproduced-issue standard of that file: cite the measured unauthenticated 200 from task 8.1's endpoint test.

## 8. Verification

- [x] 8.1 Backend suite passes (`pytest backend/tests`), including the new runner, prompt-safety, configuration and endpoint tests; frontend suite passes (`cd frontend && npm run test`).
- [x] 8.2 Re-run `backend/scripts/measure_debate_runtime.py` and `probe_advice_language.py` on the changed tree and record before / after in this section: calls still 8; synthesis stage about one call's time instead of two; max event-loop lag under 100 ms with the 0.5 s blocking stub; N same-ticker requests produce one run's calls; surplus distinct tickers rejected; zero withheld bullets over the exported reports. Keep both scripts under `backend/scripts/`.
- [x] 8.3 Manual check with the owner's provider, once: run one Analyse, confirm the stage label changes and the elapsed time counts, switch ticker mid-run and back, break `DEBATE_LLM_EFFORT` to see the 503 message, and read the run log line. Add the measured stage durations to README (replacing "not measured") and note them against the 60 s / 180 s defaults. This task needs the owner's LLM access and is the only one that does.
- [x] 8.4 Confirm no credential value appears in any log line, response body or test output produced by sections 2-3 (grep the test logs for the fake key used in 2.2).

## Notes (measurements; recorded at apply time)

### 1.2 Baseline on the unchanged tree (2026-10-07; `e77986e` plus the three siblings that landed)

`backend/scripts/measure_debate_runtime.py` (stubs only; 0.3 s per LLM call, 0.5 s per blocking read):

| Claim | Result |
|---|---|
| 8 LLM calls | **8** (3 + 3 + 2) |
| 4 sequential stages | **confirmed**: Round 1, Round 2, then the two synthesiser calls one after the other |
| Synthesis stage about the sum of its two calls | **confirmed**: wall 0.601 s, sum of calls 0.601 s, longest call 0.301 s |
| Loop lag about 0.5 s | **differs: 0.993 s.** The blocking reads of different agents run back to back with no `await` between them, so the stalls add up (two 0.5 s reads gave a 1.0 s gap). The 0.5 s figure assumed one blocking call. |
| Volatility call blocks the loop | **differs: it does not.** It is already in `asyncio.to_thread` (`calibrate-volatility-range`); the stub for it changes nothing. The blocking calls are the feature-row read, Macro's closes and News's sector lookup (design Context corrected). |
| SDK defaults 600 s / 2 retries | **confirmed** on openai 3.24.0 and anthropic 1.11.0 (`Timeout(connect=5.0, read=600, ...)`, `max_retries=2`) |
| README's 41 s run, review's 2.8 s cold model load | **reported, not reproduced** (stubs cannot measure them) |

### 1.3 Advice-wording probe baseline

`backend/scripts/probe_advice_language.py`, run over `reports/*.md` (8 reports now, so the review's "52 hits over 428 lines of 6 reports" is not reproducible as stated): **naive word hits 77, pattern hits 0 over 262 model-text lines of 8 reports**; 14/14 positive samples flagged, 0/14 negative samples flagged.

### 8.2 After (changed tree, same stubs: 0.3 s per LLM call, 0.5 s per blocking read)

`backend/scripts/measure_debate_runtime.py` (now also measures the runner) and `probe_advice_language.py`:

| Measure | Before (task 1.2) | After |
|---|---|---|
| LLM calls per run | 8 | **8** (unchanged) |
| Synthesis stage, wall time | 0.601 s (= the sum of its two calls) | **0.301 s** (about one call; the sum of the two is still 0.602 s) |
| Whole run | 2.709 s | **1.908 s** |
| Largest event-loop gap | 0.993 s | **0.009 s** (limit 100 ms) |
| 5 concurrent requests, one ticker | no runner: 5 runs | **8 calls, 1 shared result** |
| 4 distinct tickers, cap 2 | no runner: 4 runs | **2 rejected** (`DebateBusy`), 16 calls = 2 runs x 8, none for a rejected one |
| Advice-wording probe over `reports/` | 0 hits | **0 hits**, 14/14 positives, 0/14 negatives (the pattern now comes from `prompt_safety`) |

The SDK defaults the old tree relied on (600 s read timeout, 2 retries) are replaced by `DEBATE_LLM_CALL_TIMEOUT_SECONDS` and `max_retries=1` (asserted by `test_llm_client.py`).

### 8.1 and 8.4

- Backend `pytest backend/tests`: **925 passed** (718 before this change; after the review fixes). Frontend `npm run test`: **263 passed** (17 files).
- 8.4: the whole backend run was captured with `-rA -s` and DEBUG logging (7,735 lines) and searched for each fake secret value the tests use (the one in `test_llm_client.py`, the placeholder in `conftest.py`, the wrong-provider one in the endpoint test): **0 occurrences** of any of them. `test_a_missing_credential_is_named_and_its_value_is_not_in_the_response` and the `check_debate_config` tests assert it per message.

### 8.3 Partly done (2026-10-07, owner's `claude_cli` / sonnet)

Measured from `.run/backend.log`: `Debate run ticker=SAB provider=claude_cli model=sonnet status=ok round1_ms=8381 round2_ms=8526 synthesis_ms=7189 total_ms=24100 joined=1 hook_failures=0` (synthesis took one call's time; README updated). The owner confirmed the stage label moves Running agents… → Comparing positions… → Synthesising… in the panel. Not yet confirmed by hand: the ticker switch mid-run and back, and the `DEBATE_LLM_EFFORT` error shown in the panel (the 503 itself was checked over HTTP, below). Task left unticked until those two are seen.

Earlier note, before the owner's run:

Left unticked. What was checked instead, against the real server over HTTP (`uvicorn` on a spare port, `DEBATE_LLM_PROVIDER=claude_cli DEBATE_LLM_EFFORT=turbo`, no LLM involved): `POST /tickers/TCB/debate` answered **503** with `{"detail": "Unknown DEBATE_LLM_EFFORT 'turbo'. Supported: low, medium, high, xhigh, max.", "code": "debate_not_configured"}` and the CORS header for the Vite origin (so the panel can read `code`); `GET .../debate/progress` answered 200 `running: false` for a loaded and for an unknown ticker; an unknown ticker on POST was 404 (ticker check first); shutdown was clean (`close_llm_clients` runs in the lifespan). Still to do by hand with a real provider: one Analyse (stage label changes, elapsed counts), a ticker switch mid-run and back, and reading the `Debate run ticker=...` line in `.run/backend.log`; then replace "not measured" in the README with the measured stage durations.
