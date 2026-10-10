// Verbatim copies of the two blockquotes in docs/DISCLAIMER.md (Rule 6).
// disclaimer.test.js fails if either differs from the file; edit all together.

export const INLINE_DISCLAIMER =
  'Technical observation from automated agents and a statistical range — not investment advice.'

export const FULL_DISCLAIMER =
  'This analysis shows technical observations, not investment advice. The verdict comes from ' +
  'three automated agents: one reads price indicators (RSI, MACD, Ichimoku), one reads recent ' +
  'Vietnamese financial headlines, and one reads market-wide data (VN-Index, USD/VND, foreign ' +
  "flows). A language model reads the news headlines and writes the News Context agent's " +
  'reasoning and position; the other two agents report computed values. Wording and positions ' +
  'can be wrong or incomplete. The range is a statistical estimate of typical 5-session ' +
  'movement, sized so that about 2 in 3 past moves stayed inside it; larger moves are possible. ' +
  'Nothing here is a recommendation to buy, sell or hold any security.'

// Shown above the agents' reasoning (Rule 5): only News Context is model text. Identical in the export
// (export.py), which a test pins from each side.
export const LM_NOTE =
  'News Context reasoning is written by a language model; Technical Signal and Macro reasoning are computed values.'
