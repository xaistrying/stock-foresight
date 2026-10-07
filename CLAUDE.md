# CLAUDE.md

This file loads automatically at session start, in plain chat, and during
`/opsx:explore` — none of which call `openspec instructions`, so none of
them see `openspec-project-context.yaml`'s `context`/`rules` fields. This
file exists specifically to cover that gap.

It intentionally duplicates the six domain rules below. If you change a
rule, change it in BOTH this file and `openspec/config.yaml`, or
they will drift out of sync.

Everything else — full tech stack, commands, repository structure and
milestone status — lives in `openspec/config.yaml`. That file is the
source of truth for anything not listed here, and loads automatically
during `/opsx:propose`, `/opsx:continue`, and `/opsx:ff`
(proposal/design/tasks generation).

## Non-Negotiable Domain Rules

If a task in ANY mode — explore, plain chat, or formal OpenSpec artifact
generation — seems to require changing one of these, stop and ask first
rather than silently changing it.

1. **Horizon and outcome**: the horizon is 5 TRADING SESSIONS ahead,
   not calendar days. Ranges and verdicts are scored against the
   realised `outcome_t = ln(close[t+5] / close[t])`; the volatility
   model targets the daily sigma of log returns over the next 5
   sessions, displayed as a 5-session band.
2. **Never show raw log return in the UI** — convert to a simple
   percentage for display.
3. **Magnitude thresholds are volatility-relative**: any threshold on
   the size of a price move is set relative to the ticker's
   volatility, not as a fixed number. (The former Advice formula and
   its `0.5` coefficient are retired with Advice.)
4. **Reliability is measured, never asserted**: the only reliability
   figure shown is the range hit-rate, measured from price history and
   labelled as such. The agent vote count is labelled **Agreement**,
   never Confidence. The band states its nominal coverage; it is not a
   guaranteed interval.
5. **Label by provenance**: name each agent for what it reads
   (Technical Signal, News Context, Macro) and mark language-model
   text as such. "Market Sentiment" is reserved for the technical
   proxy (RSI, MACD, Ichimoku) and is never applied to news, macro or
   a verdict.
6. **Never frame output as investment advice.** Use "technical
   observation" framing. Verdict labels contain no buy, sell, hold or
   other instruction. Show the disclaimer from `docs/DISCLAIMER.md`
   wherever a verdict, Agreement, a range or agent reasoning is
   displayed or exported.

## Open Discussions and Backlog

Before exploring or proposing a change, check whether it touches a
known open question or backlog item — folding it in (or explicitly
deferring it again) beats silently re-discovering it later:

- `docs/KNOWN_ISSUES.md` — confirmed, reproduced issues not yet
  scheduled into a milestone.
- `docs/DISCUSSION_*.md` — one file per open design question raised
  during manual verification of a past change (e.g. calendar staleness
  vs. the Fresh/Stale indicator, lack of prediction-outcome tracking).
  Read any whose title looks relevant to the task at hand.
- The open questions in the archived designs
  `openspec/changes/archive/2026-10-05-multi-agent-debate-analyst/design.md`
  and `.../2026-10-05-debate-data-quality-refinements/design.md` (prompt
  language, board-settle time, `[ticker]` company aliases, the rolling
  foreign-flow window, `/insight` and feature-flag removal).

This list itself may drift — if `docs/` gains a new `DISCUSSION_*.md`
or backlog file, treat it as covered by this pointer without needing
this file edited again.
