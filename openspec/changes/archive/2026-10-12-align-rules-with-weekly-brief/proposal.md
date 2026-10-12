## Why

The product's purpose has been narrowed (owner decision, 2026-10-11, `docs/DISCUSSION_purpose_and_weekly_brief.md`) to a **weekly risk-and-awareness brief for stocks the owner holds**, with no tool-made direction verdict. The six domain rules in `CLAUDE.md` and `openspec/config.yaml` still describe the debate verdict: Rule 4 makes the vote count a labelled "Agreement", Rule 5 names the three agents, and Rule 6 forbids any buy, sell or hold wording even though the owner has ruled that the tool is for personal, non-commercial use and that it may report whether the investor's *own* written levels were reached. The weekly brief (the next changes) cannot be built under the rules as written without silent exceptions, and `CLAUDE.md` says to stop and ask before changing a rule. This change records the exact new rule texts, gets them signed off, and edits both files together.

## What Changes

Domain-rule honoring (config rule for proposals):

- **Rule 1 (horizon and outcome)**: honored unchanged.
- **Rule 2 (no raw log return)**: honored unchanged.
- **Rule 3 (volatility-relative thresholds)**: honored unchanged. The Macro agent's fixed thresholds stay an open tension, left to the later change that removes the debate surface.
- **Rule 4 (reliability measured)**: **requires sign-off**. Keep "the only reliability figure shown is the range hit-rate, measured and labelled"; keep "never Confidence"; keep the nominal-coverage statement. Add a fixed sentence that output carrying no measured directional edge says it does not predict direction. Keep the **Agreement** label only as a transitional clause for as long as the debate verdict is displayed, because the debate specs (`debate-panel-ui`, `debate-synthesiser`, `debate-report-export`, `debate-engine`) still require it.
- **Rule 5 (label by provenance)**: **requires sign-off**. Keep naming each source for what it reads and marking language-model text. Add that anything the investor wrote (levels, notes, rules) is labelled as theirs, with the date. Keep the reservation of "Market Sentiment" for the technical proxy.
- **Rule 6 (not investment advice)**: **requires sign-off**. Relax, for the owner's personal, non-commercial use only: the tool may report whether a level or rule *the investor wrote* was reached: the investor's rule text is shown verbatim and labelled as theirs, and the tool's own words in that line are limited to reached or not reached and the distance. It still makes no unmeasured claim about direction and never produces its own buy, sell or hold label. A short disclaimer is required wherever a range or reliability figure is shown; the full disclaimer stays where a verdict, Agreement or agent reasoning is shown. Add the precondition that if anyone other than the owner will use or receive the output, the owner restores Rule 6 or obtains sign-off first.
- Both rule files are edited in lockstep (`backend/tests/test_domain_rules_in_sync.py` fails on any difference), and the `tasks` rule in `config.yaml` that cites "verdict, Agreement" is updated to match.
- `docs/DISCLAIMER.md` gains a second, **short brief disclaimer** and its sync rule. The existing full and inline texts are unchanged (they describe the debate surface and stay guarded by their current tests).
- A new `domain-rules` capability records the governance as testable requirements (rules identical in both files; the disclaimer single source with guarded copies; the relaxation preconditions), by rule number and not by repeating the rule text.
- **No code, label or test-logic change.** The brief itself, its guard tests (for example narrowing the `TRANSACTION_VERBS` scan so the investor's own rule is shown verbatim in a separate block), and the removal of the debate surface belong to later changes.

Sign-off gate: the owner's 2026-10-11 decisions fix the direction; **no edit to `CLAUDE.md` or `openspec/config.yaml` happens before the owner approves the exact texts in `design.md` (task 1.1).**

## Capabilities

### New Capabilities
- `domain-rules`: how the six domain rules are kept (identical in `CLAUDE.md` and `config.yaml`), how the disclaimer text is sourced and guarded (full, inline and brief variants), and the conditions attached to the Rule 6 relaxation.

### Modified Capabilities
<!-- none: the debate specs keep requiring the Agreement label and the full disclaimer, which the transitional clause preserves. -->

## Impact

- **Files edited after sign-off**: `CLAUDE.md`, `openspec/config.yaml` (the six rules and the `tasks` rule), `docs/DISCLAIMER.md` (adds the brief disclaimer and sync rule). `docs/DISCUSSION_purpose_and_weekly_brief.md` gets a status line.
- **Tests**: `backend/tests/test_domain_rules_in_sync.py` must still pass unchanged (the structure of the six numbered rules is kept). No new test runs against code in this change; the brief-disclaimer guard is added by the change that creates the first copy (`add-weekly-holdings-brief`).
- **Existing specs and code**: untouched. Anything that still displays Agreement or the full disclaimer keeps conforming.
- **Dependencies and ordering**: independent of the other weekly-brief changes. `add-weekly-holdings-brief` (wording) depends on the signed-off texts; it can be drafted in parallel but is applied after this change.
- **Risk and open points** (full list in `design.md`): the "personal use" premise is unverified (account and machine ownership, the vendor licence, and the company-feed log's "not to be shared" note); the owner should confirm with legal or compliance before anyone else receives the output. This is a factual flag, not legal advice.
