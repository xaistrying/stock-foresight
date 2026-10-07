## 1. Reproduce the numbers this change relies on (read-only)

- [x] 1.1 Write `backend/scripts/verify_data_eligibility.py` (database opened `mode=ro`) that prints: loaded tickers by `last_loaded_at` date; per-ticker `age_sessions` under design Decision 1 (histogram); the weekday non-sessions since 2025-06 from the stored calendar; counts per eligibility reason and tickers passing ignoring age (design Context: 313 of 599, delisted 194, near_gap 200, indicators_missing 88, hard_quality_flag 67, insufficient_history 9); the count of listed tickers missing 6 or more / at least 1 market session in their last 65; and the stored `near_gap` flip demonstration (rows 26 to 77 sessions after a holiday gap are `near_gap = 1`, e.g. ACB after 2026-02-23)
- [x] 1.2 Run it and record in the PR which review figures reproduced (596 of 599 loaded 2026-09-07; 199 latest rows `near_gap`; 49 tickers with a hard flag within 120 days) and which differ; amend design.md Context if a figure does not reproduce
- [x] 1.3 Confirm in a read-only check that a zero-close row inside the last 65 stored rows makes `predict_volatility_range` read an older row (design Decision 2, hard-flag window); if not, say so in design.md

## 2. Eligibility service (data-eligibility)

- [x] 2.1 Tests first in `backend/tests/test_data_eligibility.py` on a temp SQLite file with the real schema: one test per scenario of the data-eligibility spec (healthy; several reasons; no features row; delisted; missing universe row; 64 vs 65 priced sessions; zero closes; age 0 after a weekend; holiday inside the stored range; stale database not read as fresh; age 3 vs 4; holiday gap not a gap; 6 / 2 / 3 missing sessions; hard flag in and out of the 78 window; soft flag; indicators null / senkou_span_b null), with an injected `now`
- [x] 2.2 Implement `backend/app/services/data_eligibility.py`: `assess_eligibility(ticker, now=None)`, constants `MAX_AGE_SESSIONS = 3`, `MAX_MISSING_SESSIONS = 2`; import `MIN_SESSIONS` from `app.ml.volatility` and `HARD_FLAG_BLACKOUT_SESSIONS` from `app.ml.feature_engineering`; Vietnam time via a UTC+7 constant (move `ICT` from `news_feeds.py` to a shared place if the import direction is awkward); no import of `app.api.predictions`; one date-scan query for the calendar; add the `# ponytail:` note on the full scan
- [x] 2.3 Check on the real database (read-only) that a call takes under 0.3 s; if not, add the cache or index noted in design Decision 1

## 3. Degraded-agent model and engine (debate-engine, debate-synthesiser)

- [x] 3.1 Tests first for the synthesiser (spec delta also drops the superseded BUY/SELL sentence from the mapping requirement; no code in the verdict mapping changes) in `test_debate_agents.py`: three live (existing mapping, incl. two neutral + one directional → `OBSERVE` / `majority`), two live agree (bull, bear, neutral; never `STRONG_*`, never `unanimous`), two live disagree (`SPLIT`; bull+neutral is `SPLIT`), fewer than two live (`INSUFFICIENT_DATA` / `none`, no LLM call), degraded agent named in prompts, prose failure keeps the verdict
- [x] 3.2 Add `degraded_reason` to `AgentPosition`; add `INSUFFICIENT_DATA` to `Verdict` and `none` to `AgreementLevel`; add `data_as_of`, `data_age_sessions`, `agents_degraded`, `eligibility` to `DebateResult` (use the contract names `range_5s_pct` / `sigma_daily_pct` / `range_coverage` (null when uncalibrated) where `calibrate-volatility-range` has landed, otherwise keep the current range field and flag the merge)
- [x] 3.3 Implement the live-agent vote and abstention in `synthesiser.py` (skip both LLM calls on abstention; name degraded agents in the prompts)
- [x] 3.4 Tests first for the engine: Round 1 exception → `agent_error`, neutral placeholder, not voting; two degraded after Round 1 skips Round 2 and synthesis; Round 2 raise / blank / no stance line → `round2_failed`, Round 1 position kept and shown, not voting; LLM-down run → `INSUFFICIENT_DATA`; one degraded → two live agents vote; `as_of` is the eligibility date when Technical raises and when the system date differs. Replace `test_engine_one_agent_fails_debate_proceeds`, `test_engine_round2_failure_keeps_round1_stance` and `test_parse_stance_unrecognised_keeps_round1_stance_not_neutral`, which encode the old behaviour
- [x] 3.5 Implement in `engine.py`: take `as_of` and age from `assess_eligibility` (new optional argument; call it when absent), remove `_get_as_of` and the `tech._as_of` attribute (`technical.py:140`), run Round 2 only for live agents, treat failures per the spec, build `agents_degraded` in the fixed order
- [x] 3.6 `_parse_stance_and_bullets`: report whether a stance line was recognised; Round 2 callers treat "not recognised" as failure, News Round 1 treats it as `llm_failed`. Keep the existing format-tolerance tests passing
- [x] 3.7 Technical (`technical.py`): `run(ticker, as_of=None)` reads the features row of that date (add a by-date reader next to, not importing from, the predictions module); `no_input` when no indicator is available; fallback bullets state the computed values on LLM failure (test: stance `bull`, LLM raises → live agent with value bullets). Update the fakes in existing engine tests that take `(ticker)` only
- [x] 3.8 News (`news.py`): all feeds failed or no headlines → `no_input`; LLM raise or unrecognised stance → `llm_failed` with reasoning that names the LLM, not the feeds; tests replacing the "graceful" and "no headlines returns neutral" expectations
- [x] 3.9 Resolve the spec conflict: no code change for two neutral + one directional (already `OBSERVE`); confirm `test_map_verdict_two_neutral_one_bull` stays green; the owner approved this ruling (design, Resolved by the owner)

## 4. Endpoint (debate-engine)

- [x] 4.1 Tests first in `test_debate_export_api.py`: ineligible ticker → 200 `INSUFFICIENT_DATA` with all reasons, no LLM call (patch `LLMClient.chat` to fail the test if called), no macro or news fetch, no file written; 404 and 503 unchanged; eligible ticker returns the new fields; serialiser carries `degraded_reason`, `agents_degraded`, `eligibility`, `data_as_of`, `data_age_sessions`. Update the existing endpoint tests that monkeypatch `get_latest_features_row` to also patch `assess_eligibility`
- [x] 4.2 Implement in `api/debate.py`: call `assess_eligibility` after the 404/503 checks; return the abstention shape without constructing the engine; skip `export_debate_report` for `INSUFFICIENT_DATA`; extend `_serialise_result`

## 5. Macro agent (macro-agent)

- [x] 5.1 Confirm the real column name of the live `Market().index("VNINDEX").ohlcv()` frame (the test double uses `time`) with a single read-only call recorded in the PR; do not hand-roll a different vnstock call
- [x] 5.2 Tests first in `test_macro_signals.py`: relative return uses the same two dates (index shifted 3 sessions gives the by-date value, not the positional one); index missing an endpoint → no vote and the "not covered" reasoning; signal text carries both dates; no counted signal → `no_input`; provisional foreign flow alone → `no_input`; one counted signal stays live. Rework the tests that patch `_load_ohlcv_closes` to return bare Series
- [x] 5.3 Implement: `_load_ohlcv_closes` and `_market_closes` keep dates; signal 2 aligned by date; degrade on no counted signal
- [x] 5.4 Fix the stale comment at `macro.py:180-182` ("Provisional, like Rule 3's 0.5"): reword to say the ±10% threshold is provisional, set from judgement, not backtested and not covered by Rules 1–6 (comment only; Rule 3 is not what it implements)

## 6. Frontend (debate-panel-ui)

- [x] 6.1 Tests first in `DebatePanel.test.jsx`: data-date line (age 2 and current); one degraded agent (stance-row marker, "2 of 2 live agents (1 unavailable)", Level 2 reason, no "unanimous"); `round2_failed` card text; insufficient-data state for `stale`, several reasons, empty reasons with two degraded agents; disclaimer visible and no "Report saved" text in that state; "Market Sentiment" never appears (Rule 5 guard); Re-analyse present
- [x] 6.2 Implement in `DebatePanel.jsx` and `debate-panel.css`: data-date line, degraded markers (text and icon, not colour alone), live-agent agreement text, insufficient-data view with the reason-sentence map; leave verdict label strings and the `Agreement` word to `align-rules-and-disclaimer` (use whatever the display-label map holds for `INSUFFICIENT_DATA`; add a neutral fallback if that change has not landed). Disclaimer stays unconditional (Rule 6)

## 7. Export (debate-report-export)

- [x] 7.1 Tests first in `test_debate_export_api.py`: Data as of line; Unavailable agents line; live-agent Agreement text and the two-live split text; degraded cell reads `Unavailable`; no file for `INSUFFICIENT_DATA` and an earlier same-`as_of` report survives; filename from `as_of` with a different system date; disclaimer still last
- [x] 7.2 Implement in `export.py`: compute agreement over live agents, add the lines, skip abstentions, drop the `date.today()` fallback

## 8. Verification

- [x] 8.1 Run `pytest backend/tests` and `cd frontend && npm run test`; all pass
- [x] 8.2 With the real database read-only, run `assess_eligibility` over all 599 tickers and compare with task 1.1; spot-check SAB, VIB, VPB (current), a stale listed ticker (`stale` only), a delisted ticker, and one thin-trading ticker (`near_gap`)
- [x] 8.3 Manual end-to-end with the LLM provider stubbed to fail (no real calls): ineligible and degraded-run responses match the spec and the panel renders both states; confirm no report file was written for the abstention
- [x] 8.4 Known Limitation check: with the clock injected at the 5th weekday of a simulated 5-weekday closure (and the reopening Monday) and no stored session beyond it, `assess_eligibility` reports `stale` (documented behaviour, design Decision 1); the 4th weekday reads age 3 and a 3-weekday closure does not report `stale`. Update `docs/KNOWN_ISSUES.md` only if the owner asks (the stored `near_gap` holiday behaviour is a latent issue for `/prediction` and `/insight` until `retire-direction-model` removes them; record it in the PR otherwise)
