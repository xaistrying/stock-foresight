## Rule texts for review

**Status: Rules 1-6 approved by the owner on 2026-10-07 and applied to `CLAUDE.md` and `openspec/config.yaml` (tasks 5.1, 5.3, 5.4); the disclaimer wording (row D) was approved the same day. All sign-off rows are approved.** Shortened 2026-10-07 at the owner's request: the rule texts below state the principle only; every dropped detail (the range hit-rate definition and windows, the label and disclaimer placement, the `N of the last M` wording) is already enforced by a named requirement in this change's or `calibrate-volatility-range`'s specs, and the longer wording is kept in the appendix at the end. On 2026-10-07 the owner accepted the verdict labels, the disclaimer placement, the Macro-agent gap and the range hit-rate definition (recorded in Decisions 3, 4, 6, 7, 8); the owner has not yet read the final Rule 1-6 texts below. Until the Sign-off record says otherwise, `CLAUDE.md` and `openspec/config.yaml` are not edited (task 1.1 is the gate). The exact old texts are in `CLAUDE.md:24-42`; the new texts are pasted verbatim into both files after approval. Rationale and alternatives are in Decisions 1 to 6.

| Rule | Old | New |
| --- | --- | --- |
| 1 | **Prediction target**: `target_t = ln(close[t+5] / close[t])` — log return, 5 TRADING SESSIONS ahead, not calendar days. | **Horizon and outcome**: the horizon is 5 TRADING SESSIONS ahead, not calendar days. Ranges and verdicts are scored against the realised `outcome_t = ln(close[t+5] / close[t])`; the volatility model targets the daily sigma of log returns over the next 5 sessions, displayed as a 5-session band. |
| 2 | **Never show raw log return in the UI** — convert to a simple percentage for display. | Unchanged. |
| 3 | **Advice thresholds are volatility-relative**: `0.5 x rolling_std(returns, 60 sessions)`, not a fixed number. The `0.5` coefficient is provisional (may change after M3 backtesting) — the volatility-relative *design* is not provisional. | **Magnitude thresholds are volatility-relative**: any threshold on the size of a price move is set relative to the ticker's volatility, not as a fixed number. (The former Advice formula and its `0.5` coefficient are retired with Advice.) |
| 4 | **Confidence score (v1)** = backtested hit-rate over the ticker's most recent ~60 predictions. Not a statistical prediction interval (that's a future quantile-regression upgrade, out of v1 scope). | **Reliability is measured, never asserted**: the only reliability figure shown is the range hit-rate, measured from price history and labelled as such. The agent vote count is labelled **Agreement**, never Confidence. The band states its nominal coverage; it is not a guaranteed interval. |
| 5 | **"Market Sentiment" is a technical proxy** (RSI, MACD, Ichimoku position), not real news/NLP sentiment. Must be labeled as such in the UI. | **Label by provenance**: name each agent for what it reads (Technical Signal, News Context, Macro) and mark language-model text as such. "Market Sentiment" is reserved for the technical proxy (RSI, MACD, Ichimoku) and is never applied to news, macro or a verdict. |
| 6 | **Never frame output as investment advice.** Use "technical observation" framing and show the disclaimer from `docs/DISCLAIMER.md` (created M6, not before — nothing to disclaim until M6 has UI output) anywhere Advice, Confidence, or Sentiment is displayed. | **Never frame output as investment advice.** Use "technical observation" framing. Verdict labels contain no buy, sell, hold or other instruction. Show the disclaimer from `docs/DISCLAIMER.md` wherever a verdict, Agreement, a range or agent reasoning is displayed or exported. |

## Context

The product moved from an XGBoost 5-session return predictor (retired: out-of-fold corr about 0.01) to a HAR-RV volatility band plus a three-agent LLM debate whose verdict is a deterministic vote over Round 2 stances (`multi-agent-debate-analyst` and `debate-data-quality-refinements`, archived 2026-10-05). Nothing under `CLAUDE.md`, `openspec/config.yaml`, `docs/` was updated: archived task 12.7 is ticked but neither pivot commit touched them (review Finding 6).

Figures below are "measured in the 2026-10-06 review" (`docs/DISCUSSION_post_pivot_review.md`); they were not reproduced by the author of this change. Task 1.2 reproduces the ones this change relies on. All file:line references were re-checked against the tree at commit `e77986e`.

Current state this change addresses:

- `CLAUDE.md:24-42` and `openspec/config.yaml:32-47` hold six rules that describe the retired product. Rule 4's Confidence is a backtest hit-rate from `backtest_predictions` (review: 10,191 rows, 10 tickers, last date 2026-08-05, pooled 47.7%, so 589 of 599 loaded tickers would read N/A). The archived debate design (Decision 3) flagged Rule 4 and Rule 5 "requires sign-off"; none is recorded and `CLAUDE.md` is unchanged.
- `docs/DISCLAIMER.md` describes Confidence, a "statistical model" and a backtested hit-rate. `DebatePanel.jsx:10-11` and `export.py:22` show a different, paraphrased one-liner that ends with a repo path the user cannot open.
- Verdict labels "Strong Buy Signal" / "Buy Signal" / "Caution Signal" sit in `DebatePanel.jsx:14-21` and `export.py:36-43`. The M5 notes (`docs/M5_DASHBOARD_EXPLORE_NOTES.md:185-188`) rejected BUY/SELL wording. The only guard, `/\bBUY\b/` in `AIInsightPanel.test.jsx:255`, is case-sensitive and covers a different component.
- `synthesiser.py:70` and `:79-87` put the raw enum (`BUY_SIGNAL`) into the key-tension and synthesis prompts, and `:168` writes `Verdict: BUY_SIGNAL (...)` into the displayed synthesis text when the LLM call fails.
- `openspec/config.yaml` still says "AI insight panel (Confidence, Market Sentiment, Advice)" (`:6-11`), that DATA_DICTIONARY and DISCLAIMER "don't exist yet" (`:51-56`), that M8 is "not started" (`:144-148`); `CLAUDE.md:13` promises an "AI insight panel response contract" that `config.yaml` does not contain (verified: the only "contract" hits are `:79`, `:140`, `:143`).

The owner has said the app is for personal use, which makes Rules 1-6 design choices rather than compliance constraints. The wording below is product wording, not legal advice; if the app is ever shown beyond personal use, confirm label and disclaimer wording with whoever owns compliance.

## Goals / Non-Goals

**Goals:**
- Exact, reviewable old-to-new texts for the six rules, and a recorded owner sign-off before `CLAUDE.md` or `config.yaml` is touched.
- One disclaimer text, in `docs/DISCLAIMER.md`, shown verbatim everywhere, with tests that fail on drift.
- Non-transactional verdict display labels in the panel and the export, "Agreement" for the vote count, a language-model note, neutral verdict wording in the synthesiser prompts, and case-insensitive guards.
- A verified list of stale doc claims, fixed, and a re-runnable check.

**Non-Goals:**
- Renaming enum values (`BUY_SIGNAL` etc.): recorded as a future option; the API contract does not change.
- Range maths, coverage method, `/range` (`calibrate-volatility-range`); removals in the dashboard (`retire-direction-model`); data guards and the `INSUFFICIENT_DATA` value (`debate-data-guards`); the outcome log table (`debate-outcome-log`); failure texts and prompt fencing (`harden-debate-runtime`).
- Any code outside label and disclaimer strings and their tests (plus one read-only script and one docs-lockstep test).
- Filtering LLM-written text for the words buy/sell (macro reasoning legitimately says "foreign net buying").

## Decisions

Each rule decision gives the exact old text (as in `CLAUDE.md`; `config.yaml` has the same words without bold and with different wrapping) and the proposed new text. The new text is pasted verbatim into both files after sign-off. Per the `config.yaml` design rule, each says which rule it implements or that it is new.

### Decision 1: Rule 1 keeps the formula but becomes the realised outcome (requires sign-off)

**Old**
> 1. **Prediction target**: `target_t = ln(close[t+5] / close[t])` — log return, 5 TRADING SESSIONS ahead, not calendar days.

**New**
> 1. **Horizon and outcome**: the horizon is 5 TRADING SESSIONS ahead, not calendar days. Ranges and verdicts are scored against the realised `outcome_t = ln(close[t+5] / close[t])`; the volatility model targets the daily sigma of log returns over the next 5 sessions, displayed as a 5-session band.

**Why**: the HAR-RV target is the std of five daily returns (`volatility.py:91-100`), not the log return; the debate keeps only the horizon. `DISCUSSION_model_direction.md:474` already asked for this ruling. Forecasting the realised outcome stays impossible to claim (corr about 0.01), so the formula survives only as the scoring quantity.

**Alternatives**: (a) keep Rule 1 verbatim: then the HAR target contradicts a "non-negotiable" rule. (b) A separate Rule 7 for volatility: seven rules, and the horizon and outcome are one idea. (c) Drop the formula: loses the definition `debate-outcome-log` and `range_hit_rate` score against.

### Decision 2: Rule 2 unchanged

**Text**: `2. **Never show raw log return in the UI** — convert to a simple percentage for display.` No edit. The band is displayed as a percentage (`range_5s_pct`, labelled "typical 5-session move" by `calibrate-volatility-range`), never a log value.

Note for that change: a half-width `r` in log space is `+(e^r-1)` up and `-(1-e^-r)` down; the difference is under 0.25 points at +/-5% and about 1 point at +/-10%, so a symmetric "+/-x%" is a rounding choice. It is recorded here as a literal-reading wrinkle, not a decision (Open Question 6).

### Decision 3: Rule 3 retired with Advice; the principle is re-homed in the same slot (requires sign-off)

**Old**
> 3. **Advice thresholds are volatility-relative**: `0.5 x rolling_std(returns, 60 sessions)`, not a fixed number. The `0.5` coefficient is provisional (may change after M3 backtesting) — the volatility-relative *design* is not provisional.

**New**
> 3. **Magnitude thresholds are volatility-relative**: any threshold on the size of a price move is set relative to the ticker's volatility, not as a fixed number. (The former Advice formula and its `0.5` coefficient are retired with Advice.)

**Why**: Rule 3 is dormant (review Finding 6): `/insight` is the only user of the formula and `retire-direction-model` removes it. The review's own observation stands: the idea is still right and the band already meets it. Keeping the numbered slot avoids renumbering references in archived specs and docs.

**Known gap, stated rather than hidden**: the Macro agent classifies price moves with fixed numbers: VN-Index slope beyond 0.05% of the mean (`macro.py:67`) and the ticker's 20-session return relative to the index beyond +/-1 point (`macro.py:308`). Under the new text these are not compliant. **Owner accepted this gap on 2026-10-07.** The text is not narrowed to hide it; `KNOWN_ISSUES.md` gets an entry (task 6.9), and retrofitting belongs to the macro-agent owner (`debate-data-guards`) or a later change. The `macro.py:182` comment "Rule 3's 0.5" becomes stale; that is a code comment, out of scope here, handed to the same owner.

**Alternatives**: (a) delete Rule 3 and renumber: breaks references in archived specs. (b) Leave it dormant: a rule about Advice that no longer exists teaches the wrong thing. (c) Narrow the text to "the displayed band": compliant today, but then nothing governs the next threshold anyone adds. (d) Fold into Rule 4: Rule 4 is about reliability, not thresholds.

### Decision 4: Rule 4 becomes the range hit-rate; the vote count is "Agreement" (requires sign-off)

**Old**
> 4. **Confidence score (v1)** = backtested hit-rate over the ticker's most recent ~60 predictions. Not a statistical prediction interval (that's a future quantile-regression upgrade, out of v1 scope).

**New**
> 4. **Reliability is measured, never asserted**: the only reliability figure shown is the range hit-rate, measured from price history and labelled as such. The agent vote count is labelled **Agreement**, never Confidence. The band states its nominal coverage; it is not a guaranteed interval.

**Why**: Rule 4 as written cannot survive the retirement of directional predictions (`DISCUSSION_model_direction.md`, "Consequences"). Interval coverage is the replacement that file named. Agreement is a vote count among agents that share one LLM provider, two of which read the same market backdrop (review Finding 3), so it must not carry the word Confidence. The old clause "not a prediction interval" is dropped because the band now is an empirically calibrated interval-like quantity; the new clause says what that does and does not promise. A quantile-regression challenger stays undecided.

**Definition (owner decision 2026-10-07, set by `calibrate-volatility-range`)**: non-overlapping five-session windows over about the last year, so n is about 50 and the windows are independent; it is displayed as "N of the last M five-session moves". `range_hit_rate` is `{rate, n}` per the shared contract; this change owns the label and the Rule 4 wording, not the maths. The earlier worry about overlapping daily windows (effective sample far below the nominal count) no longer applies to this definition. The rate still carries binomial noise at n about 50 (roughly +/-0.07), which is why n is always shown.

**Alternatives**: (a) keep Rule 4 for a dormant Confidence: contradicts the dashboard once `/insight` goes. (b) Keep Agreement as the Confidence replacement: a vote count is not a calibrated number (archived design Decision 3 already said so). (c) Keep the contract's last ~60 overlapping daily windows (superseded: the owner chose non-overlapping windows over about a year). (d) Require an outcome-tracked verdict hit-rate: no scoreable verdicts exist before about 2026-10-09 and news/macro cannot be backtested; becomes a later refinement via `debate-outcome-log`.

### Decision 5: Rule 5 becomes provenance labelling (requires sign-off)

**Old**
> 5. **"Market Sentiment" is a technical proxy** (RSI, MACD, Ichimoku position), not real news/NLP sentiment. Must be labeled as such in the UI.

**New**
> 5. **Label by provenance**: name each agent for what it reads (Technical Signal, News Context, Macro) and mark language-model text as such. "Market Sentiment" is reserved for the technical proxy (RSI, MACD, Ichimoku) and is never applied to news, macro or a verdict.

**Why**: the News agent is real news analysis (archived design Decision 4 relaxed Rule 5 for it without sign-off); the labels shipped ("Technical Signal", "News Context", "Macro", `debate-panel-ui` spec `:50`) already follow this idea. Stating it as provenance covers the LLM-written reasoning, key tension and synthesis, which the old rule did not.

**Alternatives**: (a) keep the label ban only: silent on LLM text and on the News agent. (b) Retire Rule 5: loses the ban on "Market Sentiment" for non-technical content, which is the point of the M8 caveat in `config.yaml`.

### Decision 6: Rule 6 keeps its meaning; display labels become non-transactional (requires sign-off)

**Old**
> 6. **Never frame output as investment advice.** Use "technical observation" framing and show the disclaimer from `docs/DISCLAIMER.md` (created M6, not before — nothing to disclaim until M6 has UI output) anywhere Advice, Confidence, or Sentiment is displayed.

**New**
> 6. **Never frame output as investment advice.** Use "technical observation" framing. Verdict labels contain no buy, sell, hold or other instruction. Show the disclaimer from `docs/DISCLAIMER.md` wherever a verdict, Agreement, a range or agent reasoning is displayed or exported.

**Display labels** (the shared contract; **accepted by the owner on 2026-10-07**; display strings only, enum values unchanged):

| Enum value (API, unchanged) | Old display | New display |
| --- | --- | --- |
| `STRONG_BUY_SIGNAL` | Strong Buy Signal | Strong bullish lean |
| `BUY_SIGNAL` | Buy Signal | Bullish lean |
| `OBSERVE` | Observe | Observe |
| `CAUTION_SIGNAL` | Caution Signal | Bearish lean |
| `STRONG_CAUTION_SIGNAL` | Strong Caution Signal | Strong bearish lean |
| `SPLIT` | Split — No Consensus (panel), Split (No Consensus) (export) | Split — no consensus |
| `INSUFFICIENT_DATA` (added by `debate-data-guards`) | n/a | Insufficient data |

**Alternatives for the labels**: keep "Buy Signal" (a transaction verb the M5 notes rejected, and it ships in exported files that circulate); "Bullish signal" / "Bearish signal" (keeps "signal", which the retired Advice used as "Signal: up"); "lean" (chosen: hedged, no verb of action, symmetric). Weakness: "lean" is jargon for some retail readers, and "Observe" is itself an imperative verb; the owner accepted both on 2026-10-07 (Open Question 1, resolved). Renaming the enum values to match is a recorded future option, not done here.

### Decision 7: Disclaimer text and a single source with drift tests

**Chosen text** (`docs/DISCLAIMER.md`). The owner's drafts are used with two adjustments, each a factual fix:

Full:
> This analysis shows technical observations, not investment advice. The verdict comes from three automated agents: one reads price indicators (RSI, MACD, Ichimoku), one reads recent Vietnamese financial headlines, and one reads market-wide data (VN-Index, USD/VND, foreign flows). A language model writes the agents' reasoning and revises their positions in a second round, so wording and positions can be wrong or incomplete. The range is a statistical estimate of typical 5-session movement, sized so that about 2 in 3 past moves stayed inside it; larger moves are possible. Nothing here is a recommendation to buy, sell or hold any security.

Inline:
> Technical observation from automated agents and a statistical range — not investment advice.

Adjustments: (1) "This page" becomes "This analysis", because the same text ends exported `.md` files, which are not pages. (2) The coverage clause "sized so that about 2 in 3 past moves stayed inside it" is new: the review measured the shipped band at about a third of real 5-session moves (32.3% in-sample, 33.8% last 12 months; not reproduced here), so a bare "typical movement" would overstate it. "About 2 in 3" is the nominal `range_coverage` target in the shared contract; **it must be checked against the value and method `calibrate-volatility-range` fixes** (task 2.7). I found no other factual error: the agents' inputs match `technical.py` (RSI, MACD histogram, Tenkan/Kijun), `news_feeds.py` (VnExpress, CafeF, Vietstock RSS, 7 days) and `macro.py` (VN-Index, ticker versus VN-Index, USD/VND, foreign flow), and Round 2 can change stances (`technical.py:143-179`).

The old inline text's repo path ("See docs/DISCLAIMER.md") is dropped: the user cannot open it from the UI (review Finding 7).

**Single source and drift test.** `docs/DISCLAIMER.md` keeps two headings, `## Full disclaimer` and `## Inline version`, each followed by one blockquote. Parsing rule used by both tests: take the consecutive lines starting with `>` under the heading, strip the leading `> `, join with one space, collapse whitespace. The frontend copy lives in one module, `frontend/src/lib/disclaimer.js` (proposed by `retire-direction-model`, owner decision 2026-10-07), which exports `INLINE_DISCLAIMER` and `FULL_DISCLAIMER` and is imported by `DebatePanel` and `RangeDisplay`; if this change lands first it creates the module. `export.py` exports `DISCLAIMER_FULL`. `frontend/src/lib/disclaimer.test.js` and `test_debate_export_api.py` read `docs/DISCLAIMER.md` and fail on any difference.

**Alternatives**: import the markdown into the frontend with Vite `?raw` (one copy, but needs `server.fs.allow` for a path outside `frontend/`, and the vitest behaviour is unverified; the copy-plus-test route is cheaper and the brief asks for a test); a generated constants file (a build step for two strings); keep paraphrases (the status quo, which drifted).

### Decision 8: Where the disclaimer shows

**Panel** (placement accepted by the owner 2026-10-07): the inline text stays an always-visible paragraph in every state (not-run, loading, error, populated). Under it a native `<details><summary>About this analysis</summary>` holds the full text. The disclosure only adds text; nothing can hide the inline line, so the existing "no control hides the disclaimer" intent holds. Native `<details>` needs no state or dependency.

**Export**: the report ends with `---` and the full text as one plain paragraph (no italics, no path). A report is read out of context (NotebookLM, shared files), so it carries the full version, not the one-liner.

**Alternatives**: full text always visible in the panel (about 90 words under every result; the panel is a glanceable verdict); inline only (the LLM and range statements would never be shown to the user, which is the gap the review found).

### Decision 9: Neutral verdict wording in the synthesiser prompts and fallback

The tension and synthesis prompts need the vote outcome, not its label. The stance lines already list each agent's Round 2 stance, so the `Verdict: {verdict}` line (`synthesiser.py:70`) and `led to the verdict "{verdict}"` (`:79-87`) are replaced by a vote summary built from the stance counts, for example `2 bullish, 1 neutral, 0 bearish (majority)`. The failure fallback at `:168` (`Verdict: BUY_SIGNAL (...)`, rendered in Level 3 and the report) becomes `Vote: 2 bullish, 1 neutral, 0 bearish.`.

**Alternatives**: pass the display label ("Bullish lean": still a stance word the model may echo as advice); pass a prose description per enum value (a second table to keep in step; the counts carry the same information); scan LLM output for buy/sell and rewrite it (false positives on "net buying", and it hides rather than prevents).

The `debate-synthesiser` mapping requirement's sentence "MUST NOT use the words BUY or SELL as standalone instructions" (`:19`) is superseded by this change's ADDED requirements. It is not edited here because `debate-data-guards` modifies that requirement (the 2-neutral-plus-1 conflict, `INSUFFICIENT_DATA`); that change should drop the sentence when it rewrites the block.

### Decision 10: Language-model note and "Agreement" label

New fixed string, identical in panel and export: `Reasoning, key tension and synthesis are written by a language model.` Panel: top of Level 2 and of Level 3 content. Export: first line under `## Agent Positions`. The Summary (verdict, Agreement, range) carries no note: those are computed (the verdict by a deterministic vote), though Round 2 stances can be LLM-influenced, which the full disclaimer states.

The panel's vote line (`agreementText`, `DebatePanel.jsx:45-53`) gains the prefix: `Agreement: Majority — 2 of 3 agents`, `Agreement: Split — 3 different positions`. The export already prints `**Agreement**:`.

**Alternatives**: mark every bullet (noise); rely on the disclaimer alone (the marking should sit next to the text it describes).

### Decision 11: Case-insensitive guards, scoped to fixed text

Guard regexes, applied to rendered fixed text with the two disclaimer strings removed first (the full text legitimately says "buy, sell or hold" in a negation):
- `/\b(buy|sell|hold)\b/i`
- an enum token: `/[A-Z]+_SIGNAL\b|INSUFFICIENT_DATA/`
- `/\bconfiden(ce|t)\b/i`
- `/market sentiment/i`

Panel test: render every state and every verdict value, at Levels 1 to 3, with fixture text that avoids those words (the existing `MOCK_RESULT` does). Export test: the same for generated reports. Synthesiser test: build both prompts for every stance combination. A parity test asserts every `Verdict` literal value has a label in `export.py` (and the panel list matches the contract table), so a new enum value without a label fails a test instead of rendering raw text. The panel's fallback for an unknown verdict becomes "Unrecognised verdict" instead of the raw enum (`DebatePanel.jsx:227`).

**Why scoped**: LLM-written reasoning may say "foreign net buying"; a guard over it would fail on correct text. Fixed text is the part this project controls.

### Decision 12: Docs sync inventory, each claim verified against the current file

| File | Verified stale claim (HEAD `e77986e`) | Action (group 6) |
| --- | --- | --- |
| `config.yaml:6-11` | "AI insight panel (Confidence, Market Sentiment, Advice)", "Model v1 is a single XGBoost regressor", M7/M8 "not implemented" | Replace with the debate/band description |
| `config.yaml:51-56` | "DATA_DICTIONARY.md doesn't exist yet", "DISCLAIMER.md doesn't exist yet — created in M6" | Both exist (317 and 32 lines); state so |
| `config.yaml:66-95` | no entry for the pivot; `:77-79` "rules 3-6 in effect, not the stubbed contract below" (no contract below) | Add pivot entry, drop the phrase |
| `config.yaml:91-136` | "Current focus: no active milestone"; "single most consequential open item: the served model `pooled_xgb_model.json`... 198 of 208 show Confidence N/A"; known gap "Confidence (rule 4) is backtest-only" | Rewrite: the pivot took Option 3; open items per `DISCUSSION_post_pivot_review.md` |
| `config.yaml:144-148` | M8 "not started" | The News Context agent delivered news-based context (LLM reading of headlines, not a sentiment score) |
| `config.yaml:163-166` | tasks rule about Confidence, Sentiment, Advice | Rewrite to the new Rules 4-6 (gated) |
| `CLAUDE.md:13` | "AI insight panel response contract" in `config.yaml` | None exists; remove the phrase |
| `CLAUDE.md:40-41` | "created M6, not before" | Gone with Rule 6's rewrite (gated) |
| `MODEL_CARD.md:1-14, 108-110, 163-167, 259` | titled the M3 pooled XGBoost, "M6's confidence score (Rule 4) reads"; paths `openspec/changes/xgboost-training-pipeline/` | Retirement banner, fix archive paths, short HAR-RV section that does not cite corr 0.479 (the review says that is a 15-ticker variant; the shipped model measured 0.433 in-sample, 0.431 out-of-time, not reproduced) |
| `DISCUSSION_model_direction.md:574-575` | "open, undecided... still serving predictions" | Dated update: Option 3 taken |
| `DISCUSSION_calendar_staleness.md:46,51` | `ticker-manual-refresh` "still active/unarchived" | Archived 2026-08-12 (`changes/archive/2026-08-12-ticker-manual-refresh/`); fix links; note the dot's fate follows `retire-direction-model` |
| `DISCUSSION_prediction_outcome_tracking.md:66,76-77,95-97,107` | Rule 4 framed as the backtest hit-rate; options about Confidence | Dated update: Rule 4 reframed, points to `debate-outcome-log` |
| `DATA_DICTIONARY.md:7,44,54,155` | pre-archive paths (`openspec/changes/data-ingestion-vnstock/` etc.); no HAR-RV artifact, `reports/` or debate log | Fix paths (dated archive folders); add artifact, reports, `debate_log` |
| `KNOWN_ISSUES.md` | no entry for RSS text in prompts, `claude_cli` subprocess, `pickle.load`, data sent to LLM APIs | Five new entries (task 6.9) |

`CLAUDE.md`'s backlog pointer already covers `docs/DISCUSSION_post_pivot_review.md` by its glob, but the open questions of `974c905` live only in the archived design; one pointer line is added (task 6.2).

New wording for the `config.yaml` context opening (not a rule, no sign-off needed): "Product: web app for Vietnamese HOSE stocks. A HAR-RV volatility model gives a 5-session typical-move band; a three-agent LLM debate (technical, news, macro; two rounds) gives a verdict by deterministic vote over Round 2 stances. The XGBoost return predictor is retired (served until `retire-direction-model` lands; `docs/MODEL_CARD.md`). SageMaker (M7) is not implemented."

**Sequencing**: statements about what is retired or logged are written after the changes that make them true (`retire-direction-model`, `debate-outcome-log`); until then the docs say "tracked by `<change>`".

### Decision 13: Gate the rule edits on a recorded sign-off

`CLAUDE.md` says to stop and ask before changing a rule, and this agent cannot ask. So: the sign-off is task 1.1, recorded in the table below; tasks 5.x (the only ones that edit the rule blocks of `CLAUDE.md` and `config.yaml`) require rows R1-R6 to read approved; task group 3 (labels) requires row L and group 2 (disclaimer) requires row D. Rule texts are not needed for the string work, so owner approval of the labels (row L) does not approve any rule. If the owner edits a text, the edited text goes in the last column and the tasks use it verbatim. Doc edits that are not rules (group 6) need no sign-off but follow the sequencing above.

**Alternatives**: edit first and ask after (what the rule forbids); a separate `signoff.md` (an extra file for eight rows).

### Decision 14: Keep the six rules identical in both files, with a test

`CLAUDE.md` says rules are duplicated in `config.yaml` and "will drift out of sync" otherwise; the review found wording differences. `backend/tests/test_domain_rules_in_sync.py` extracts the six rules from each file, strips `**`, backticks and line wrapping, and fails on any difference. One small test against a documented failure mode; it passes only if the pasted texts match.

## Sign-off record

Rows are filled by the owner (task 1.1). Status values: pending, approved, approved with edits (final text in the last column), rejected.

| Row | Item | Text in | Status | Date | Final text if edited |
| --- | --- | --- | --- | --- | --- |
| R1 | Rule 1 | Decision 1 | approved | 2026-10-07 | |
| R2 | Rule 2 (unchanged) | Decision 2 | approved | 2026-10-07 | |
| R3 | Rule 3 | Decision 3 | approved (shortened text; Macro-agent gap accepted) | 2026-10-07 | |
| R4 | Rule 4 | Decision 4 | approved (shortened text; hit-rate definition accepted) | 2026-10-07 | |
| R5 | Rule 5 | Decision 5 | approved | 2026-10-07 | |
| R6 | Rule 6 | Decision 6 | approved (shortened text) | 2026-10-07 | |
| L | Verdict display labels | Decision 6 table | approved by the owner | 2026-10-07 | |
| D | Disclaimer full and inline | Decision 7 | approved, including the "This analysis" and coverage-clause adjustments; the coverage clause is still re-checked against `calibrate-volatility-range` (task 2.7) | 2026-10-07 | |

Reproduction (task 1.2), `backend/scripts/verify_rules_alignment_claims.py`, run 2026-10-07 against the read-only database: `backtest_predictions` 10191 rows, 10 distinct tickers, last date 2026-08-05, pooled hit-rate 0.477; `ohlcv` 599 distinct tickers, 589 with no backtest row. All six figures equal the review's (0 differ). Task 2.7 (coverage phrase), `evaluate_vol_range.py` run 2026-10-07 against the archived `calibrate-volatility-range` model: `range_coverage` 0.68; measured coverage 68.0% all windows, 70.6% last 12 months, 73.0% out-of-time test, all inside 0.60 to 0.75, so "about 2 in 3" in `DISCLAIMER.md`, `disclaimer.js` and `DISCLAIMER_FULL` stands unchanged. `--docs --expect present`: all 16 stale claims of Decision 12 present before the doc edits.

## Risks / Trade-offs

- **[Sign-off never recorded]** → rule blocks stay stale and the lockstep test stays green; every other task proceeds. The gate is the point.
- **[Wording still reads as advice]** ("Bullish lean") → the labels are the owner's contract, hedged and verb-free; they are product wording, not legal advice; confirm with whoever owns compliance if the app is shown beyond personal use.
- **[Coverage phrase goes stale]** ("about 2 in 3") → checked in task 2.7 against `range_coverage`; any later refit that changes the nominal value must update `DISCLAIMER.md` and the two copies (the tests fail until it does).
- **[Range hit-rate is noisy]** (n about 50 gives roughly +/-0.07) → the UI always shows "N of the last M"; the window definition is `calibrate-volatility-range`'s.
- **[Guard false negatives]** → the guards cover fixed text only; LLM-written text is controlled by prompts (Decision 9) and the News prompt's existing "do not recommend".
- **[Merge conflicts in `DebatePanel.jsx`, `export.py`]** → this change touches string constants and three small spots; siblings touch the range line, new result fields and error text. Conflicts are mechanical; the parity test catches a missed label.
- **[Docs ahead of code]** → sequencing in Decision 12.
- **[Third-party data]** → no new data leaves the machine; the KNOWN_ISSUES entry records what the debate already sends (ticker, indicator values, headlines, macro numbers) and that vendor retention terms were not reviewed.

## Migration Plan

1. Task 1: sign-off and reproduction (read-only).
2. Tasks 2-4: disclaimer, labels, prompts and guards (tests first). No data migration; enum values and API shapes are untouched, so stored data and clients are unaffected. Existing local `reports/*.md` keep the old labels and footer and are not rewritten.
3. Task 5: rule edits in both files together, in one commit, after sign-off.
4. Task 6: remaining docs, after the sibling changes they describe.
5. Task 7: verification and `openspec validate`.

**Rollback**: revert the commits; no schema, API or stored-data change.

## Open Questions

Resolved by the owner on 2026-10-07: (1) the labels, including "lean" and "Observe", are accepted; (2) the full disclaimer sits behind the native "About this analysis" disclosure with the inline text always visible; (3) the Macro agent's fixed thresholds are recorded as a known gap under Rule 3; (4) `range_hit_rate` uses non-overlapping five-session windows over about the last year (n about 50), shown as "N of the last M five-session moves"; (5) the shared frontend disclaimer string lives in `frontend/src/lib/disclaimer.js`.

Still open:

1. **The exact Rule 1-6 texts and the disclaimer wording await owner review** (Sign-off record).
2. No sibling is named as owner of rendering `range_hit_rate` in the panel (`retire-direction-model` plans a `RangeDisplay` component; the label requirement here is conditional "where shown"); the author should confirm when reconciling.
3. Rule 2 and a symmetric "+/-x%" band for a log-space half-width (Decision 2): leave as rounding?
4. The `macro.py:182` comment "Rule 3's 0.5" and the superseded BUY/SELL sentence in the `debate-synthesiser` mapping requirement: handed to `debate-data-guards`.
5. The structure requirement of `debate-report-export` ("Markdown export structure is NotebookLM-optimised") still shows the old one-line footer in its template; it is not modified here because `calibrate-volatility-range` and `debate-data-guards` also modify it. Whichever lands last replaces the template's last line with the full disclaimer.
6. `AIInsightPanel` and `PredictionDisplay` still carry the old inline text until `retire-direction-model` lands; that text is not part of the drift test.
7. Contract deviation: none. `sigma_daily_pct`, `range_5s_pct`, `range_hit_rate`, `INSUFFICIENT_DATA` are used as defined; "Range hit-rate" and "Agreement" are the labels. The hit-rate window is now the non-overlapping year-long definition decided on 2026-10-07 rather than "~60 windows".


## Appendix: longer rule wording (superseded 2026-10-07)

Kept for traceability. These are the first drafts of Rules 1, 3, 4, 5 and 6; they restated detail that the specs already enforce (`volatility-range`: hit-rate definition and windows; `debate-panel-ui`: Agreement and Range hit-rate labels, disclaimer placement, no transaction verbs; `debate-report-export`: footer and verdict label), and ran to 65 to 111 words each against 17 to 36 in the original rules.

- **Rule 1**: **Horizon and outcome**: the horizon is 5 TRADING SESSIONS ahead, not calendar days. The realised outcome that ranges and verdicts are scored against is `outcome_t = ln(close[t+5] / close[t])` (stored as `features.target`). The volatility model's target is the daily sigma of log returns over sessions t+1 to t+5 (the standard deviation of the next five daily log returns), scaled to a 5-session band for display.
- **Rule 3**: **Magnitude thresholds are volatility-relative**: any threshold that classifies the size of a price move (for example "large" or "within the normal range") is expressed relative to a volatility estimate for that ticker (a forecast or a trailing standard deviation), not as a fixed number. The displayed band satisfies this by construction. The former Advice formula and its `0.5` coefficient are retired with Advice. Thresholds on indicator levels (RSI, MACD, Ichimoku) and on non-price quantities are not covered.
- **Rule 5**: **Label by provenance**: each agent is labelled by what it reads: "Technical Signal" (price indicators: RSI, MACD, Ichimoku), "News Context" (recent Vietnamese financial headlines), "Macro" (market-wide data). Text written by a language model is marked as such. "Market Sentiment" is reserved for the technical proxy (RSI, MACD, Ichimoku position): when used it says so, and it is never applied to news, macro or a verdict.
- **Rule 6**: **Never frame output as investment advice.** Use "technical observation" framing. Verdict display labels are non-transactional ("lean", "observe", "split", "insufficient data") and never contain buy, sell, hold or any instruction. Show the disclaimer from `docs/DISCLAIMER.md` anywhere a verdict, Agreement, a range, a range hit-rate or agent reasoning is displayed or exported: the inline version always visible, the full version one step away in the UI and at the end of every exported report.
- **Rule 4**: **Reliability is measured, never asserted**: the only number shown as a reliability measure is the **range hit-rate**: of the ticker's non-overlapping five-session moves over about the last year (about 50), how many had `abs(ln(close[t+5] / close[t]))` inside the band displayed at the time, recomputed from OHLCV history by re-running the model for each date, shown as "N of the last M five-session moves" and labelled "Range hit-rate", never "Confidence". The count of agents holding the majority position is labelled **Agreement**; it counts agents, is not a probability, and is never called Confidence. The band is a calibrated estimate of typical movement with a stated nominal coverage, not a guaranteed prediction interval.
