## MODIFIED Requirements

### Requirement: Disclaimer appears at the bottom of every exported report (Rule 6)
Every exported `.md` file SHALL end with a `---` rule followed by the full disclaimer from `docs/DISCLAIMER.md` (the blockquote under "Full disclaimer"), written as one plain paragraph that is the last non-empty line, with no italics and no repo path (Rule 6). This replaces the last line of the template in "Markdown export structure is NotebookLM-optimised". The text SHALL equal the file's text after whitespace normalisation (blockquote lines joined with one space, whitespace collapsed), and a test SHALL fail if it does not. The footer MUST be present regardless of verdict.

#### Scenario: Disclaimer in export
- **WHEN** any `.md` report is generated
- **THEN** the last non-empty line is the full disclaimer text, unconditionally

#### Scenario: Footer matches the source file
- **WHEN** the export test reads `docs/DISCLAIMER.md` and a generated report
- **THEN** the report's last non-empty line equals the normalised "Full disclaimer" text, and the test fails if the file or the exporter's copy is edited alone

#### Scenario: Old one-line footer is gone
- **WHEN** a report is generated
- **THEN** it does not contain `See docs/DISCLAIMER.md`

## ADDED Requirements

### Requirement: Report verdict line uses the display label (Rule 6)
The `**Verdict**:` line of the Summary SHALL show the verdict's display label from the table in the `debate-synthesiser` capability ("Verdict display labels are non-transactional (Rule 6)"), never the enum text. The Agreement line keeps the word "Agreement"; the report SHALL NOT use the word "Confidence" in fixed text.

#### Scenario: Label for each verdict
- **WHEN** a report is generated for `BUY_SIGNAL`
- **THEN** the Summary reads `**Verdict**: Bullish lean` and does not contain `BUY_SIGNAL`

#### Scenario: Split label
- **WHEN** a report is generated for `SPLIT`
- **THEN** the Summary reads `**Verdict**: Split — no consensus`

### Requirement: Report marks language-model-written sections (Rule 5)
The first line under the `## Agent Positions` heading SHALL be `Reasoning, key tension and synthesis are written by a language model.`, the same string the panel shows.

#### Scenario: Note present
- **WHEN** a report is generated
- **THEN** the line directly after `## Agent Positions` is that sentence

### Requirement: Fixed report text contains no transaction verbs (Rule 6)
All fixed report text (headings, labels, notes, verdict label), excluding the disclaimer footer and the agents' own reasoning, SHALL NOT contain "buy", "sell" or "hold" as whole words in any letter case, nor any verdict enum text.

#### Scenario: Guard over every verdict
- **WHEN** a report is generated for each verdict value from a fixture whose agent text avoids those words, and the footer is removed
- **THEN** a case-insensitive search for `\b(buy|sell|hold)\b` and for `[A-Z]+_SIGNAL` finds nothing
