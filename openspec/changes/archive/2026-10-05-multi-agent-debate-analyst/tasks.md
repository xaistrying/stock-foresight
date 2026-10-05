## 1. Backend foundation — debate package scaffold

- [x] 1.1 Create `backend/app/services/debate/` package with `__init__.py`, `engine.py`, `technical.py`, `news.py`, `macro.py`, `synthesiser.py`, `export.py`, `llm_client.py`
- [x] 1.2 Add `httpx` and `openai` to `backend/requirements.txt`; verify existing venv install does not break
- [x] 1.3 Implement `LLMClient` in `llm_client.py` — reads `DEBATE_LLM_PROVIDER` (default `openai`) and `DEBATE_LLM_MODEL` (default `gpt-4o-mini`) from environment; wraps async chat completion for both `openai` and `anthropic` providers
- [x] 1.4 Define shared data models in `engine.py`: `AgentPosition(agent_id, stance, reasoning, volatility_range_pct)` and `DebateResult(ticker, as_of, verdict, agreement_level, round1, round2, synthesis, volatility_range_pct, duration_ms)`
- [x] 1.5 Create `reports/` directory at repo root; add `.gitkeep`; add `reports/*.md` to `.gitignore` (reports are user-local, not committed)

## 2. HAR-RV volatility model

- [x] 2.1 Implement `backend/app/ml/volatility.py` — HAR-RV linear model using 5-session, 20-session, 60-session trailing close-to-close volatility as features; target is 5-session forward realized volatility (Rule 1: 5 trading sessions)
- [x] 2.2 Write `backend/scripts/train_har_rv.py` — trains the linear model on existing OHLCV data, serialises to `backend/data/models/har_rv_model.pkl`; run once to produce the artifact
- [x] 2.3 Run `python backend/scripts/train_har_rv.py` and verify `har_rv_model.pkl` is produced; check in-sample correlation ≥ 0.40 (Finding 5 baseline)
- [x] 2.4 Add `predict_volatility_range(ticker: str) -> float | None` to `volatility.py` — loads the model, fetches the ticker's last 60 OHLCV sessions, returns `volatility_range_pct` (positive float, ±%) or `None` if < 60 sessions; output is percentage, never raw log (Rule 2)
- [x] 2.5 Write unit tests for `volatility.py`: (a) correct output type and sign for a known OHLCV fixture, (b) returns `None` for < 60 rows, (c) no raw log return exposed

## 3. Technical Agent

- [x] 3.1 Implement `technical.py` — `TechnicalAgent.run(ticker)` reads the latest feature row (reuses `get_latest_features_row` from `predictions.py`), computes stance via RSI/MACD/Ichimoku majority vote (same logic as existing `_compute_sentiment` in `insight.py`)
- [x] 3.2 Extend `TechnicalAgent.run` to call `predict_volatility_range(ticker)` and include `volatility_range_pct` in `AgentPosition`
- [x] 3.3 Construct LLM prompt with computed indicator values; parse LLM response into `reasoning` list of 3–5 bullets; verify each bullet references a specific value
- [x] 3.4 Handle NULL indicators gracefully: stance `neutral`, reasoning `["Indicator data unavailable for this session"]`
- [x] 3.5 Write unit tests: (a) bull/bear/neutral stance from known feature row values, (b) NULL indicators → neutral, (c) `volatility_range_pct` present in returned `AgentPosition`

## 4. News Agent

- [x] 4.1 Implement `news_feeds.py` — async `fetch_headlines(ticker, sector)` using `httpx.AsyncClient`; reads the VnExpress, CafeF and Vietstock RSS feeds (parsed with `defusedxml`); returns headline strings from the last 7 calendar days, tagged `[ticker]` / `[sector]` / `[market]` and capped (revised 2026-10: v1 scraped the sites' search pages, which stopped working — see 13.1)
- [x] 4.2 Implement ticker→sector mapping: read `icb_code2` from the universe table for the ticker; map the ICB supersector code (18 codes, `0500` … `9500`) to a sector label whose Vietnamese keywords tag `[sector]` headlines (revised 2026-10: the original code map did not match the codes the universe table holds)
- [x] 4.3 Implement `NewsAgent.run(ticker)` — calls `fetch_headlines`, passes headlines to LLM with a structured prompt instructing signal extraction from provided text only; parse LLM response into `{ stance, reasoning }`
- [x] 4.4 Implement graceful degradation: if `fetch_headlines` raises any exception, return `AgentPosition(stance="neutral", reasoning=["News data unavailable — could not fetch the news feeds."])`; `fetch_headlines` raises only when every feed fails (one failing feed is logged and skipped)
- [x] 4.5 Enforce label: `agent_id = "news"` in `AgentPosition`; UI and export use "News Context" for this agent_id
- [x] 4.6 Write unit tests with mocked `httpx` responses: (a) successful headline fetch returns non-empty list, (b) one failing feed is skipped and all feeds failing → graceful neutral position, (c) empty headline list → neutral with "No recent news found" reasoning

## 5. Macro Agent

- [x] 5.1 Implement `macro.py` — `MacroAgent.run(ticker)` fetches four signals: VN-Index 20-session slope, the ticker's own 20-session return relative to VN-Index (no sector index exists), USD/VND 5-session change, market-wide foreign net value for the latest session (VCI price board, 30 large caps)
- [x] 5.2 Implement VN-Index fallback: check `ohlcv` table for `VNINDEX` rows; if absent, fetch via vnstock market API (use vnstock skill wrapper, do not hand-roll)
- [x] 5.3 Map each signal to a partial stance vote; compute overall stance via majority (4 votes)
- [x] 5.4 Pass computed numeric signals to LLM for translation into 3–4 readable reasoning bullets; LLM MUST NOT add macro context beyond the provided numbers
- [x] 5.5 Write unit tests: (a) four bullish signals → bull stance, (b) VNINDEX absent from DB → fetches via API (mocked), (c) VN-Index API also fails → omitted from vote, remaining 3 signals used

## 6. Debate engine and synthesiser

- [x] 6.1 Implement `engine.py` — `DebateEngine.run(ticker)`: Round 1 runs `TechnicalAgent`, `NewsAgent`, `MacroAgent` concurrently via `asyncio.gather`; collects three `AgentPosition` objects
- [x] 6.2 Implement Round 2 in `engine.py`: construct per-agent response prompt (agent's own R1 + other two agents' R1 positions); run three response calls concurrently; collect updated `AgentPosition` objects
- [x] 6.3 Implement `synthesiser.py` — `Synthesiser.run(round1_positions, round2_positions)`: apply verdict/agreement_level mapping from design.md Decision 2; call LLM to produce `key_tension` paragraph; return `SynthesisResult`
- [x] 6.4 Ensure Round 2 prompt explicitly instructs agents to maintain position unless a specific counter-argument is compelling (design.md Decision 9 / synthesiser spec requirement)
- [x] 6.5 Assemble final `DebateResult` from all sub-results; include `duration_ms` (wall clock for the full run)
- [x] 6.6 Write unit tests for `engine.py`: (a) all three agents successful → `DebateResult` with all fields, (b) one agent raises exception → neutral fallback, debate proceeds, (c) `agreement_level` correct for unanimous/majority/split inputs
- [x] 6.7 Write unit tests for `synthesiser.py`: all six verdict mappings (STRONG_BUY_SIGNAL through STRONG_CAUTION_SIGNAL and SPLIT)

## 7. Debate API endpoint

- [x] 7.1 Implement `backend/app/api/debate.py` — `POST /tickers/{ticker}/debate` router; calls `DebateEngine.run(ticker)`; returns `DebateResult` as JSON
- [x] 7.2 Add 404 guard: if `get_features_computed(ticker) == 0` or `get_latest_features_row(ticker) is None` → HTTP 404
- [x] 7.3 Register debate router in `backend/app/main.py`
- [x] 7.4 Write integration tests for the debate endpoint: (a) 404 for unloaded ticker, (b) 200 with valid `DebateResult` shape for a loaded ticker (mock LLM calls to avoid real API costs in CI), (c) response includes `verdict`, `agreement_level`, `round1`, `round2`, `synthesis`

## 8. Export service

- [x] 8.1 Implement `export.py` — `export_debate_report(result: DebateResult) -> Path`: serialises a `DebateResult` to the markdown schema defined in design.md Decision 10; writes to `reports/YYYY-MM-DD_<TICKER>.md` at repo root
- [x] 8.2 Ensure the disclaimer line ends every exported file unconditionally (Rule 6)
- [x] 8.3 Ensure agent labels in the export: TechnicalAgent → "Technical Signal", NewsAgent → "News Context", MacroAgent → "Macro" (Rule 5)
- [x] 8.4 Call `export_debate_report` from the debate endpoint after `DebateEngine.run` completes; the endpoint returns the `DebateResult` JSON regardless of whether the export succeeds (export failure is logged, not surfaced to the user)
- [x] 8.5 Write unit tests: (a) output file exists at expected path after export, (b) disclaimer present unconditionally, (c) agent labels correct in Summary table and Full Debate headers, (d) re-running overwrites the file

## 9. Volatility range in prediction endpoint

- [x] 9.1 Add `volatility_range_pct` field to `GET /tickers/{ticker}/prediction` response (calls `predict_volatility_range(ticker)`)
- [x] 9.2 Add `deprecated: true` field and `Deprecation: true` response header to `GET /tickers/{ticker}/insight` response
- [x] 9.3 Update prediction endpoint tests to assert `volatility_range_pct` present in response
- [x] 9.4 Update insight endpoint tests to assert `deprecated: true` field and deprecation header present

## 10. Frontend — DebatePanel component

- [x] 10.1 Create `frontend/src/components/DebatePanel/` with `DebatePanel.jsx`, `debate-panel.css`, `DebatePanel.test.jsx`
- [x] 10.2 Implement `useDebateAnalysis(ticker)` hook in `frontend/src/hooks/` — wraps `POST /tickers/{ticker}/debate` as a React Query mutation (on-demand, not auto-fetch)
- [x] 10.3 Add `postDebateAnalysis(ticker)` to `frontend/src/api/` client
- [x] 10.4 Implement not-run state: "Analyse [TICKER]" button + disclaimer visible; no placeholder N/A values
- [x] 10.5 Implement loading state: per-stage labels ("Running agents…" → "Comparing positions…" → "Synthesising…"); derive stage from mutation status or a staged polling approach
- [x] 10.6 Implement Level 1: verdict badge (color-coded by verdict), agreement label ("X of 3 agents"), per-agent stance icons (↑/→/↓), disclaimer unconditional (Rule 6), "Show reasoning" toggle
- [x] 10.7 Implement Level 2: three agent cards (header = "Technical Signal" / "News Context" / "Macro" per Rule 5), stance label, bullet reasoning list, key tension block, "Full debate" toggle
- [x] 10.8 Implement Level 3: Round 1 + Round 2 per-agent positions, synthesis reasoning, "Export confirmation" note (export already happened server-side; button copies the file path or shows a success message)
- [x] 10.9 Write component tests: (a) not-run state shows Analyse button and disclaimer, (b) Level 1 renders verdict + agreement after mutation success, (c) Level 2 renders agent cards with correct labels, (d) disclaimer present in all states, (e) "Market Sentiment" label never appears

## 11. Frontend — feature flag and dashboard wiring

- [x] 11.1 Add `VITE_DEBATE_PANEL_ENABLED` env variable to `frontend/.env.example` (default `false`)
- [x] 11.2 In `App.jsx` (or the component that renders the insight panel region), conditionally render `DebatePanel` when `import.meta.env.VITE_DEBATE_PANEL_ENABLED === 'true'`, otherwise render existing `AIInsightPanel`
- [x] 11.3 Verify that with flag `false`, existing `AIInsightPanel` tests pass unchanged
- [x] 11.4 Set `VITE_DEBATE_PANEL_ENABLED=true` in local `.env` for development; document in README how to enable

## 12. End-to-end validation

- [x] 12.1 Run full backend test suite (`pytest backend/tests`) — all existing tests pass; new tests pass
- [x] 12.2 Run frontend tests (`npm run test` in `frontend/`) — all existing tests pass; new DebatePanel tests pass
- [x] 12.3 Manual end-to-end with VCB: load ticker → click Analyse → debate completes → Level 1 shows verdict → Level 2 shows agent cards with correct labels → Level 3 shows full transcript → `reports/<date>_VCB.md` exists at repo root
- [x] 12.4 Verify `reports/<date>_VCB.md` structure matches design.md Decision 10 schema; verify disclaimer present; verify "News Context" label (not "Market Sentiment") in Agent Positions table
- [x] 12.5 Test graceful degradation: temporarily break one feed URL → the other feeds still supply headlines; break all feed URLs → NewsAgent returns neutral + "unavailable" reasoning → debate completes with 2 active agents; verify no crash
- [x] 12.6 Test feature flag rollback: set `VITE_DEBATE_PANEL_ENABLED=false` → AIInsightPanel renders → no DebatePanel in DOM
- [x] 12.7 Update `docs/MODEL_CARD.md` to note XGBoost directional serving is retired; document HAR-RV volatility model and its corr 0.479 baseline; update `openspec/config.yaml` milestone status and current model note

## 13. Data-source corrections (2026-10)

Found by running real debates: every agent except the Technical one reported "unavailable". Each fix has unit tests; the backend suite passes.

- [x] 13.1 NewsAgent: replace search-page scraping with the RSS feeds and `[ticker]` / `[sector]` / `[market]` tagging (`news_feeds.py`); correct the ICB sector map to the 18 supersector codes — design.md Decision 6
- [x] 13.2 NewsAgent: treat feed content as untrusted — `defusedxml`, 15 s / 2 MB / 3-redirect bounds per feed, markup / control / invisible-character stripping, future-dated items dropped
- [x] 13.3 NewsAgent: VN-Index headlines first (4 slots), reserved foreign-flow slots (2, market-wide recaps first); ticker symbols that are also everyday words (VND, VAT) match only as "cổ phiếu / mã VND"
- [x] 13.4 MacroAgent: move VN-Index and USD/VND to the vnstock 4.x `Market` API; log failures as warnings; run the fetches off the event loop with a 20 s deadline each; catch vnai's rate-limit `sys.exit()`
- [x] 13.5 MacroAgent: fix `_load_ohlcv_closes` ordering (it returned newest-first, flipping the sign of every return computed from it); relabel the relative-performance signal as the ticker's own return
- [x] 13.6 MacroAgent: replace per-ticker foreign flow (never available) with market-wide, latest-session foreign net value from the VCI price board — design.md Decision 7
- [x] 13.7 Synthesiser: define `r2_stances` in the reasoning fallback (an LLM failure there turned the whole debate into an HTTP 500)
- [x] 13.8 LLM client: add the `claude_cli` provider and `DEBATE_LLM_EFFORT` — design.md Decision 8 addendum

Not built: daily foreign-flow snapshots for a true rolling 5–10 session window (needs a job run after each close).
