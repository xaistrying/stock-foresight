## 1. Sign-off (blocks every edit to CLAUDE.md and config.yaml)

- [x] 1.1 (Approved 2026-10-11; see "Sign-off record" in `design.md`.) Show the owner the old-to-new texts of Rules 4, 5 and 6 in `design.md` D1. Record the approval (date, and the approved wording if it changed) under "Sign-off record" in `design.md`. If the owner asks for edits, change D1 first and re-confirm. Domain rules 4, 5 and 6 require this sign-off; Rules 1 to 3 are honored unchanged.
- [x] 1.2 Record in `design.md` the state of the "personal use" premise on that date (confirmed, or deferred until anyone other than the owner will receive output), and the owner's one-line statement of it. This is a factual record, not legal advice.

## 2. Edit the rules (only after 1.1)

- [x] 2.1 Edit Rules 4, 5 and 6 in `CLAUDE.md` to the approved text. Keep the six numbered items, their numbers and the "N. " format so the sync test still splits them. Leave Rules 1 to 3 untouched.
- [x] 2.2 Paste the identical Rules 4, 5 and 6 into the "Non-negotiable domain rules" block of `openspec/config.yaml`. Reword the `tasks` rule that says "verdict, Agreement, a range, a range hit-rate or language-model-written text must include (a) provenance labels per rule 5, (b) the disclaimer per rule 6, and (c) verdict labels from the `debate-synthesiser` display label table" so it names the full disclaimer for a verdict, Agreement or agent reasoning and the short one where only a range or reliability figure is shown.
- [x] 2.3 Run `backend/tests/test_domain_rules_in_sync.py` and confirm it passes without any change to the test.
- [x] 2.4 Re-read the intro of `CLAUDE.md` ("It intentionally duplicates the six domain rules below...") and the "Open Discussions and Backlog" pointer; confirm they are still accurate, and fix a line only if it quotes a rule's old wording.

## 3. Disclaimer source

- [x] 3.1 Add a "Brief disclaimer" section to `docs/DISCLAIMER.md` with the text in `design.md` D3, and extend the intro to say the file holds three texts (full, inline, brief), which Rule 6 text each belongs to, and that a copy of the brief text needs its own guard test written by the change that creates the copy. Leave the existing full and inline texts byte-for-byte unchanged.
- [x] 3.2 Run the existing disclaimer guards and confirm they pass unchanged: `frontend/src/lib/disclaimer.test.js` and the disclaimer checks in `backend/tests/test_debate_export_api.py`.

## 4. Verification and records

- [x] 4.1 Search the repo's docs and specs for text that quotes the old Rule 4, 5 or 6 wording literally (for example "Verdict labels contain no buy, sell, hold" or "The agent vote count is labelled Agreement, never Confidence"). List each hit in the change notes; edit only where the quote would now be false, and leave the debate specs alone (the transitional clause keeps them true).
- [x] 4.2 Run `openspec validate align-rules-with-weekly-brief --strict` and fix any finding.
- [x] 4.3 Add a status line to `docs/DISCUSSION_purpose_and_weekly_brief.md` recording that the rules change was applied, with the date and the sign-off reference.
- [x] 4.4 On archive, confirm the `domain-rules` spec is synced into `openspec/specs/`, and note in the archive that the Agreement clause of Rule 4 and the "agreement label is transitional" requirement must be deleted by the change that removes the debate surface. **Done (2026-10-12):** archived with the spec synced to `openspec/specs/domain-rules/spec.md` (4 requirements added). **Carry-over for the change that removes the debate surface:** it must delete the Agreement clause of Rule 4 (in `CLAUDE.md` and `openspec/config.yaml`, identically) and the requirement "The agreement label is transitional" from `openspec/specs/domain-rules/spec.md`, and re-run `backend/tests/test_domain_rules_in_sync.py`.
