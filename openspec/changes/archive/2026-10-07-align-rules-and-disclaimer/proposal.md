## Why

The product moved from an XGBoost return predictor with Confidence, Market Sentiment and Advice to a HAR-RV volatility band plus a three-agent LLM debate whose verdict is a vote. The rules, the disclaimer, the verdict wording and the docs still describe the old product: `CLAUDE.md` and `openspec/config.yaml` tell every session the app has an "AI insight panel (Confidence, Market Sentiment, Advice)", `docs/DISCLAIMER.md` describes a "statistical model" and a backtested hit-rate, and the debate panel and the exported reports label verdicts "Strong Buy Signal" / "Buy Signal" — wording the M5 notes (`docs/M5_DASHBOARD_EXPLORE_NOTES.md:185-188`) rejected, and that the old test guard `/\bBUY\b/` (`AIInsightPanel.test.jsx:255`) is too narrow to catch. The 2026-10-06 post-pivot review (`docs/DISCUSSION_post_pivot_review.md`, Findings 6 and 7) found Rules 1, 3, 4 and 5 each need a ruling, and that the archived debate change flagged Rule 4 and Rule 5 as "requires sign-off" without a sign-off ever being recorded.

CLAUDE.md says a rule change must be made in both `CLAUDE.md` and `openspec/config.yaml`, and that work stops and asks first. This change therefore proposes the exact new rule texts for the owner to approve, and gates every edit to those two files behind a recorded sign-off.

## What Changes

- **Rule texts (proposal only until signed off)**, written out old to new in `design.md`:
  - Rule 1 keeps `ln(close[t+5]/close[t])` but becomes the realised 5-session outcome that bands and verdicts are scored against; the volatility model's target is the daily sigma over the next 5 sessions.
  - Rule 2 unchanged.
  - Rule 3 loses Advice and the `0.5 x rolling_std(60)` formula; the surviving idea is re-homed in the same slot as "any magnitude threshold on a price move is volatility-relative".
  - Rule 4: Confidence becomes the **range hit-rate** (of the non-overlapping five-session moves over about the last year, about 50, how many stayed inside the displayed band, measured from history and shown as "N of the last M five-session moves"). The agent vote count is labelled **Agreement** and is never called Confidence.
  - Rule 5 becomes a provenance rule: label each agent by what it reads, say when text is LLM-written, reserve "Market Sentiment" for the technical proxy.
  - Rule 6 keeps its meaning; display labels become non-transactional ("Bullish lean" ... "Bearish lean", "Observe", "Split — no consensus", "Insufficient data"); enum values do not change.
- **Disclaimer**: rewrite `docs/DISCLAIMER.md` (full and inline versions) for the debate product; the frontend copy lives in `frontend/src/lib/disclaimer.js` (shared with `RangeDisplay`), `export.py` holds the other, and a test in each stack fails if a copy drifts from the file. The panel shows the inline text always and the full text one click away; exported reports end with the full text.
- **Labels** (display strings only): verdict labels in `DebatePanel.jsx` and `export.py`, the "Agreement" label, a one-line "reasoning is written by a language model" note, neutral verdict descriptions in the synthesiser prompts (today they receive raw `BUY_SIGNAL` text), and case-insensitive guard tests for the panel, the export and the prompts.
- **Docs sync** (tasks, gated where they touch rules): `CLAUDE.md` and `config.yaml` in lockstep, `MODEL_CARD.md` retirement note, status lines in three `DISCUSSION_*.md` files, `DATA_DICTIONARY.md`, and new `KNOWN_ISSUES.md` entries for RSS text in LLM prompts, the `claude_cli` subprocess, `pickle.load` of the model file, and ticker/indicator context sent to third-party LLM APIs.
- **Guard against recurrence**: a small test that fails when the six rule texts in `CLAUDE.md` and `config.yaml` differ.
- No change to enum values, API shapes, the vote logic, or any code outside label and disclaimer strings and their tests.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `debate-panel-ui`: ADDED requirements only (neutral verdict labels, Agreement label, range hit-rate label where shown, inline disclaimer verbatim plus a full-disclaimer disclosure, LLM-text note, no transaction verbs in fixed panel text). No existing requirement is modified, to avoid colliding with sibling changes that touch this spec.
- `debate-report-export`: MODIFIED "Disclaimer appears at the bottom of every exported report (Rule 6)" (the full disclaimer, verbatim, replaces the one-line italic text); ADDED requirements for verdict display labels and the LLM-text note in reports.
- `debate-synthesiser`: ADDED requirements for the non-transactional verdict display label table and for neutral verdict descriptions in the prompts and in the synthesis fallback text. The existing mapping requirement is left untouched.

## Impact

- **Domain rules touched** (config.yaml rule for proposals): Rule 1 requires sign-off (role change); Rule 2 honored unchanged; Rule 3 requires sign-off (retired with Advice, principle re-homed); Rule 4 requires sign-off (replacement); Rule 5 requires sign-off (rewritten as provenance); Rule 6 requires sign-off (meaning kept, display labels and disclaimer coverage widened). **Nothing in this change edits `CLAUDE.md` or `openspec/config.yaml` before the owner records approval of the exact texts (task 1.1). As of 2026-10-07 the owner has accepted the verdict labels, the disclaimer placement, the Macro-agent gap and the hit-rate definition, but has not yet read the final Rule 1-6 texts: the sign-off for those stays pending, and `design.md` opens with a one-table "Rule texts for review".**
- **Code (strings and tests only)**: `frontend/src/components/DebatePanel/DebatePanel.jsx` and its test; `backend/app/services/debate/export.py` and `synthesiser.py`; `backend/tests/test_debate_export_api.py`, `test_debate_agents.py`, a new `backend/tests/test_domain_rules_in_sync.py`; a read-only script `backend/scripts/verify_rules_alignment_claims.py`.
- **Docs**: `docs/DISCLAIMER.md`, `CLAUDE.md`, `openspec/config.yaml`, `docs/MODEL_CARD.md`, `docs/DATA_DICTIONARY.md`, `docs/KNOWN_ISSUES.md`, `docs/DISCUSSION_model_direction.md`, `docs/DISCUSSION_calendar_staleness.md`, `docs/DISCUSSION_prediction_outcome_tracking.md`.
- **Sibling changes and ordering** (drafted in parallel; the author reconciles):
  - `calibrate-volatility-range`: the coverage sentence in the disclaimer ("about 2 in 3") and the range hit-rate definition in Rule 4 depend on the `range_coverage` value and method it fixes; apply the coverage-dependent wording after it, or re-check it against its measured value. That change owns the range line in the export, the "typical 5-session move" label and the rendering of `range_hit_rate`.
  - `retire-direction-model`: removes `AIInsightPanel`, `PredictionDisplay`, `/insight` and the dashboard-ui requirements for Confidence, Advice and the old disclaimer. This change's doc-sync tasks that describe XGBoost as retired from serving run after it; `DISCLAIMER.md` describes only the debate surface, so any `AIInsightPanel` copy of the old inline text that is still in the tree when this lands is left for that change to delete.
  - `debate-data-guards`: adds the `INSUFFICIENT_DATA` verdict value and result fields. This change owns only its display label ("Insufficient data") and adds a test that every verdict enum value has a label; whichever lands second reconciles `VERDICT_CONFIG` / `VERDICT_DESCRIPTIONS`. It also owns the mapping requirement in `debate-synthesiser` whose sentence about "BUY"/"SELL" this change supersedes, and the stale `macro.py:182` comment that refers to "Rule 3's 0.5".
  - `debate-outcome-log`: `DATA_DICTIONARY.md` and the outcome-tracking discussion status are updated after its table exists.
  - `harden-debate-runtime`: owns news prompt fencing and the failure-text fixes; the `KNOWN_ISSUES.md` entries here point to it. Both changes edit `DebatePanel.jsx`, in different places.
- **Not decided here, out of scope**: renaming the enum values (recorded as a future option), Watchlist curation, a quantile-XGBoost challenger, cross-sectional work, a scheduler, a multi-ticker verdict Rail.
