## Why

The existing AI insight panel (M5/M6) produces a single deterministic output — Confidence, Technical Signal, and Advice — from a directional XGBoost model that `docs/DISCUSSION_model_direction.md` has established is statistically indistinguishable from a coin flip (pooled hit-rate 47.8%, corr 0.0095). The dashboard has solid data infrastructure (208 tickers, clean OHLCV, computed indicators) but no mechanism to synthesise qualitative market context — news, macro environment, sector momentum — alongside technical signals into a reasoned, legible analysis. This change replaces the single-model insight panel with a multi-agent debate system that treats analysis as a deliberative process: independent specialist agents present positions, argue against each other, and converge on a verdict that is transparent about its reasoning and its disagreements.

## What Changes

- **Retire XGBoost directional prediction** as the source of Advice and Confidence. The model remains in the codebase but is removed from the live serving path. Its directional output has no demonstrated value (Finding 3, `DISCUSSION_model_direction.md`); replacing it with a volatility-range estimate (HAR-RV linear model, corr 0.48 established in Finding 5) is a prerequisite for the Technical Agent's range signal.
- **Introduce three specialist agents** running in parallel on-demand:
  - `TechnicalAgent` — indicators (RSI, MACD, Ichimoku, Bollinger, ATR), volatility range estimate, OBV trend
  - `NewsAgent` — recent Vietnamese financial headlines from public RSS feeds (VnExpress, CafeF, Vietstock), tagged ticker / sector / market-wide, + LLM extraction of bullish/bearish signals and market backdrop
  - `MacroAgent` — quantitative macro signals: VN-Index trend, the ticker's return relative to VN-Index, USD/VND rate, market-wide foreign net flow for the latest session (all from the vnstock 4.x API, no scraping)
- **Introduce a Synthesiser agent** that reads all three positions after a response round and produces a verdict with majority logic, explicit key tensions, and a confidence level based on agent agreement.
- **Replace the AIInsightPanel** with a progressive-disclosure Debate Panel:
  - Level 1: verdict + agent stance summary (glanceable)
  - Level 2: per-agent position + key tension (expandable)
  - Level 3: full debate transcript + export to `.md` (deep review)
- **Add on-demand markdown export** — each completed analysis is written to `reports/YYYY-MM-DD_<TICKER>.md`, structured for NotebookLM ingestion as a searchable knowledge base of dated analyses.
- **Explicitly implement M8 (real news sentiment)** — this change is where Rule 5's "technical proxy only" constraint is relaxed for the NewsAgent, which produces genuine news-derived context. Rule 5 is honored for the TechnicalAgent's signal; the NewsAgent's output is labeled distinctly as "news context", not "Market Sentiment".

## Capabilities

### New Capabilities

- `debate-engine`: Orchestration layer that runs three specialist agents in parallel, collects positions, runs a response round, and calls the Synthesiser. Manages agent state, prompt construction, and LLM calls. Backend service under `backend/app/services/debate/`.
- `technical-agent`: Specialist agent that reads the ticker's latest feature row and OHLCV, computes a stance (bull/bear/neutral) with reasoning from RSI, MACD, Ichimoku, Bollinger bands, ATR, OBV, and a 5-session volatility range estimate from a HAR-RV linear model (replacing XGBoost direction). Honors Rule 1 (target definition), Rule 2 (no raw log return), Rule 3 (volatility-relative thresholds).
- `news-agent`: Specialist agent that reads recent Vietnamese financial headlines from public RSS feeds (VnExpress, CafeF, Vietstock), tags them as ticker, sector or market-wide news, feeds them to an LLM, and returns bull/bear/neutral stance + structured bullet reasoning. Explicitly labeled as "news context" in the UI — not "Market Sentiment" — to remain distinct from Rule 5's technical proxy.
- `macro-agent`: Specialist agent that computes quantitative macro signals — VN-Index 20-session trend, the ticker's 20-session return relative to VN-Index, USD/VND 5-session change, market-wide foreign net buy/sell value for the latest session — and returns a stance + reasoning. No scraping; all data from the vnstock 4.x API or existing OHLCV.
- `debate-synthesiser`: Agent that receives all three specialist positions plus their round-2 responses, counts majority, identifies the key tension (the strongest minority argument), and produces the final verdict object: `{ verdict, agreement_level, tensions, reasoning }`.
- `debate-report-export`: Service that serialises a completed debate into a structured `.md` file written to `reports/YYYY-MM-DD_<TICKER>.md`, with sections matching the progressive-disclosure levels so NotebookLM can answer both summary and deep queries from the same file.
- `debate-panel-ui`: Progressive-disclosure frontend component replacing `AIInsightPanel`. Three disclosure levels: verdict + stance row (Level 1, always visible), per-agent cards + key tension (Level 2, expandable), full transcript + export button (Level 3). Honors Rule 6 (disclaimer always visible at Level 1).

### Modified Capabilities

- `dashboard-ui`: The AI insight panel region is replaced by the new `debate-panel-ui` component. The panel's trigger changes from automatic (loads with ticker) to on-demand (user clicks "Analyse"). Level 1 shows a stale/not-run state before first analysis.
- `ticker-prediction`: `GET /tickers/{ticker}/prediction` and `GET /tickers/{ticker}/insight` are retained for backwards compatibility during the transition but the insight endpoint's Advice field is marked deprecated — debate verdict supersedes it. The XGBoost model is removed from the live prediction path; the endpoint returns the volatility range instead of a directional point prediction. This is a **BREAKING** change to the prediction endpoint's response shape (adds `range_pct`, removes directional `predicted_log_return` from the primary response).

## Impact

- **Backend**: new `backend/app/services/debate/` package (`engine.py`, `technical.py`, `news.py`, `macro.py`, `synthesiser.py`, `export.py`); new `backend/app/api/debate.py` endpoint (`POST /tickers/{ticker}/debate`); new `backend/app/ml/volatility.py` (HAR-RV linear model, replaces XGBoost direction in serving); new `backend/reports/` directory for `.md` exports.
- **Frontend**: `AIInsightPanel` replaced by `DebatePanel`; new `useDebateAnalysis` hook (mutation, not query — on-demand); `useTickerInsight` and `useTickerPrediction` hooks remain for backwards compatibility during transition.
- **Dependencies**: adds `httpx` (async HTTP for the news feeds), `defusedxml` (safe RSS parsing) and LLM SDKs (OpenAI, `anthropic`) to `backend/requirements.txt`; the LLM provider is configurable via environment variable — `openai`, `anthropic`, or `claude_cli` (the `claude` command, using a Claude login instead of an API key) — no hard dependency on a specific vendor.
- **Domain rules touched**: Rule 4 (Confidence) — the hit-rate concept no longer applies once XGBoost direction is retired; agreement level between agents replaces it. Rule 4 requires sign-off to change. Rule 5 (Sentiment = technical proxy only) — NewsAgent introduces real news context under a distinct label; the technical proxy label is preserved for TechnicalAgent's signal only. This is a deliberate relaxation of Rule 5 for the NewsAgent surface, not a silent change — noted here for sign-off.
- **docs/DISCUSSION_model_direction.md option selected**: Option 3 (volatility range) for the Technical Agent's quantitative signal; Option 1 (do nothing to XGBoost direction) for the retired endpoint — it stays in the codebase but exits the serving path.
- **docs/DISCUSSION_prediction_outcome_tracking.md**: the `.md` export partially addresses the "no mechanism logs live predictions" gap — each analysis is dated and archived — but outcome tracking (scoring a past analysis against realized price) is explicitly out of scope for this change.
