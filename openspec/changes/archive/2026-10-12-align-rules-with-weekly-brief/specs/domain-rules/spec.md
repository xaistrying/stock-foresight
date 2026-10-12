## ADDED Requirements

### Requirement: The six domain rules are identical in CLAUDE.md and config.yaml
`CLAUDE.md` (section "Non-Negotiable Domain Rules") and `openspec/config.yaml` (the "Non-negotiable domain rules" block) SHALL each state exactly six numbered rules, and rule N SHALL read the same in both files after stripping bold, backticks and line wrapping. A change to any rule SHALL be made in both files in the same change, after the owner has approved the exact text, and SHALL name the rule number it touches.

#### Scenario: A rule differs between the two files
- **WHEN** the text of any of Rules 1 to 6 differs between `CLAUDE.md` and `openspec/config.yaml`
- **THEN** `backend/tests/test_domain_rules_in_sync.py` fails and names the rule number

#### Scenario: A rule is edited without sign-off
- **WHEN** a change edits a rule text and its `design.md` has no recorded owner approval of that text
- **THEN** the edit tasks are not started until the sign-off record exists

### Requirement: The disclaimer has one source and every copy is guarded
`docs/DISCLAIMER.md` SHALL be the single source of disclaimer text. It SHALL hold the full and inline texts (shown with a verdict, Agreement or agent reasoning) and a short brief disclaimer (shown with a range or reliability figure when none of those is shown). Each verbatim copy of a text elsewhere in the repository SHALL be checked by a test that fails when the copy differs from the source after whitespace normalisation, and the coverage phrase SHALL match the range's nominal coverage.

#### Scenario: A copy of the full or inline text drifts
- **WHEN** `frontend/src/lib/disclaimer.js` or `backend/app/services/debate/export.py` differs from `docs/DISCLAIMER.md`
- **THEN** the existing frontend or backend disclaimer test fails

#### Scenario: A copy of the brief disclaimer is added
- **WHEN** a module adds a copy of the brief disclaimer
- **THEN** the same change adds a test that compares it with the "Brief disclaimer" section of `docs/DISCLAIMER.md`

### Requirement: The advice relaxation is limited to the investor's own rules
Rule 6 SHALL apply as relaxed only for the owner's personal, non-commercial use. The tool SHALL NOT produce its own buy, sell or hold label and SHALL NOT make a claim about price direction that has no measured edge against a base rate. Where the tool reports whether a level or rule the investor wrote was reached, the investor's rule text SHALL be shown verbatim and labelled as theirs with its entry date, and the tool's own words in that line SHALL be limited to reached or not reached and the distance. The ban on any figure called Confidence, the provenance labels with the language-model note, and the prompt-injection safeguards SHALL stay in force.

#### Scenario: A line reports the investor's own level
- **WHEN** the output states that a level the investor entered was reached
- **THEN** the line is labelled as the investor's own with its entry date and carries no direction claim

#### Scenario: The tool would originate a label
- **WHEN** any code path would show a buy, sell or hold label that did not come from a rule the investor wrote
- **THEN** it is not shown, and a guard test over fixed tool text fails if such a word appears outside a block labelled as the investor's own

### Requirement: The agreement label is transitional
While the debate verdict is displayed, its vote count SHALL be labelled **Agreement** and SHALL NOT be called Confidence. When the debate surface is removed, the change that removes it SHALL remove this requirement and the corresponding clause in Rule 4.

#### Scenario: The debate verdict is shown
- **WHEN** a screen or export shows the debate vote count
- **THEN** it is labelled Agreement and never Confidence

#### Scenario: The debate surface is removed
- **WHEN** a change removes the debate verdict from every screen and export
- **THEN** that change deletes this requirement and the Agreement clause of Rule 4 in both rule files
