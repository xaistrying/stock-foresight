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

---

# Follow-up: Stale is not just rare, it is unreachable (2026-08-28)

Raised by the owner looking at the dashboard and observing that the dot
next to each ticker symbol "doesn't show much meaning." Investigated in
that session; this section records what was proven, a new option that
wasn't on the list above, and a separate defect found along the way.

## The original doc understated the problem

The section above says Stale is "effectively unreachable in practice."
It is stronger than that — it is unreachable by construction, and this
is now confirmed empirically, not just argued from the code.

`useTickerFreshness.js` computes exactly one comparison:

```js
predictionAsOf >= latestSessionDate ? FRESH : STALE
```

- `predictionAsOf` is `max(features.date)` for the ticker —
  `GET /tickers/{ticker}/prediction` returns the `date` of
  `LATEST_FEATURES_ROW` (`backend/app/api/predictions.py`).
- `latestSessionDate` is `max(ohlcv.date)` for the ticker — the last
  row of `/history`.

Checked directly against `backend/data/app.db`, all 15 currently loaded
tickers:

| Ticker | `max(ohlcv.date)` | `max(features.date)` |
| --- | --- | --- |
| ACB | 2026-08-18 | 2026-08-18 |
| BID | 2026-08-18 | 2026-08-18 |
| CTG | 2026-08-18 | 2026-08-18 |
| FPT | 2026-08-18 | 2026-08-18 |
| GAS | 2026-08-18 | 2026-08-18 |
| HPG | 2026-08-12 | 2026-08-12 |
| MSN | 2026-08-12 | 2026-08-12 |
| MWG | 2026-08-12 | 2026-08-12 |
| PNJ | 2026-08-18 | 2026-08-18 |
| SAB | 2026-08-19 | 2026-08-19 |
| TCB | 2026-08-18 | 2026-08-18 |
| VHM | 2026-08-13 | 2026-08-13 |
| VIB | 2026-08-18 | 2026-08-18 |
| VND | 2026-08-13 | 2026-08-13 |
| VNM | 2026-08-12 | 2026-08-12 |

Equal for every ticker, with no exceptions. `load_ticker` writes OHLCV
and recomputes features in the same call, so the two dates move in
lockstep and the comparison is a tautology: it asks whether a
prediction agrees with the data it was computed from, when the same
code path wrote both. The dot is a constant, not a signal.

**Consequence for the UI**: the dot's own tooltip reads "Fresh — up to
date with the latest trading session." That is misleading. It actually
means "up to date with the latest session *this app happens to have
stored*", which is circular. On 2026-08-28 the dashboard showed nine
green Fresh dots while four of those tickers (HPG, MSN, MWG, VNM) sat
on data from 2026-08-12 — sixteen calendar days behind.

The element actually carrying information in that view is the small
grey "Loaded 15d ago" footer text, not the dot above it. The dot, plus
the three-item legend explaining a mapping that only ever resolves to
one value, is currently pure decoration.

## Separate defect found: near_gap is invisible on the chip

`GET /tickers/{ticker}/prediction` can return `status: "near_gap"`,
meaning no prediction is obtainable for that ticker's latest row. That
state is handled correctly in `PredictionDisplay`, `ChartPanel`, and
`AIInsightPanel` — but **not in `TickerChip`**. `useTickerFreshness`
only reads `as_of`, which is present on a `near_gap` response, so such
a ticker resolves to FRESH and renders a confident green dot while
having no prediction at all.

No ticker is currently in this state (`near_gap = 0` on every ticker's
latest `features` row as of this check), so this is latent, not live.
But it is reachable, and it is precisely the case where a green dot is
most wrong.

## New option not previously listed: cross-ticker max as the reference

Options 1-3 above framed calendar-awareness as needing a wall-clock
threshold ("more than N days old"), with the attendant "what is the
right N?" problem and the holiday-gap false-positive risk that
Decision 10 was written to avoid.

There is a third reference point neither the original design nor this
doc considered: **`max(date)` across all loaded tickers**, rather than
each ticker against itself.

The DB already demonstrates this works — SAB is at 2026-08-19 while HPG
is at 2026-08-12. The app therefore already knows, from its own stored
data and nothing else, that at least five sessions exist which HPG has
not been refreshed against.

Properties:

- **No new dependency.** No market calendar, no vnstock call, no
  threshold constant to pick. It is a query over data already stored.
- **Does not reintroduce the holiday false positive.** If genuinely no
  newer session exists anywhere in the app's data, nothing goes stale —
  which is the exact property Decision 10 was protecting.
- **It is a lower bound, not the truth.** If nothing has been refreshed
  in a month, every ticker still reads Fresh. It degrades toward the
  current (harmless-but-useless) behaviour rather than toward false
  alarms.

This does not revive rejected option 3. Option 3 was rejected for
stacking wall-clock age on top of internal consistency, conflating two
questions in one signal. This *replaces* the internal-consistency
meaning outright — which the proof above shows was never a real signal
to begin with, so nothing is being conflated away.

## Recommendation from this session

Adopt the cross-ticker reference as the dot's primary meaning and fold
the `near_gap` defect into the same change, giving three states that
are all actually reachable:

- **Fresh** — this ticker is at the newest session any loaded ticker
  has.
- **Stale** — a newer session exists in this app's own data; refresh.
- **No prediction** — latest row is `near_gap`, no value obtainable.

**Deleting the dot entirely** (with its legend, and most of
`useTickerFreshness`) remains a legitimate alternative if the above is
judged not worth building. "Loaded Xd ago" already tells the user what
they need, and removing a signal that cannot vary is better than
keeping it.

**Explicitly rejected**: repurposing the dot to carry prediction
direction or signal strength (green up / red down). It duplicates the
AI insight panel, and a green-or-red dot beside a ticker symbol reads
as buy/sell — a Rule 6 violation regardless of the label attached to
it.

## Constraints on whoever picks this up

- `FRESHNESS` in `useTickerFreshness.js` is a public contract with
  more consumers than the dot itself: `TickerChip`'s
  `FRESHNESS_DESCRIPTION` ARIA/title strings, its `data-freshness`
  attributes (consumed by `ticker-panel.css`), `TickerPanel`'s legend,
  and `TickerPanel.test.jsx`. All move together.
- Rule 6 governs any new state's label and colour, per the rejection
  above.
- Still `/opsx:propose` territory, not a quick patch — unchanged from
  the original doc's conclusion.

**Status**: still open and undecided, but the framing has changed. The
original question was "should we add a second calendar-aware signal
alongside the dot?" The better question now is "the dot is provably
constant — should it be repointed at a reference that varies, or
removed?"
