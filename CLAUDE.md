# CLAUDE.md

This file loads automatically at session start, in plain chat, and during
`/opsx:explore` — none of which call `openspec instructions`, so none of
them see `openspec-project-context.yaml`'s `context`/`rules` fields. This
file exists specifically to cover that gap.

It intentionally duplicates the six domain rules below. If you change a
rule, change it in BOTH this file and `openspec/config.yaml`, or
they will drift out of sync.

Everything else — full tech stack, commands, repository structure,
milestone status, and the AI insight panel response contract — lives in
`openspec/config.yaml`. That file is the source of truth for anything
not listed here, and loads automatically during `/opsx:propose`,
`/opsx:continue`, and `/opsx:ff` (proposal/design/tasks generation).

## Non-Negotiable Domain Rules

If a task in ANY mode — explore, plain chat, or formal OpenSpec artifact
generation — seems to require changing one of these, stop and ask first
rather than silently changing it.

1. **Prediction target**: `target_t = ln(close[t+5] / close[t])` — log
   return, 5 TRADING SESSIONS ahead, not calendar days.
2. **Never show raw log return in the UI** — convert to a simple
   percentage for display.
3. **Advice thresholds are volatility-relative**: `0.5 x
   rolling_std(returns, 60 sessions)`, not a fixed number. The `0.5`
   coefficient is provisional (may change after M3 backtesting) — the
   volatility-relative *design* is not provisional.
4. **Confidence score (v1)** = backtested hit-rate over the ticker's
   most recent ~60 predictions. Not a statistical prediction interval
   (that's a future quantile-regression upgrade, out of v1 scope).
5. **"Market Sentiment" is a technical proxy** (RSI, MACD, Ichimoku
   position), not real news/NLP sentiment. Must be labeled as such in
   the UI.
6. **Never frame output as investment advice.** Use "technical
   observation" framing and show the disclaimer from
   `docs/DISCLAIMER.md` (created M6, not before — nothing to disclaim
   until M6 has UI output) anywhere Advice, Confidence, or Sentiment is
   displayed.
