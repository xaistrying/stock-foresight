## Context

Source: `docs/DISCUSSION_describe_not_vote_redesign.md`, sections "Settled for step 1 (2026-10-09)" (owner answers, inventory, constraints), "Decided 2026-10-09" and "Proposal breakdown". This is change P1 of that breakdown; P2a (company feed) and S1 (a read-only study) run beside it and P2b, P3, P4 and P7 wait for it to be applied.

How a run works today (read on 2026-10-09):

- `DebateEngine.run` (`engine.py:123`) runs the three agents in parallel (Round 1), then, only when at least two agents are live (`engine.py:165`), runs each live agent's `respond` (Round 2; with fewer live agents `round2` is a copy of `round1`), then `Synthesiser.run`, which takes the vote over the Round 2 stances and, unless it abstains, makes two more model calls (key tension and summary). `agents_degraded` is read from `round2` (`engine.py:200`). `_safe_run` (`engine.py:209`) catches an agent's exception, and applies `withhold_advice` to every position's bullets (`engine.py:225`).
- Model calls: Technical (prose only), News (its stance and bullets), Macro (prose only), the same three again in Round 2, and two in synthesis: 8. Technical and Macro **stances** are rule-computed (`technical.py:34`, `macro.py:298`); their model calls only write bullets, and each agent already has a values list it returns when that call fails (`technical.py:290`, `macro.py:451`). News's Round 1 call produces its stance and is the only call that has to stay.
- The runner has three stages (`STAGES`, `runner.py:51`), a log line with `round1_ms`, `round2_ms`, `synthesis_ms` and `total_ms`, and a progress endpoint that reports the stage.
- The outcome log writes `r1_*` and `r2_*` in one loop (`outcome_log.py:127`); `score_debates.py` reports verdict hit-rates over all analysed rows and per-agent hit-rates for rounds 1 and 2.
- The panel's Debate matrix is 3 agents by 2 rounds (6 cards); the Verdict panel shows badge, Agreement, stance chips (from `round2`), Key tension (the only user of the warn colours), Synthesis, data line and the report-saved line.

Constraints, all from the note: the owner chose pure removal; the vote and Agreement stay on screen, computed from Round 1, until step 3; no domain rule changes; keep the `r2_*` log columns and write NULL for new rows; keep the News-path safety tests; no new UI. The 9 rows in `backend/data/debate_log.db` (backed up on 2026-10-09) become scoreable around 2026-10-12 and must stay readable.

## Goals / Non-Goals

**Goals:**

- One model call per run (News's), no Round 2, no Key tension, no Synthesis, in the engine, the API, the panel, the report and the specs.
- Technical and Macro reasoning are plain computed values, with no band line in Technical's bullets.
- The vote, Agreement and the verdict labels behave as before, computed from Round 1 stances.
- Provenance stays accurate: only text a model wrote is marked as model text, and the disclaimer says what is still true.
- Old log rows and old report files keep working; new rows and files are valid under the new shape.

**Non-Goals:** VCI news and events, fundamentals, Fibonacci levels, dropping the vote or Agreement, any rule edit, the parts headline, a coverage table, the by-year coverage disclosure, any new UI element, any change to the model-call time ceiling, the run budget or the retry policy, and renaming `round1`, `STAGES` or the `debate-*` capabilities (P2b and P3 reshape those).

## Decisions

### 1. The response drops `round2` and the whole `synthesis` object (open choice 1 of the note)

`POST /tickers/{ticker}/debate` stops returning `round2` and `synthesis`. `verdict` and `agreement_level` already sit at the top level, so `synthesis` has nothing left that is not a duplicate. `DebateResult` loses `round2` and `synthesis`, and `SynthesisResult` is deleted (11 callers in the code index, all in the engine, synthesiser and tests).

*Alternative: keep the keys, empty, "for compatibility".* Rejected: the only client is this repository's frontend, deployed with the backend, so compatibility protects nobody; empty keys would also invite later code to read them, and the panel's "Key tension unavailable" branch exists only to handle a null that can no longer occur. A reviewer comparing old and new payloads sees an honest shape change instead of a hidden one.

`round1` keeps its name. "Round 1" is now just the one pass of the agents; renaming it would touch the log's `r1_*` meaning, the frontend fixtures and the volatility-range spec for no product gain, and P2b/P3 will restructure the payload anyway.

### 2. One `round1` stage; the progress endpoint stays (open choice 2)

`STAGES = ("round1",)`, and the engine calls `on_stage("round1")` once. The panel shows "Running agents…" for the whole run (it already shows that label for `round1` and falls back to it for an unknown stage, so a stale server cannot break it). `STAGE_LABELS` loses `round2` and `synthesis`. The run log line becomes `... status=ok round1_ms=… total_ms=… joined=1 hook_failures=0`; `RunContext.stage_ms` holds `round1` and `total`.

*Alternative A: rename the stage to `agents`.* Rejected for the reason in Decision 1. *Alternative B: remove the progress endpoint and the polling hook, since one stage carries no information.* Rejected for step 1: it deletes API surface and a hook (a spec requirement, `useDebateProgress`, its tests and the client's `getDebateProgress`) beyond "pure removal", and the endpoint's fate depends on P2a/P2b, which may add sources and stages, and on P3, which leaves no model call. The poll is cheap (one request per 2 s while a run is going). It is recorded as an Open Question so P3 decides it deliberately.

The run budget (`DEBATE_RUN_TIMEOUT_SECONDS` 180, client limit 200 s) and the 60 s per-call ceiling are unchanged: one call, retried at most once, cannot approach 180 s, and lowering the budget is a tuning change that needs measurements, not a removal. The note's "MODIFY the time budget" is read as the typical-duration notice and the stage timings, which do change (Decision 8).

### 3. The engine and the agents lose their model calls except News's

- `TechnicalAgent.run` returns the stance, the three range fields and `evidence` as before, with `reasoning` = the values list (`_VALUE_LABELS`, e.g. `RSI: 41.4`, `MACD histogram: -0.0652`, `Ichimoku Tenkan-sen: 43.08`, `Ichimoku Kijun-sen: 43.97`). It no longer constructs an `LLMClient`, builds `_REASONING_PROMPT`, or reads `_range_line`; its fetch of the range service (`_fetch_range`) stays, because the three range fields still ride on the position.
- `MacroAgent.run` returns the stance, `evidence` and `reasoning` = its four signal lines (VN-Index trend, relative performance, USD/VND, market foreign flow, each with its provisional or final label as the signal text already carries). The post-hoc append of `window_note` (`macro.py:393`) can never fire any more, because the values list already contains the note inside "Relative performance: unavailable (…)"; it is removed with its test condition checked by the task list.
- `respond` is deleted from all three agents, with the Round 2 prompts and `ROUND2_UNAVAILABLE_NOTE`. `NewsAgent.run` is unchanged and keeps `_parse_stance_and_bullets` (used only by News after this change).
- `DegradedReason` becomes `agent_error | no_input | llm_failed`. Technical and Macro can no longer fail through a model, so only `agent_error` and `no_input` apply to them; `llm_failed` stays News's.
- `agents_degraded` is read from `round1`. `_safe_run` loses its `fallback` branch; it keeps applying `withhold_advice` to every position's bullets (a no-op for the computed lines, and the News bullets still pass through it).
- `Synthesiser` is reduced to the deterministic vote. The class and its `LLMClient` go; `_map_verdict` and `_vote` stay as a pure function of the live stances, called by the engine. The module and the capability keep the names `synthesiser` and `debate-synthesiser`: the verdict display label table lives in that capability and `openspec/config.yaml`'s `tasks` rule points at it, and P3 removes the vote (and this module) entirely.

*Alternative: keep Technical and Macro model calls but drop Round 2 only.* Rejected by the owner's scope ("Technical and Macro reasoning become the values list that already exists as their fallback").

### 4. The Technical bullets carry no band line (decided item 1)

The range service still supplies `range_5s_pct`, `sigma_daily_pct` and `range_coverage`, and `AgentPosition` keeps them. They show where they showed before: the range block (`RangeBlock.jsx`, from `GET /range`) and the export Summary line (`export.py:175`), as a percentage over 5 sessions with its nominal coverage (Rules 1, 2 and 4, unchanged). The bullets simply do not repeat them, so the daily sigma figure leaves the reports until P7 (the export already never prints it, per "Export Summary states the typical 5-session move and its coverage").

### 5. Report format: new files change, old files stay (open choice 3)

The new report is `# TICKER · DATE`, `## Summary` (unchanged lines), `## Agent Positions` (the language-model sentence, then the table), `## Agent Reasoning` (one `### <label> (<stance or Unavailable>)` block per agent with its bullets, degraded agents marked not counted as today), `---` and the disclaimer. Key Tension, Round 1/Round 2 headings and Synthesis are gone. The Agent Positions table keeps its current rule, the first bullet in the "Key reasoning" cell; for Technical and Macro that is now one value ("RSI: 41.4"), which is thin, and is accepted because the full list sits in the next section and P2b replaces this table with the rule-written coverage table.

There is no format marker and no migration. The 9 existing files in `reports/` keep the old structure; a same-day re-run overwrites with the new structure (the existing "re-analysis replaces" rule). Nothing parses report files: `score_debates.py` only lists their names to cross-check the log, and the real-reports test (`test_the_real_exported_reports_have_no_withheld_bullet`) reads every non-heading, non-`**` line, so it covers both structures; the new fixed sentence is plain text that does not match the recommendation pattern.

*Alternative: keep the old section names with new content (for example "Full Debate" holding one round).* Rejected: "Debate", "Round 1" and "Synthesis" would then label things that no longer exist, in a document NotebookLM is asked questions about.

### 6. Outcome log: `r2_*` NULL; scoring reads both; verdict statistics split by vote basis

- **Write:** the `r2_*` columns stay in the table (no migration, per the note: a new column would need one). `build_row` writes `r1_*` only and the `INSERT` omits the `r2_*` columns, so they are NULL (the columns are nullable `TEXT`, `debate_log.py:32-34`). `agents_degraded` is the Round 1 list, `evidence` is unchanged (it was always Round 1).
- **Read:** `score_debates.py` scores `r5`, `inside_band` and `direction_hit` from `verdict` and `range_5s_pct`, which both kinds of row have, so scoring is unchanged. `stance_lean("r2_*")` already returns no lean for NULL, so the per-agent Round 2 tables simply count the older rows.
- **Pooled verdict statistics must split** (note: "must split on `code_rev`"). Verdicts before and after this change are voted on different inputs, so the report prints the directional verdict rates and "verdict minus technical-only" once per **vote basis**: rows whose `r2_*` stances are present (voted on Round 2) and rows whose `r2_*` are NULL (voted on Round 1). Each group states its n and the `code_rev` values it contains. Coverage at the band (`inside_band`) does not depend on the vote and stays pooled; per-agent Round 1 tables stay pooled (the Technical and Macro stances and News's Round 1 call are unchanged); per-agent Round 2 tables only ever contain older rows.
- **Why the basis is read from `r2_*` and not from `code_rev` alone:** `code_rev` is a short git hash with a `+dirty` suffix, or NULL when git fails. It is provenance, not an ordered boundary, so "before or after this change" cannot be decided from it without knowing which commit landed this change. Inside the analysed population every agent is live, so an older row has all three `r2_*` stances and a newer one has none: the test is exact and needs no commit lookup. The `code_rev` values per group are still printed, which satisfies the intent of the note's constraint and lets a reader check the split against the history. *Alternative: group by exact `code_rev`.* Rejected: one group per commit, most with a handful of rows, and no pooled figure at all.
- The "basis" labels are report-only text, new, and covered by no domain rule; they name an input, not a quality.

The funnel (`population`) is unchanged. The 9 existing rows are all Round 2 basis and become scoreable around 2026-10-12 exactly as before.

### 7. Panel and matrix

- The result state shows, in order: badge, Agreement, stance chips (from `round1`), data line, "Analysed HH:MM", the report-saved line, Re-analyse. `agreementText` and the insufficient-data reasons read `round1`.
- The Debate matrix is one row of three cards (Technical Signal, News Context, Macro), same card, same five-line clamp, same Unavailable card (reason text without `round2_failed`), same three-tab form below 768 px (one card per panel). Row labels, the `ROUNDS` constant and the six skeleton cells become three. The prompt reads "Run Analyse to see each agent's position." (replacing the sentence that names Rounds 1 and 2).
- In `drawer` mode the strip loses its third column: the range block stays at the left, the verdict with Agreement and the chips at the right, and the foot (data line, report line, disclaimer) on a full-width row. This is the minimum change that removes a deleted component from the layout; no new element is added. The phone order drops the two paragraphs. The exact column ratio is a visual choice made at apply time (the layout was not seen running in this planning session).
- The warn colours were used only by Key tension (`verdict-panel.css`). With the block gone, the Key tension rules in `verdict-panel.css` are deleted. The three warn tokens **stay** in `tokens.css`, and so do their two pairs in `scripts/check-contrast.mjs` and `contrast.test.js`: `tokens.test.js` pins that file to the approved design's `tokens.json` (version 10) and the contrast test records that design's lowest text pair (4.80:1, the warn label), so whether the design keeps a warn colour is a design-system call, not part of this removal. Only the two stale descriptions ("Key tension body text", "Key tension label") change. The tokens are unused, which the contrast requirement now says in words and a test asserts (no component stylesheet refers to `--warn-`). *Alternative: delete the tokens, their pin and their pairs.* Rejected for step 1: it edits the owner-approved token set and the recorded contrast figures for a purely cosmetic gain; P2b, which draws new cards, is the natural place to decide it.

### 8. Time notice

"Analysis takes about 45 seconds." is a fixed sentence from `TYPICAL_ANALYSIS_SECONDS`. With one call it overstates the run (the README's own 2026-10-07 measurement had Round 1 alone at 8.4 s on `claude_cli`). The requirement stops naming a number: it says the number comes from the one named constant, which is set from a measured typical run of the current agent set. The measurement is an apply-time task (a few real runs on the owner's provider, the median rounded up to a convenient figure); the design does not invent it. See Open Question 1.

### 9. Provenance and disclaimer (Rules 5 and 6)

- **The language-model sentence** (panel `LM_NOTE` in `frontend/src/lib/disclaimer.js` and `LM_NOTE` in `export.py`, one string by the existing "same string the panel shows" rule) becomes: `News Context reasoning is written by a language model; Technical Signal and Macro reasoning are computed values.` It is shown above the Debate matrix's cards (panel) and as the first line under `## Agent Positions` (report). It is no longer shown in the Verdict panel, which now holds no model text. Rule 5: it implements "mark language-model text as such"; it names the three agents by their existing labels. *Alternative: a per-card tag on News Context.* Rejected for step 1 as new UI; P2b's cards can carry it.
- **The disclaimer's full text** (`docs/DISCLAIMER.md`, `frontend/src/lib/disclaimer.js` `FULL_DISCLAIMER`, `export.py` `DISCLAIMER_FULL`) says "A language model writes the agents' reasoning and revises their positions in a second round, so wording and positions can be wrong or incomplete." After this change that is false twice (a model no longer revises, and writes only News's reasoning). This is not in the note's inventory; it is found here and handled as a **text correction, not a rule edit**: Rule 6 requires the disclaimer to show and to match the file, and says nothing of this clause. The proposed replacement of that one sentence is: `A language model reads the news headlines and writes the News Context agent's reasoning and position; the other two agents report computed values. Wording and positions can be wrong or incomplete.` All three copies are edited together, as the file's own header instructs, and the existing drift tests (`disclaimer.test.js`, `test_the_exporters_copy_equals_the_source_file`) pass only when they agree. The inline version ("Technical observation from automated agents and a statistical range — not investment advice.") stays true and is unchanged. The owner decided on 2026-10-09 that this wording needs no sign-off (personal use; Open Question 2 is resolved), so it is applied as proposed; the disclaimer is shown wherever a verdict, Agreement, a range or reasoning shows, as today.

### 10. Safety tests stay on the News path

The News Round 1 headline fence, injection and "untrusted, do not recommend" tests, the `fence` unit tests, the `withhold_advice` sample, sentence, logging and real-reports tests, and the engine-seam withholding tests keep running. Only tests whose subject is a removed prompt are deleted (Round 2 prompts, the Technical and Macro Round 1 describe-only prompts, both synthesiser prompts). The test that a withheld Round 1 bullet is a placeholder "in Round 2 and the synthesis" is rewritten, not deleted: the placeholder reaches the response and the report, and the stance is unchanged. `DESCRIBE_ONLY` is kept if the News prompt (or anything else) still uses it, and removed with its test only if nothing does.

### 11. Cleanups and docs

`_get_sector_closes` (`macro.py:174`) is deleted; `get_connection` stays imported because `_load_ohlcv_closes` uses it (`macro.py:43`). The `technical-agent` spec's "existing insight endpoint" and `backend/app/api/insight.py` references are replaced (the file does not exist; `backend/app/api/` holds `debate.py`, `range.py`, `tickers.py`). `openspec/config.yaml` lines 6-10 are edited at apply time (project context, not a rule; `CLAUDE.md` does not repeat it). Its stale "Current focus" list waits for P3's config edit, as decided.

### Domain-rule mapping of the labels and strings this change defines

| Item | Rule | Note |
| --- | --- | --- |
| Language-model sentence (panel and report) | 5 | Replaces the old sentence; marks only News Context. |
| Agent labels Technical Signal, News Context, Macro | 5 | Unchanged. |
| Verdict labels | 6 | From the kept `debate-synthesiser` table, unchanged. |
| "Agreement: …" wording | 4 | Unchanged; counts live agents, never "Confidence". |
| Typical 5-session move line and range block | 1, 2, 4 | Unchanged except the Technical bullets no longer repeat it. |
| Disclaimer clause | 6 | Wording corrected for accuracy; the requirement to show it is unchanged. |
| "Vote basis" group names in `score_debates.py` | none | New, report-only, names an input; not covered by Rules 1-6. |
| Typical-duration number | none | New, set from a measurement; not a threshold or score. |
| Thresholds | 3 | None added or changed (Macro's fixed thresholds are `KNOWN_ISSUES.md` #5, deferred). |

### Backlog folded in or deferred (per `CLAUDE.md` and `openspec/config.yaml`)

- `KNOWN_ISSUES.md` #1 (RSS text in prompts), #2 (`claude_cli` subprocess), #4 (data to a third-party model) and the unauthenticated debate endpoint: **reduced** (one call, News's, instead of eight; only the headline prompt carries third-party text) and **not closed**; the entries stay open until a step leaves no model call. One factual line is added to #1 (Round 2 and synthesis prompts no longer exist).
- `KNOWN_ISSUES.md` #5 (Macro fixed thresholds): untouched; closed by a later step. The debate-log hazard (irreplaceable file): this change only adds NULL-valued writes; the 2026-10-09 backup stands.
- `DISCUSSION_calendar_staleness.md` (the Fresh/Stale dot): not touched. `DISCUSSION_prediction_outcome_tracking.md`: options 2 and 3 are kept working; option 4 and a nightly basket stay deferred.
- Archived open questions (prompt language, board-settle time, `[ticker]` aliases, the rolling foreign-flow window): deferred as in the note. `/insight` and the feature flag: `/insight` is retired (`ticker-prediction`) and `VITE_DEBATE_PANEL_ENABLED` does not appear in `frontend/src` (checked 2026-10-09; `dashboard-ui` already says the panels render with no flag), so this looks done and is not reopened. Apply confirms with one `grep` and writes nothing.

## Risks / Trade-offs

- **The vote now rests on one model-derived stance.** Technical and Macro were always rule-computed in Round 1, and Round 2 could revise them with a model; News alone depends on a model. Verdict agreement may therefore shift even for the same data. → Accepted by the owner ("interim state accepted"); the log's vote-basis split keeps the two series apart; no claim is made that the verdicts are comparable.
- **Round 2 could previously mask a bad Round 1 stance.** Removing it removes that (circular) check. → The SAB evidence shows the check was not independent; nothing else is lost.
- **The thin "Key reasoning" cell** for Technical and Macro in the report table. → Full lists are in `## Agent Reasoning`; P2b replaces the table.
- **A stale browser tab or an old server** during the one-deploy switch reads `round2` that no longer exists. → The panel reads `round1` only and shows "Running agents…" for any stage; the apply deploys backend and frontend together (local app).
- **Disclaimer wording is a legal-adjacent text.** → The change is a factual correction to one sentence, guarded by the drift tests, and the owner decided on 2026-10-09 that it needs no sign-off (personal use); nothing in the rules is edited.
- **Drawer-strip layout was not seen running.** → A manual check at 900 px and 1144 px is a task; the CSS-text tests assert the new grid.
- **Deleting tests with the prompts they covered** could drop coverage of something still live. → The task list names which tests are deleted, which are rewritten and which must stay, and the News-path tests are explicitly kept.
- **Two other changes sit nearby.** P2a (`add-company-feed-news-and-events`) adds a new package and its own log file, pins `vnstock` and `vnai`, and imports private names from `services/debate/news_feeds.py` (`_clean`, `_fetch_feed`, `FEEDS`, `HEADERS`, `TIMEOUT`, `MAX_REDIRECTS`) and from `services/bulk_ingestion.py`; S1 (`evaluate-band-coverage-by-market-regime`) adds a read-only script that re-implements the vendor index call and imports nothing from `macro.py`. → This change edits neither `news_feeds.py` nor `bulk_ingestion.py` and leaves `_get_vnindex_closes` and `_market_closes` in `macro.py` untouched. No delta spec collides: P2a and S1 each add a new capability and modify none. The only textual overlap is in files edited at apply time, `docs/KNOWN_ISSUES.md` and `docs/DATA_DICTIONARY.md` (different sections), and `backend/tests/conftest.py` is P2a's alone.

## Migration Plan

1. Back up is already taken (`~/backups/stock-foresight/debate_log-2026-10-09.db`); re-check it exists before applying, and do not delete or rewrite any row of `debate_log.db`.
2. Apply backend and frontend together on one branch; there is no data migration and no schema change.
3. After deploy: run one Analyse on an eligible ticker and confirm the response has `round1` and no `round2`/`synthesis`, the new log row has `r2_*` NULL, the report has the new sections, and `score_debates.py --dry-run` prints both vote bases without error.
4. Rollback: revert the commit. Rows written meanwhile have NULL `r2_*`, which the old `score_debates.py` already handles (NULL stances are not scored), so no repair is needed.
5. Archive this change before P2b is applied (the breakdown's sequencing).

## Open Questions

1. **The typical-duration number.** Recommendation: measure a few real runs on the owner's provider at apply time, set `TYPICAL_ANALYSIS_SECONDS` to the median rounded up, and update the one test that names it. Until measured, 45 s overstates. Alternative if the owner prefers no number: reword to "Analysis takes a few seconds." and drop the constant; not recommended because the requirement wants one named, testable source.
2. **The corrected disclaimer sentence** (Decision 9). Resolved 2026-10-09: the owner said the disclaimer is not important (personal use), so the wording proposed there is applied as a one-sentence text correction with no sign-off step.
3. **The progress endpoint with a single stage.** Recommendation: keep it in step 1 (Decision 2) and decide its removal in P3, when no model call remains. Nothing here blocks that.
4. **Whether the Technical and Macro table cells should join all their bullets.** Recommendation: no; keep the first-bullet rule and let P2b's coverage table replace it.
