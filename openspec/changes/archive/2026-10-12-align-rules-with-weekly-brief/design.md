## Context

`CLAUDE.md` (section "Non-Negotiable Domain Rules") and `openspec/config.yaml` (the "Non-negotiable domain rules" block of `context`, plus the `tasks` rule) each carry the same six rules word for word. `backend/tests/test_domain_rules_in_sync.py` fails on any wording difference between the two files, after stripping bold, backticks and line wrapping, and expects exactly six numbered rules in each.

The rules were last rewritten for the debate product (`openspec/changes/archive/2026-10-07-align-rules-and-disclaimer`). Since then the owner decided (2026-10-11, `docs/DISCUSSION_purpose_and_weekly_brief.md`, "Decided by the owner"):

- decision 3: retire Agreement and the vote, with a fixed sentence that the brief does not predict direction;
- decision 5: Rule 6 is relaxed because the tool is for personal, non-commercial use;
- decision 6: scope of that relaxation (yes to plainer wording for the investor's own rules, the investor's own stops and targets reported as reached, and a shorter disclaimer; no tool-originated buy, sell or hold label, except applying the investor's own written rule).

The debate surface (engine, synthesiser, panel, export) is not removed by this change. Four capability specs still require the **Agreement** label and the full disclaimer: `debate-panel-ui`, `debate-synthesiser`, `debate-report-export`, `debate-engine` (and `dashboard-ui` and `debate-outcome-log` mention it). The rule texts below therefore keep a transitional clause so those specs and their tests stay true until the later change that removes the surface.

A review in the same session (risk and privacy) listed what must not be relaxed even for personal use: the ban on a Confidence figure, provenance labels and the model-text note, the injection backstop (`withhold_advice` and prompt fencing), and the "about 2 in 3" coverage phrase in any shortened disclaimer.

## Goals / Non-Goals

**Goals:**
- Put exact, reviewable old-to-new texts for Rules 4, 5 and 6 in front of the owner and edit `CLAUDE.md` and `config.yaml` only after approval.
- Keep both files identical so `test_domain_rules_in_sync.py` passes without edits.
- Keep every existing debate spec and test true (transitional clause).
- Add a short brief disclaimer to `docs/DISCLAIMER.md` for the weekly brief, with a sync rule, without touching the existing full and inline texts.
- Record the governance as a small `domain-rules` spec.

**Non-Goals:**
- Building the brief, or any code (next changes).
- Changing the guard tests' logic (for example the `TRANSACTION_VERBS` scan in `backend/tests/test_debate_export_api.py`): they guard the debate export text, which this change leaves as is. Narrowing them for the brief is part of `add-weekly-holdings-brief`.
- Removing the debate surface, Agreement, or the three agents.
- Resolving the Macro agent's fixed thresholds against Rule 3.
- Legal advice. The personal-use premise is flagged, not decided.

## Decisions

### D1. Rule texts for review (old to new)

Rules 1 to 3 are unchanged and not repeated. New wording of Rules 4, 5 and 6 (cited rule numbers are the existing ones; the "new" parts are marked):

**Rule 4, old:** Reliability is measured, never asserted: the only reliability figure shown is the range hit-rate, measured from price history and labelled as such. The agent vote count is labelled **Agreement**, never Confidence. The band states its nominal coverage; it is not a guaranteed interval.

**Rule 4, new:** Reliability is measured, never asserted: the only reliability figure shown is the range hit-rate, measured from price history and labelled as such, and no figure is called Confidence. The band states its nominal coverage; it is not a guaranteed interval. Output that carries no measured directional edge says in one fixed sentence that it does not predict direction. While the debate verdict is still displayed, its vote count is labelled **Agreement**.

**Rule 5, old:** Label by provenance: name each agent for what it reads (Technical Signal, News Context, Macro) and mark language-model text as such. "Market Sentiment" is reserved for the technical proxy (RSI, MACD, Ichimoku) and is never applied to news, macro or a verdict.

**Rule 5, new:** Label by provenance: name each source for what it reads (Technical Signal, News Context, Macro, and any new source by what it reads) and mark language-model text as such. Anything the investor wrote (levels, notes, rules) is labelled as theirs with its entry date. "Market Sentiment" is reserved for the technical proxy (RSI, MACD, Ichimoku) and is never applied to news, macro or a verdict.

**Rule 6, old:** Never frame output as investment advice. Use "technical observation" framing. Verdict labels contain no buy, sell, hold or other instruction. Show the disclaimer from `docs/DISCLAIMER.md` wherever a verdict, Agreement, a range or agent reasoning is displayed or exported.

**Rule 6, new:** This tool is for the owner's personal, non-commercial use; if anyone else will use or receive its output, restore the old Rule 6 or obtain sign-off first. Output is technical observation and conditions. It makes no unmeasured claim about direction, and the tool never produces its own buy, sell or hold label. Where the tool reports whether a level or rule the investor wrote was reached, the investor's rule text is shown verbatim and labelled as theirs (Rule 5), and the tool's own words in that line are limited to reached or not reached and the distance. Verdict labels contain no buy, sell, hold or other instruction. Show the full disclaimer from `docs/DISCLAIMER.md` wherever a verdict, Agreement or agent reasoning is displayed or exported, and the short brief disclaimer wherever a range or reliability figure is displayed without them; the coverage phrase must match the range's nominal coverage.

Why these edits: each cites an owner decision above and nothing beyond it. Rule 6's new first sentence carries the precondition the owner's "personal use" premise needs; the risk review found that premise unverified.

*Alternative considered:* delete Rule 6 entirely. Rejected: the owner scoped the relaxation (decision 6), and the prohibition on tool-originated labels and unmeasured direction claims rests on the project's own evidence, not on law.

*Alternative considered:* remove Agreement now. Rejected: four specs and their tests require it; removing it belongs with the removal of the debate surface.

### D2. Both files edited in lockstep, structure preserved

The six rules keep their numbers and the "N. " list format so `test_domain_rules_in_sync.py` (`RULE_START = ^\s*([1-6])\.`) still splits them. Edits are made to `CLAUDE.md` first, then pasted into `config.yaml`, and the test is run. `CLAUDE.md`'s own note ("change a rule in BOTH files") stays. The `tasks` rule in `config.yaml` that says "verdict, Agreement, a range, a range hit-rate or language-model-written text must include provenance labels per rule 5, the disclaimer per rule 6, and verdict labels from the `debate-synthesiser` display label table" is reworded to "the disclaimer per rule 6 (full where a verdict, Agreement or agent reasoning is shown, short where only a range or reliability figure is shown)".

### D3. A second disclaimer, not a changed one

`docs/DISCLAIMER.md` is the single source for two guarded copies of the full and inline texts (`frontend/src/lib/disclaimer.js`, `backend/app/services/debate/export.py`). Those texts describe the three-agent verdict and stay unchanged. A new section "Brief disclaimer" holds the short text for the weekly brief:

> Technical observation, not investment advice. Figures can be wrong or incomplete. "About 2 in 3" is an estimate from price history, not a promise.

The coverage phrase in it ("about 2 in 3", read as about 2 weeks in 3 for a weekly brief) is held to the same rule as the other texts: it must match the range's nominal coverage. The exact sync test for the brief copy is written by `add-weekly-holdings-brief`, which creates the first copy; this change only defines the source text and the rule.

*Alternative considered:* edit the full disclaimer to cover both surfaces. Rejected: it would break two existing guard tests and the debate export's verbatim requirement, for text that is about to be removed.

### D4. A small `domain-rules` capability

The governance is made testable: the six rules identical in both files (already enforced by `test_domain_rules_in_sync.py`), the disclaimer single source, and the Rule 6 preconditions. The spec cites rule numbers and does not repeat the rule text, so the words live only in the two files the test already compares.

*Alternative considered:* no spec (the previous rules change added requirements to debate specs). Rejected: this change touches no debate behavior, so there is nothing to attach requirements to, and the spec step would be empty.

### D5. Sign-off gate

Task 1.1 shows the owner the texts in D1 and records approval (date and wording) in this file under "Sign-off record". Tasks that edit `CLAUDE.md` and `config.yaml` are blocked until that record exists, as in the 2026-10-07 change.

## Risks / Trade-offs

- **[The personal-use premise is unverified]** (account and machine ownership; vnstock is licensed "personal, research, non-commercial"; `company_feed_log.db` is marked not to be shared) → Rule 6's first sentence makes the precondition explicit; the owner confirms with legal or compliance before anyone else receives the output. Factual flag, not legal advice.
- **[Transitional clause becomes permanent]** the Agreement clause could outlive the debate surface → the later removal change must delete it, and `design.md` of that change must cite this clause.
- **[A looser Rule 6 invites wording drift]** "plain decision-support wording" was judged undefined by the review → the rule limits it to lines reporting the investor's own rule, labelled as theirs; no new wording is allowed outside that.
- **[Two files can drift]** → the existing sync test; edits are applied to both in one task and the test run immediately.
- **[Short disclaimer lacks the agent description]** → it is used only where no verdict or agent reasoning is displayed.

## Migration Plan

Edit `CLAUDE.md`, then `config.yaml`, then `docs/DISCLAIMER.md`; run `backend/tests/test_domain_rules_in_sync.py` and the disclaimer tests (`frontend/src/lib/disclaimer.test.js`, `backend/tests/test_debate_export_api.py`) to confirm nothing else changed. Rollback is a revert of the three files. No data, API or code is touched.

## Open Questions

- Exact short disclaimer wording and where the canonical coverage phrase is checked (settled in `add-weekly-holdings-brief`).
- Whether to confirm the personal-use premise now or at the first use by anyone other than the owner.

## Sign-off record

**Task 1.1, 2026-10-11, owner approval of the D1 texts after a walk-through:**
- Rule 4 new text: approved as written.
- Rule 5 new text: approved, with the investor-written entry-date labelling kept in Rule 5 (not only in the brief's spec).
- Rule 6 new text: approved **with the tightening** now in D1 (the tool's own words in a line about the investor's own level or rule are limited to reached or not reached and the distance; the investor's rule text is shown verbatim and labelled as theirs).
- Rules 1 to 3: honored unchanged.

**Task 1.2 (personal-use premise), 2026-10-11: deferred.** The owner stated that the tool is internal and non-commercial. Account and machine ownership, the vendor licence ("personal, research, non-commercial") and the company-feed log's "not to be shared" note were not confirmed in this session. The premise is therefore carried by Rule 6's first sentence: confirm it with legal or compliance **before anyone other than the owner receives the output or it runs on employer equipment or accounts.** This is a factual flag, not legal advice.

**Task 4.1 findings, 2026-10-11:** literal quotes of the old Rule 4 or 6 wording remain only in archived changes (historical, left alone), in this change's own D1, and in one code docstring (`backend/app/services/debate/prompt_safety.py:2`, "Rule 6: never frame output as investment advice"). That docstring describes the model prompt withholding advice, which still holds under the new Rule 6, and this change may not edit code; it is left as is.
