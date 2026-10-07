## ADDED Requirements

### Requirement: Verdict display labels are non-transactional (Rule 6)
Every verdict enum value SHALL have exactly one display label, and the panel and the exported report SHALL show that label instead of the enum text. Enum values (the API contract) do not change. The labels are:

| Enum value | Display label |
| --- | --- |
| `STRONG_BUY_SIGNAL` | Strong bullish lean |
| `BUY_SIGNAL` | Bullish lean |
| `OBSERVE` | Observe |
| `CAUTION_SIGNAL` | Bearish lean |
| `STRONG_CAUTION_SIGNAL` | Strong bearish lean |
| `SPLIT` | Split — no consensus |
| `INSUFFICIENT_DATA` | Insufficient data |

No display label SHALL contain "buy", "sell" or "hold" as a whole word, in any letter case. This requirement supersedes the sentence about "BUY" and "SELL" "as standalone instructions" in "Synthesiser maps Round 2 stances to a verdict and agreement level".

#### Scenario: Every enum value has a label
- **WHEN** the set of values of the `Verdict` type is compared with the label table used by the export
- **THEN** the two sets are equal, so a new enum value without a label fails a test

#### Scenario: Labels carry no transaction verb
- **WHEN** each display label is checked case-insensitively for the whole words "buy", "sell" and "hold"
- **THEN** none is found

#### Scenario: Enum values are unchanged
- **WHEN** the debate endpoint returns a result whose majority is bullish
- **THEN** `verdict` is `BUY_SIGNAL` and only the display label reads "Bullish lean"

### Requirement: Synthesiser prompts and fallback text describe the vote neutrally (Rule 6)
The key-tension prompt, the synthesis-summary prompt and the synthesis fallback text SHALL describe the outcome by stance counts and agreement level (for example `2 bullish, 1 neutral, 0 bearish (majority)`), and SHALL NOT contain verdict enum text or the words "buy", "sell" or "hold".

#### Scenario: Prompts contain no enum text for any stance combination
- **WHEN** both prompts are built for every combination of three Round 2 stances
- **THEN** neither contains an enum value (such as `BUY_SIGNAL`) nor, case-insensitively, the whole words "buy", "sell" or "hold"

#### Scenario: Synthesis fallback shows the vote, not the enum
- **WHEN** the synthesis LLM call fails for a debate whose Round 2 stances are bull, bull, neutral
- **THEN** the returned reasoning reads `Vote: 2 bullish, 1 neutral, 0 bearish.` and contains no enum text
