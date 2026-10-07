// Verbatim copies of the two blockquotes in docs/DISCLAIMER.md (Rule 6).
// disclaimer.test.js fails if either differs from the file; edit all together.

export const INLINE_DISCLAIMER =
  'Technical observation from automated agents and a statistical range — not investment advice.'

export const FULL_DISCLAIMER =
  'This analysis shows technical observations, not investment advice. The verdict comes from ' +
  'three automated agents: one reads price indicators (RSI, MACD, Ichimoku), one reads recent ' +
  'Vietnamese financial headlines, and one reads market-wide data (VN-Index, USD/VND, foreign ' +
  "flows). A language model writes the agents' reasoning and revises their positions in a second " +
  'round, so wording and positions can be wrong or incomplete. The range is a statistical ' +
  'estimate of typical 5-session movement, sized so that about 2 in 3 past moves stayed inside ' +
  'it; larger moves are possible. Nothing here is a recommendation to buy, sell or hold any ' +
  'security.'

// Shown above LLM-written text (Rule 5); identical in the export (export.py).
export const LM_NOTE = 'Reasoning, key tension and synthesis are written by a language model.'
