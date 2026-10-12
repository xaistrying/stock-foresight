## Why

The debate runs eight language-model calls (three agents in Round 1, three in Round 2, two for synthesis) and shows the result as stance chips, a Key tension paragraph and a Synthesis paragraph. The 2026-10-08 SAB report showed what that buys: Round 2 is circular (Macro cites "the News agent's data supports this" and News cites Macro), Key tension and Synthesis restate a vote that had no stock-specific evidence behind it, and the Technical and Macro bullets are a model's paraphrase of numbers the code has already computed (each agent already has a plain values list as its fallback when the model fails). This is step 1 of `docs/DISCUSSION_describe_not_vote_redesign.md`: the owner chose a **pure removal** first, so that the later steps (readings cards, company filings, dropping the vote) start from a smaller, more honest surface, and so that the 9 rows already in the outcome log stay scoreable.

## What Changes

- **Remove Round 2.** Delete the agents' `respond` methods and their prompts, the engine's second `gather`, the `round2` key of `DebateResult` and of the `POST /tickers/{ticker}/debate` response, the `round2_failed` degraded reason and its note.
- **Remove Key tension and Synthesis.** Delete the two synthesiser model calls and their prompts, the `SynthesisResult` type and the `synthesis` key of the response; remove the Key tension block and its styles (the warn colour tokens stay defined, unused), the Synthesis paragraph and the "Comparing positions…" and "Synthesising…" progress labels from the panel; remove the Key Tension and Synthesis sections from new report files.
- **Technical and Macro reasoning become their existing values list.** Neither agent calls a language model any more: Technical's bullets are the computed indicator values (RSI, MACD histogram, Ichimoku Tenkan-sen and Kijun-sen) and Macro's are the four signal lines. The Technical bullets carry **no "Typical 5-session move" line** (the range block and the export Summary keep stating the band, as a percentage over 5 sessions).
- **The vote and Agreement stay, computed from Round 1 stances.** Same mapping, same degraded-agent rules, same display labels; only the input stance changes. Technical and Macro stances were always rule-computed; News's stance is still a model reading of the headlines (the one remaining model call).
- **The Debate matrix goes from 6 cards to 3** (one per agent, no round rows); below 768 px it stays a tablist of three agent tabs.
- **Provenance stays accurate.** After this change only the News Context bullets are language-model text, so the fixed sentence "Reasoning, key tension and synthesis are written by a language model." is replaced (panel and report, one string), and the one clause of `docs/DISCLAIMER.md` that says a model "revises their positions in a second round" is corrected in its three guarded copies (see design Decision 9).
- **Outcome log stays readable both ways.** The `r2_*` columns are kept and written as NULL for new rows (no migration); `outcome_log.py` and `score_debates.py` read old and new rows, and the verdict statistics are reported separately for rows voted on Round 2 stances and rows voted on Round 1 stances.
- **One stage, one model call.** The run has a single `round1` stage and one model call (News); the progress label, the run log line, the typical-duration notice and `scripts/measure_debate_runtime.py` follow.
- **Cleanups the owner decided to fold in.** Delete the dead `_get_sector_closes` in `macro.py`; fix the stale "existing insight endpoint" and `backend/app/api/insight.py` text in the `technical-agent` spec; edit `openspec/config.yaml` lines 6-10 ("two rounds", "vote over Round 2 stances") at apply time.
- **BREAKING (local API, one consumer):** `POST /tickers/{ticker}/debate` no longer returns `round2` or `synthesis`; `GET /tickers/{ticker}/debate/progress` only ever reports `round1`; the run log line drops `round2_ms` and `synthesis_ms`; `degraded_reason: "round2_failed"` no longer occurs. The only client is this repository's frontend, deployed together with the backend.
- **New report files change format; old files do not.** The nine files in `reports/` stay as written (nothing parses them, and "Existing report files are not backfilled" stands).

**Out of scope** (each is a later step in the discussion note, or a standing decision): VCI company news and events, fundamentals, Fibonacci levels, dropping the vote and Agreement, any edit to a domain rule, the parts headline (volatility percentile, catalysts list, market backdrop), a rule-written coverage table, and the by-year coverage disclosure. No new UI is added.

## Capabilities

### New Capabilities

None. This change removes behaviour and adjusts the text of existing requirements.

### Modified Capabilities

- `debate-engine`: remove the Round 2 requirement; `DebateResult` loses `round2` and `synthesis`; degraded reasons lose `round2_failed`; the vote reads Round 1; refusals return an empty `round1` only.
- `debate-synthesiser`: remove the key-tension, maintain-positions, abstain-without-a-call and neutral-prompt requirements; the two vote requirements read Round 1 stances (renamed so their titles carry no round number); add that the vote is deterministic and makes no model call; the verdict display label table is **kept unchanged** (only its cross-reference to the renamed requirement is retargeted).
- `debate-panel-ui`: remove the Key tension requirement; the result state, the matrix (three cards), the running-stage labels, the unavailable-agent reasons, the insufficient-data state, the language-model marking and the typical-duration notice are reworded.
- `debate-report-export`: new files have Summary, Agent Positions and Agent Reasoning sections (no Key Tension, Round or Synthesis); the language-model note names only News Context.
- `debate-runtime`: remove the concurrent-synthesiser and unusable-synthesis-text requirements; the progress stage, run log line, fencing, describe-only and withheld-wording requirements are narrowed to the prompt and bullets that remain (the News headline path).
- `debate-outcome-log`: `r2_*` are NULL for new rows; the report reads old and new rows; verdict statistics are reported per vote basis (new requirement).
- `technical-agent`: stale insight-endpoint text fixed; the range requirement keeps the range-service part and drops the prompt wording; reasoning is the computed values list.
- `macro-agent`: remove the model-translation requirement and add a values-list requirement; the foreign-flow and VN-Index-fallback requirements are reworded where they speak of the model.
- `news-agent`: the fencing requirement drops its Round 2 sentence.
- `dashboard-ui`: the layout-mode and contrast requirements drop Key tension and Synthesis.
- `volatility-range`: one scenario names `round1.technical` only.

## Impact

- **Backend:** `services/debate/engine.py`, `synthesiser.py`, `technical.py`, `macro.py`, `news.py`, `export.py`, `runner.py`, `outcome_log.py`, `prompt_safety.py` (docstring and, if unused, `DESCRIBE_ONLY`), `api/debate.py`, `scripts/score_debates.py`, `scripts/measure_debate_runtime.py`; the 10 backend test files listed in `tasks.md`.
- **Frontend:** `VerdictPanel/VerdictParts.jsx`, `PanelStates.jsx`, `DebateMatrix/DebateMatrix.jsx`, `AgentCard.jsx`, `lib/debateText.js`, `lib/disclaimer.js`, `hooks/useDebateProgress.js`, `api/tickers.js`, the drawer-strip rules in `App.css` and the Key tension rules in `verdict-panel.css`; the frontend tests and fixtures listed in `tasks.md`.
- **Docs and config (at apply time):** `docs/DISCLAIMER.md` (one clause), `docs/DATA_DICTIONARY.md` (the `r2_*` note), `README.md` (the "up to 8 LLM calls" and run-line passages), `docs/KNOWN_ISSUES.md` (one factual line; entries stay open), `openspec/config.yaml` (context lines 6-10).
- **Data:** `backend/data/debate_log.db` keeps its schema and its 9 rows (backed up on 2026-10-09 at `~/backups/stock-foresight/debate_log-2026-10-09.db`); no migration; `app.db` untouched. Nothing here writes to either.
- **Behaviour:** one model call per Analyse instead of eight. Verdicts before and after this change are voted on different inputs (Round 2 versus Round 1 stances) and are not comparable as one series.
- **Dependencies:** none added or changed.

## Domain rules

All six rules are honoured **unchanged**; none needs sign-off, and no rule text names Round 2, Key tension or Synthesis.

- **Rule 1 (5 trading sessions, scored against `outcome_t`):** touched through the `technical-agent` range requirement and the outcome-log reports. The band stays a 5-session band from the range service, and the log still scores bands and verdicts against the realised 5-session outcome.
- **Rule 2 (no raw log return in the UI):** touched through the same requirement. The band still shows as a percentage (range block, export Summary); removing the Technical band line removes a place it was stated, adds none, and the daily sigma stays out of the reports.
- **Rule 3 (volatility-relative thresholds):** not touched. No threshold is added or changed; Macro's existing fixed thresholds stay (`docs/KNOWN_ISSUES.md` #5, closed by a later step, not this one).
- **Rule 4 (reliability measured; Agreement):** touched. The vote keeps the label **Agreement** and its wording; the range hit-rate stays the only reliability figure; the band still states its nominal coverage.
- **Rule 5 (label by provenance):** touched. Agent labels (Technical Signal, News Context, Macro) are unchanged and "Market Sentiment" stays reserved for the technical proxy; the language-model marking shrinks to what is still model text, News Context's bullets.
- **Rule 6 (not advice; disclaimer):** touched. The disclaimer still shows wherever a verdict, Agreement, a range or agent reasoning shows (panel, matrix, report); verdict labels still come from the `debate-synthesiser` display label table, which this change keeps; the fixed-text guards for "buy", "sell" and "hold" are kept and cover the new fixed strings.
