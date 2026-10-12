# Disclaimer

This file is the single source of truth for the disclaimer text (domain Rule 6
in `CLAUDE.md`). Two verbatim copies exist and are guarded by tests that fail
on any difference after whitespace normalisation (blockquote lines joined with
one space, whitespace collapsed):

- `frontend/src/lib/disclaimer.js` (`INLINE_DISCLAIMER`, `FULL_DISCLAIMER`),
  checked by `frontend/src/lib/disclaimer.test.js`;
- `backend/app/services/debate/export.py` (`DISCLAIMER_FULL`), checked by
  `backend/tests/test_debate_export_api.py`.

To change the wording: edit the blockquotes below, then paste the same text
into both copies. The tests fail until all three agree. The coverage phrase
("about 2 in 3") must also match the range's nominal coverage.

The panel always shows the inline version and puts the full version behind
"About this analysis"; exported reports end with the full version.

This file holds three texts. The **full** and **inline** texts describe the
three-agent verdict and are shown wherever a verdict, Agreement or agent
reasoning is displayed or exported (Rule 6). The **brief** text, at the end of
this file, is shown wherever only a range or reliability figure is displayed
(the weekly holdings brief). A copy of the brief text elsewhere in the
repository needs its own test that compares it with the section below; the
change that creates the first copy writes that test.

## Full disclaimer

> This analysis shows technical observations, not investment advice. The
> verdict comes from three automated agents: one reads price indicators (RSI,
> MACD, Ichimoku), one reads recent Vietnamese financial headlines, and one
> reads market-wide data (VN-Index, USD/VND, foreign flows). A language model
> reads the news headlines and writes the News Context agent's reasoning and
> position; the other two agents report computed values. Wording and positions
> can be wrong or incomplete. The range is a statistical estimate of typical
> 5-session movement, sized so that about 2 in 3 past moves stayed inside it;
> larger moves are possible. Nothing here is a recommendation to buy, sell or
> hold any security.

## Inline version

> Technical observation from automated agents and a statistical range — not investment advice.

## Brief version

> Technical observation, not investment advice. Figures can be wrong or incomplete. "About 2 weeks in 3" is an estimate from price history, not a promise.
