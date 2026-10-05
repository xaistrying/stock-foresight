## Context

The existing AI insight panel delivers a single deterministic result — Confidence (Rule 4: hit-rate), Technical Signal (Rule 5: RSI/MACD/Ichimoku proxy), and Advice (Rule 3: volatility-relative direction) — driven by an XGBoost model whose directional output `docs/DISCUSSION_model_direction.md` established is statistically worthless (corr 0.0095, 47.8% hit-rate). The infrastructure underneath the model — 208 tickers, computed indicators, OHLCV quality gate — is sound and remains. The problem is that a single deterministic number gives no insight into *why* a signal is what it is, and papers over genuine uncertainty.

The proposed change replaces the single-model panel with a three-agent adversarial debate: Technical, News, and Macro agents each form an independent position; a Synthesiser then resolves them. The UI adopts progressive disclosure so the verdict is glanceable but the full reasoning is always one click away. Every completed analysis is exported to a structured `.md` file for NotebookLM archival.

Key constraints flowing into this design:
- FastAPI + React stack; no new framework without prior agreement
- vnstock package is the canonical data source for VN market data
- LLM vendor is left configurable (environment variable); no hard-coded provider
- On-demand only — no background scheduling in this change
- Rules 1–6 remain in effect; Rule 4 and Rule 5 are explicitly touched (see Decisions)

## Goals / Non-Goals

**Goals:**
- Replace the XGBoost directional serving path with a HAR-RV volatility-range estimate (corr 0.48, proven in Finding 5 of `DISCUSSION_model_direction.md`)
- Run three specialist LLM agents in parallel on-demand for a selected ticker
- Produce a verdict with explicit agreement level and key tensions, not a forced consensus
- Expose the result through a three-level progressive-disclosure UI
- Export each analysis to `reports/YYYY-MM-DD_<TICKER>.md` for NotebookLM
- Honor Rule 6 (disclaimer) at Level 1 — always visible, no collapse
- Honor Rule 2 (no raw log return in UI) — volatility range shown as ±X%

**Non-Goals:**
- Scheduled / background analysis (on-demand only)
- Outcome tracking — scoring past analyses against realized prices (deferred, see `DISCUSSION_prediction_outcome_tracking.md`)
- PDF parsing of SSI Research or other structured reports (v1 uses headlines only)
- Retaining XGBoost direction in any live path
- Calendar staleness fix (deferred, see `DISCUSSION_calendar_staleness.md`)
- Portfolio-level risk or holdings (Finding 7 option, not in scope here)
- Cross-sectional momentum signal (Finding 9 outcome: not exploitable at current scale)

## Decisions

### Decision 1: Adversarial structure — parallel positions + response round + synthesis

**Chosen**: Three agents produce independent positions first (Round 1, run in parallel). Each agent then receives the other two positions and produces a short response — hold, shift, or qualify — without being forced to agree (Round 2, run in parallel). A Synthesiser reads all six outputs (3 × Round 1 + 3 × Round 2) and produces the verdict.

**Why not sequential chain**: A → B → C chains cause downstream agents to anchor on whoever went first, suppressing genuine disagreement. The whole value of a debate is independent signal; chaining degrades it to elaboration.

**Why not pure majority vote without a response round**: Round 2 surfaces the *strongest counter-argument*, which is the most useful thing for a human reader: not "two agents agree" but "two agents agree and the dissenter's reason is X." The response round is cheap (3 short LLM calls) and adds the tension that makes Level 2 of the UI worth opening.

**Why not unlimited rounds**: Convergence is not the goal — honest disagreement preserved in the output is. Two rounds (position + response) are sufficient; more rounds push toward consensus and erase the signal.

### Decision 2: Verdict levels — `STRONG_BUY_SIGNAL` / `BUY_SIGNAL` / `OBSERVE` / `CAUTION_SIGNAL` / `STRONG_CAUTION_SIGNAL` / `SPLIT`

**Chosen**: Six verdict values keyed to agent agreement:
- 3/3 bullish → `STRONG_BUY_SIGNAL`
- 2/3 bullish → `BUY_SIGNAL`
- 3/3 neutral → `OBSERVE`
- 2/3 neutral (mixed) → `SPLIT` (no majority direction)
- 2/3 bearish → `CAUTION_SIGNAL`
- 3/3 bearish → `STRONG_CAUTION_SIGNAL`

"SPLIT" is an explicit outcome, not a fallback. It means the data is genuinely ambiguous and the right action is to observe — that is more honest than forcing a verdict from a tie.

**Domain rule note**: None of these verdict labels are "BUY" or "SELL" — Rule 6 is honored. The labels are framed as signals and observations, not advice. The disclaimer (docs/DISCLAIMER.md) is displayed at Level 1 unconditionally.

**New label definition** (not previously covered by rules 1–6): `agreement_level` ∈ `{unanimous, majority, split}` — reflects how many agents agreed, shown in Level 1's subtitle line.

### Decision 3: Rule 4 replacement — agreement level, not hit-rate

**Sign-off required** (Rule 4 change): The existing Confidence score (hit-rate over ~60 backtested predictions) cannot survive the retirement of XGBoost directional predictions. With no directional prediction, there is nothing to score a hit-rate against.

**Chosen replacement**: `agreement_level` — `unanimous` (3/3), `majority` (2/3), `split` (no majority) — displayed in Level 1 alongside the verdict. This is structurally similar to Rule 4's intent (a calibration signal for how much to trust the output) but sourced from inter-agent consistency rather than backtested accuracy.

**What this is not**: it is not a statistical confidence interval, not a probability, not a backtested hit-rate. It is an agreement count. The UI must label it as such: "2 of 3 agents" not "67% confidence."

**The old Confidence widget** in `AIInsightPanel` is retired with the XGBoost path. The `GET /tickers/{ticker}/insight` endpoint is deprecated but not removed in this change.

### Decision 4: Rule 5 boundary — TechnicalAgent keeps the proxy label; NewsAgent uses a distinct label

**Relaxation noted** (Rule 5 partial change): Rule 5 says "Market Sentiment" must be labeled a technical proxy. This change introduces genuine news context via the NewsAgent — that is, by definition, not a technical proxy.

**Chosen boundary**:
- `TechnicalAgent` output is labeled **"Technical Signal"** — Rule 5 honored unchanged
- `NewsAgent` output is labeled **"News Context"** — explicitly distinct from "Market Sentiment"
- The overall debate verdict is labeled **"Debate Verdict"** — never "Market Sentiment"
- "Market Sentiment" as a label does not appear anywhere in the new UI

This preserves Rule 5's letter and spirit: the technical proxy is still labeled as such. The NewsAgent surface is a new label that Rule 5 does not govern.

### Decision 5: Volatility range replaces XGBoost directional point — HAR-RV linear model

**Chosen**: A HAR-RV (Heterogeneous Autoregressive Realized Volatility) linear model using 5-session, 20-session, and 60-session trailing close-to-close volatility as predictors, trained on the existing OHLCV data. This implements Finding 5's best approach (corr 0.479) without requiring `high`/`low` (Parkinson/Garman-Klass, which would improve to 0.464 but `high`/`low` are underused in the current pipeline — a future improvement).

**Output**: `±X%` range displayed as the TechnicalAgent's quantitative anchor (e.g. "Expected range: ±2.1% over 5 sessions"). Rule 2 honored — no raw log return shown; converted to percentage. Rule 1 — the 5 trading sessions horizon is preserved.

**Why not retrain XGBoost for volatility**: Finding 6 showed a plain linear regression edges out tuned XGBoost (0.479 vs 0.471) for this target because log-volatility is close to linear-additive in its predictors. Using the correctly-shaped tool.

### Decision 6: NewsAgent data sources — public RSS feeds (VnExpress, CafeF, Vietstock), tagged by relevance

**Chosen**: Async fetch (httpx) of three public RSS feeds — VnExpress *kinh doanh*, CafeF *thị trường chứng khoán*, Vietstock *cổ phiếu* — parsed with `defusedxml`. Headlines from the last 7 calendar days are tagged `[ticker]` (names the symbol as a whole word, in the title or snippet), `[sector]` (the title matches Vietnamese keywords for the ticker's ICB supersector) or `[market]` (VN-Index, rates, FX, GDP, foreign flow ...), ordered ticker, then sector, then market, and capped at 5 / 4 / 10 (19 in all). Among `[market]` headlines, VN-Index ones come first (at most 4), then foreign-flow ("khối ngoại") ones (2 reserved slots, market-wide recaps ahead of one-stock stories). The LLM receives headline text only — each with its date and a snippet of at most 160 characters; no full-article parsing in v1.

**Revision (2026-10)**: v1 scraped the sites' *search pages* and kept only headlines that named the ticker or its sector. By implementation time it returned nothing for any ticker: Vietstock's search URL answered 404, Cafef's results never passed the ticker filter, and the sector map used ICB codes the universe table does not hold (so no sector was ever found). The ticker-name filter was also the wrong shape: market-wide news (VN-Index moves, rates, FX, GDP, foreign flow) moves most stocks, and in a sample of 177 feed items none named SAB.

**Why RSS** (this reverses v1's "why not RSS/API"): each site publishes a stable public RSS feed of 20–60 recent items spanning 1–5 days, verified live on 2026-10-05. Feeds are structured, so there is no regex over page HTML.

**Market-wide headlines are context, not company evidence**: the prompt says so explicitly and keeps the stance neutral unless the headlines themselves make a case for bull or bear; bullets cite each headline's tag and date. Text-based macro reasoning belongs in this agent (see Decision 7).

**Feed content is untrusted** (it reaches an LLM prompt): XML is parsed with `defusedxml` (no entity expansion); each feed is bounded to 15 s in total, 2 MB decoded and 3 redirects; markup, control and invisible characters are stripped and text is length-capped; the prompt tells the model to ignore instructions inside headlines. With the `claude_cli` provider tools are disabled, so a hostile headline can only change the text output.

**Why 7 days**: Shorter windows miss multi-day news cycles; longer windows pull in stale context that the Macro Agent already covers via index trends. 7 calendar days is ~5 trading sessions, matching the prediction horizon (Rule 1). The feeds themselves reach back only 1–5 days.

**Failure mode**: One feed failing is logged and skipped. If every feed fails, the NewsAgent returns a `stance: "neutral"` with `reasoning: ["News data unavailable — could not fetch the news feeds."]`; if the feeds work but nothing is relevant, `["No recent news found for this ticker, its sector or the market."]`. Either way the debate proceeds and the synthesiser notes the absence.

### Decision 7: MacroAgent data sources — vnstock 4.x market data

**Chosen**: All data via vnstock's 4.x `Market` API — no additional scraping:
- VN-Index 20-session price trend (computable from existing `ohlcv` for `VNINDEX` if loaded, else `Market().index("VNINDEX")`)
- Ticker vs VN-Index: the ticker's own 20-session return minus the index's (outperform / inline / underperform, ±1 point). **Revised (2026-10)**: v1 specified a *sector index* relative return, but free vnstock data has no sector index and it was never implemented; the code computes the ticker's own return, and the prompt now says so (the model had been reporting "the sector is outperforming").
- USD/VND 5-session change: `Market().forex("USDVND")`
- Foreign flow — market-wide, latest session (below)

**Foreign flow — revised (2026-10)**: v1 assumed per-ticker net foreign flow from vnstock trading data ("available per-ticker"). It is not available: `foreign_trade` raises `NotImplementedError` on both free providers (kbs, vci), for the index and for tickers alike, and the index quote's foreign fields are zeros. What the free API does return is each stock's foreign buy and sell *value* for the latest session, from VCI's price board. The agent sums that over 30 large caps (VN30 as of writing; a sample, refreshed when the index is reviewed) into net and gross value; a net beyond ±10% of gross (provisional and not backtested, like Rule 3's 0.5) votes inflow/outflow, otherwise neutral. Limits: latest session only (partial while the market is open), negotiated deals are included, and there is no history to roll over 5–10 sessions. The multi-session picture reaches the debate through the NewsAgent instead — press recaps such as "khối ngoại bán ròng ... trong tuần" hold reserved slots (Decision 6). A true rolling window would need daily snapshots stored by a job run after each close; that is not built.

**Resilience**: The fetches run off the event loop (`asyncio.to_thread`), in parallel, each with a 20 s deadline. A failure degrades that signal to "unavailable" (no vote) and logs a warning — for foreign flow once per process, then at debug level. vnai's rate limiter ends the process with `sys.exit()` (a `SystemExit`, which `except Exception` misses); the fetchers catch it, as bulk ingestion does, and re-raise any other exit request.

**Why purely quantitative**: The Macro Agent's value is fast, reproducible signal from clean numbers — not LLM interpretation of macro text. Text-based macro reasoning belongs in the NewsAgent (its `[market]` headlines carry it). Keeping MacroAgent deterministic means its Round 1 position is computed, not generated, which is faster and cheaper.

**LLM use in MacroAgent**: The LLM is used only to *translate* the computed signals into a stance + bullet reasoning, not to fetch or interpret raw data. The computed values are passed as structured context in the prompt.

### Decision 8: LLM provider — configurable via environment variable, defaulting to OpenAI

**Chosen**: A thin `LLMClient` abstraction in `backend/app/services/debate/llm_client.py` that reads `DEBATE_LLM_PROVIDER` (default: `openai`) and `DEBATE_LLM_MODEL` (default: `gpt-4o-mini`) from environment. The abstraction wraps enough of the OpenAI SDK to also support `anthropic` (Claude) by switching the provider variable.

**Why gpt-4o-mini as default**: Vietnamese language support is strong, cost is low (~$0.15/1M input tokens), and latency is acceptable for on-demand use. The full debate (6 LLM calls + synthesis) is estimated at ~8,000–15,000 tokens total, costing ~$0.01–0.02 per analysis at gpt-4o-mini rates. Adjust upward for gpt-4o if quality warrants.

**Why an abstraction**: avoids hard vendor lock-in; lets the user switch to Claude (better Vietnamese reasoning in some benchmarks) or a local model without rewiring the engine.

**Addendum (2026-10) — `claude_cli` provider and reasoning effort**: a third provider, `DEBATE_LLM_PROVIDER=claude_cli`, runs the `claude` command (Claude Code) headless so the debate can use a Claude subscription login where no API key is available. Each call spawns a process (slower than an API call), counts against the subscription's usage limits, and ignores `DEBATE_MAX_TOKENS_PER_CALL` and temperature. It runs with tools disabled, from an empty directory, ignoring the user's Claude Code hooks, plugins and `CLAUDE.md` (they added ~35k tokens per call); `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` are removed from its environment so it always uses the login. The prompt goes in argv after `--`, with stdin on `/dev/null`: `claude -p` waits only 3 s for stdin and a stalled event loop can exceed that. `DEBATE_LLM_MODEL` takes the CLI's aliases (default `haiku`; also `sonnet`, `opus`), and `DEBATE_LLM_EFFORT` (`low` … `max`; unset uses the CLI's default) sets reasoning effort — an unknown value is rejected because the CLI silently ignores it.

### Decision 9: Progressive disclosure — three levels, client-side state, no separate routes

**Chosen**: A single `DebatePanel` React component with internal `disclosureLevel` state (0 = not run, 1 = verdict, 2 = agent cards, 3 = full transcript). No separate page routes; the panel expands in place within the existing dashboard layout.

**Level 1** (always visible after analysis runs): verdict badge, agreement label ("2 of 3 agents"), per-agent stance icons (↑ bull / → neutral / ↓ bear), disclaimer (Rule 6).
**Level 2** (one click on verdict or "Show reasoning"): per-agent card with stance + bullet reasoning (3–5 bullets each), key tension block (the synthesiser's identified disagreement).
**Level 3** (one click on "Full debate" or "Export"): full Round 1 positions, Round 2 responses, synthesiser reasoning, export-to-`.md` button.

**Not run state**: Level 1 shows an "Analyse" button. Before first analysis, no stale data is shown — blank state with prompt to run. This is different from the old `AIInsightPanel` which showed N/A placeholders automatically on ticker load.

**Why not a separate page**: the dashboard is a single-page tool; navigating away from the chart to read an analysis breaks the workflow. The panel expands in-place.

### Decision 10: Markdown export structure — three-section document matching disclosure levels

**Chosen schema** for `reports/YYYY-MM-DD_<TICKER>.md`:

```
# <TICKER> · <DATE>

## Summary
**Verdict**: <verdict>  
**Agreement**: <agreement_level> (<N> of 3 agents)  
**Agents**: Technical <stance_icon> · News <stance_icon> · Macro <stance_icon>

## Agent Positions
| Agent | Stance | Key reasoning |
...

## Key Tension
<synthesiser's tension paragraph>

## Full Debate
### Round 1 — Initial Positions
#### Technical Agent ...
#### News Agent ...
#### Macro Agent ...
### Round 2 — Responses
#### Technical Agent ...
...
### Synthesis
...

---
*Technical observation — not investment advice. See docs/DISCLAIMER.md.*
```

**Why this structure**: NotebookLM answers both "what was the VCB verdict on 04 Oct?" (Summary section) and "what did the news agent say specifically?" (Full Debate section) from the same document. The Summary section alone is enough for a quick query; the Full Debate enables deep queries.

## Risks / Trade-offs

**[News feed availability] → Mitigation**: A feed URL can move or disappear (v1's scraped search pages did: Vietstock's returned 404). Three independent feeds are fetched concurrently; one failing is logged and skipped, and all failing degrades the NewsAgent to neutral stance + "unavailable" reasoning rather than failing the whole debate. The feed code is isolated in `news_feeds.py`; fixing it does not touch other agents.

**[LLM cost creep] → Mitigation**: Each analysis costs ~$0.01–0.02 at gpt-4o-mini. On-demand only (not scheduled) bounds cost to user-initiated calls. A `DEBATE_MAX_TOKENS_PER_CALL` env variable caps individual call size. No mitigation for a user running analysis in a tight loop — cost is noted as a known open item, not solved in this change.

**[LLM hallucination in NewsAgent] → Mitigation**: The LLM receives only headlines as input for the NewsAgent, not open-ended web access. Prompt explicitly instructs the model to derive signals only from the provided headlines, to treat `[market]` headlines as backdrop rather than company evidence, and to stay neutral unless the headlines make a case. The structured output format (stance enum + bullet list) reduces hallucination surface compared to free-form generation.

**[Slow debate latency] → Mitigation**: Round 1 runs three agents in parallel (asyncio). Round 2 runs three response calls in parallel. The sequential bottleneck is only Round 1 → Round 2 → Synthesis (three serial steps of parallel calls). Estimated wall time was 4–8 seconds for gpt-4o-mini; measured with the `claude_cli` provider (Sonnet, extra-high effort) it is roughly 40–65 seconds, dominated by per-call process start-up and four serial LLM steps (Round 1, Round 2, then the synthesiser's two calls in sequence). The UI shows a per-stage loading indicator ("Running Technical... News... Macro..." then "Comparing positions..." then "Synthesising...") so the user understands what is happening.

**[Rule 4 Confidence widget removed — users expect it] → Mitigation**: The old `AIInsightPanel` showed Confidence prominently. This change retires it. The `GET /tickers/{ticker}/insight` endpoint is deprecated but kept alive; a banner in the new panel explains the change for any user who notices.

**[VN-Index not in OHLCV if not loaded] → Mitigation**: The MacroAgent checks whether `VNINDEX` is in the OHLCV table; if not, it fetches via vnstock's `Market().index("VNINDEX")` directly (the pre-4.x `Vnstock().stock(...)` API raises for an index). Not a blocker — just a conditional fetch path.

**[Round 2 pushes agents toward agreement] → Mitigation**: The Round 2 prompt explicitly instructs agents to maintain their position if the evidence supports it and to shift *only* if a specific counter-argument is compelling. The synthesiser is instructed to report the Round 2 final position of each agent, not whether they shifted — preventing "agreement theater."

## Migration Plan

1. **Merge debate engine and new API endpoint** without touching existing endpoints. `GET /tickers/{ticker}/insight` and `GET /tickers/{ticker}/prediction` continue to function unchanged.
2. **Deploy HAR-RV volatility model** — a new artifact in `backend/data/models/har_rv_model.pkl`. Does not replace `pooled_xgb_model.json`; coexists with it.
3. **Replace `AIInsightPanel` with `DebatePanel`** in the frontend. Feature-flagged initially via `VITE_DEBATE_PANEL_ENABLED=true` env variable — allows toggling back to the old panel without code change if needed.
4. **Validate one ticker end-to-end** (VCB recommended — good liquidity, active news coverage, sector clearly defined) before removing the feature flag.
5. **Deprecate `GET /tickers/{ticker}/insight`** with a response header `Deprecation: true` once the debate panel is stable. Remove in a later change — not this one.

**Rollback**: set `VITE_DEBATE_PANEL_ENABLED=false` → old panel returns. The XGBoost model is never deleted from disk; reverting the feature flag fully restores old behaviour.

## Open Questions

1. **LLM prompt language** — Vietnamese or English? The NewsAgent reads Vietnamese headlines; reasoning in English is easier to review and test, but Vietnamese may produce more nuanced extraction of VN-specific financial terminology. Decision deferred to implementation; default to English with explicit instruction to handle Vietnamese input.

2. **MacroAgent foreign flow data freshness** — *Resolved (2026-10)*: there is no per-ticker foreign flow in free vnstock data at all (see Decision 7). The market-wide latest-session figure is as fresh as VCI's price board, and partial while the market is open.

3. **Reports directory location** — `backend/reports/` (colocated with the backend, easy to serve via FastAPI) vs. `reports/` at the repo root (more visible, easier to push to NotebookLM manually). Leaning toward `reports/` at repo root; confirm before implementing the export service.

4. **Feature flag default** — ship with debate panel on or off by default? Leaning toward off (`VITE_DEBATE_PANEL_ENABLED=false`) for the first deploy, enabling manually after validation. Confirm before frontend implementation.
