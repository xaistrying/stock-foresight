# Discussion: Fresh/Stale never reflects calendar age (2026-08-12)

Raised during manual verification of the `ticker-manual-refresh` change,
after observing that a ticker loaded 13 days ago (`VHM`) still showed
**Fresh** in the ticker panel. Not a bug — this is the freshness dot
working exactly as designed. Recording it here because the gap it leaves
is worth a deliberate decision, not a silent assumption.

## How Fresh/Stale actually works today

Defined in [`useTickerFreshness.js`](../frontend/src/hooks/useTickerFreshness.js),
from [Decision 10](../openspec/changes/archive/2026-08-12-vite-react-dashboard-ticker-panel/design.md)
of the `vite-react-dashboard-ticker-panel` change:

- **Fresh** — the stored prediction's `as_of` date is on or after the
  latest session in the ticker's own stored `/history`.
- **Stale** — `as_of` is *before* the latest stored session.
- **Loading** — the prediction/history query (or a `/load` request) is
  in flight.
- **Unknown** — not enough data to compare (not loaded, error, no rows).

The comparison is deliberately **not calendar-aware** — it was designed
this way on purpose, so a genuine holiday gap (no newer session exists
yet) doesn't misreport as stale. Quoting Decision 10 directly: "Staleness
is defined against actual data availability, not a fixed calendar age
... a ticker isn't stale just because time passed if there's genuinely
no newer session to refresh against."

## Why this means Fresh almost always shows, regardless of calendar age

`load_ticker` (`backend/app/services/ticker_ingestion.py`) always writes
OHLCV and recomputes features **in the same call**, and
`GET /tickers/{ticker}/prediction` always computes live from the newest
features row (`backend/app/api/predictions.py`) — there's no separate,
independently-updatable "stored prediction" to fall behind. So the
instant any load completes, `as_of` and the latest stored session are
the same date by construction. There is no code path in this app today
where a *loaded* ticker's prediction lags behind its *own* stored
history — Stale is effectively unreachable in practice.

**Net effect**: a ticker can sit unloaded for weeks and still show
Fresh, because Fresh only checks internal consistency (prediction agrees
with its own stored data), never "is this data itself old by wall-clock
time." This exact gap is what motivated the `ticker-manual-refresh`
change in the first place (see its
[proposal.md](../openspec/changes/ticker-manual-refresh/proposal.md),
still active/unarchived as of this writing) — Refresh and the "Loaded
Xd ago" text next to it exist *because* the dot can't tell you a ticker
is calendar-stale. That change explicitly scoped a calendar-age
indicator **out**, deferring it as a future decision (see that change's
[design.md](../openspec/changes/ticker-manual-refresh/design.md)
"Non-Goals" and "Open Questions").

## The open question

Should there be a second, calendar-aware signal — independent of the
existing internal-consistency Fresh/Stale dot — that flags a ticker
whose `last_loaded_at` is more than N calendar days old? Options raised
informally so far, none decided:

1. **Do nothing.** The "Loaded Xd ago" text is already visible on every
   loaded chip; a user who cares can read it and click Refresh
   themselves. Adding a second dot/badge risks visual noise for a
   judgment call (how old is "too old" for a given ticker's own
   volatility/liquidity?) that has no obviously correct default.
2. **A third visual state alongside the existing dot** (e.g. a small
   badge or a second color) that fires past some threshold (7d? 14d?
   configurable per environment?). Needs a real threshold decision, and
   needs to not collide with or muddy the existing Fresh/Stale meaning —
   likely means the two signals render as visually distinct elements
   (dot vs. badge), not a fourth dot color.
3. **Fold it into the existing dot's semantics** by redefining Stale to
   also mean "loaded more than N days ago." Rejected in the original
   `ticker-manual-refresh` design specifically because it would
   conflate two different questions (internal consistency vs. wall-clock
   age) into one signal — probably still the wrong call now for the same
   reason, but listed for completeness.

No consensus reached yet. If this gets picked up, it should go through
`/opsx:propose` as its own change (it touches `useTickerFreshness.js`'s
public meaning, which other code — the legend, TickerChip's dot render —
depends on), not a quick patch.

**Status**: open, undecided. Not blocking anything currently shipped.

## Note by owner

We should open a discussion about the meaning of these states.
