# Discussion: No mechanism logs live predictions against realized outcomes (2026-08-12)

Raised while manually spot-checking the `ticker-manual-refresh` feature:
compared VNM's stored prediction (made `as_of: 2026-08-03`) against the
actual close 5 trading sessions later, once refresh pulled that data in.
Recording it here because it surfaces a real gap in how (or whether) this
app's model accuracy is tracked over time in production use — relevant to
any future continuous-training work.

## What was checked

Before refreshing VNM (last loaded 2026-08-03):

| | Value |
|---|---|
| `as_of` | 2026-08-03 |
| `predicted_log_return` | -0.0038 (**-0.38%**) |
| Confidence | 65% (60-prediction hit-rate) |
| Sentiment (technical proxy, RSI/MACD/Ichimoku) | bullish |
| Advice | HOLD |

After refresh, real trading sessions through 2026-08-12 were available,
including the actual t+5 target session (2026-08-10, 5 trading sessions
after 2026-08-03: 08-04, 08-05, 08-06, 08-07, 08-10):

| | Predicted | Actual (2026-08-10) |
|---|---|---|
| Log return | -0.0038 | +0.0261 |
| As % move | -0.38% | **+2.64%** |
| Direction | down | **up** — miss |

One prediction, direction and magnitude both missed. `n=1` — this proves
nothing statistically about the model. What it does demonstrate is that
**this comparison had to be done entirely by hand**, ad hoc, in a
terminal, and is not persisted anywhere. The moment this session ends,
the comparison is gone.

## Why nothing captures this today

- `GET /tickers/{ticker}/prediction` computes live from the latest
  features row on every call (`backend/app/api/predictions.py`) — it
  does not log the prediction it returns anywhere.
- `backtest_predictions` (confirmed to exist via
  `sqlite3 backend/data/app.db ".tables"`) is populated by the M3
  walk-forward backtest process, not by live `/prediction` calls. It's
  what Confidence's 60-prediction hit-rate reads from — but that data is
  backtest-time-travel accuracy, not live-serving accuracy. The two can
  diverge (feature/label drift, data revisions from vnstock between
  pulls, etc.) and there's currently no way to tell if they have.
- There is no scheduled job of any kind in this app (confirmed during
  the `ticker-manual-refresh` investigation — no cron/APScheduler/
  Celery/background task anywhere in `backend/app`). Even if predictions
  were logged, nothing would later go back and fill in "what actually
  happened" once t+5 arrives — that requires a job to run at some later
  point, and no such mechanism exists.
- A secondary wrinkle observed during this check: vnstock's returned
  `close` for a given date can shift slightly between pulls (VNM's
  2026-08-03 close read 60.5 before this refresh, 60.3 after). Any
  outcome-logging design needs to decide whether "actual outcome" means
  the close as observed at prediction time, as re-observed later, or
  something else — this wasn't a problem before because nothing compares
  across two points in time at all today.

## Why this matters for continuous training

Confidence (Rule 4) is currently backtest-only; nothing measures whether
live, currently-served predictions are hitting at a similar rate over
time. If the model's live accuracy quietly drifted from its backtested
accuracy, there is no instrumentation in this app that would surface it.
That's the prerequisite gap before any real continuous-retraining loop
(triggering retraining off live drift, not just a fixed backtest number)
could be built.

## Options raised, none decided

1. **Do nothing yet.** Confidence's backtest hit-rate is the only
   documented v1 requirement (Rule 4); live-accuracy tracking was never
   in scope for v1. Revisit only if backtest-vs-live divergence is
   suspected for a real reason, not preemptively.
2. **Log every served prediction** (ticker, `as_of`, target date,
   predicted value) to a new table at request time, independent of
   whether it's ever scored. Cheap, but scoring still needs a separate
   mechanism (see 3).
3. **A scoring job** that, given logged predictions, finds ones whose
   target date now has real OHLCV data and computes the realized
   outcome (hit/miss, error magnitude) — writing into either
   `backtest_predictions` itself (if its schema fits) or a new table.
   Needs the same "when does this run" question `ticker-manual-refresh`
   already ran into: there's no scheduler in this app today, so this
   would either piggyback on the manual Refresh action, run at server
   startup, or require introducing an actual scheduled job for the
   first time in this codebase.
4. **Surface live-vs-backtest divergence in the UI** once (2) and (3)
   exist — e.g. a secondary "live hit-rate (last N)" alongside the
   existing backtest-based Confidence. Would need explicit UI framing
   so it doesn't get confused with or silently replace Confidence
   (Rule 4 specifically defines Confidence as the backtest hit-rate;
   changing what number is shown there needs sign-off, not a quiet
   swap).

## Scope note

This is materially bigger than `ticker-manual-refresh` — it touches the
DB schema (new table or `backtest_predictions` extension), introduces
either the first scheduled job in this codebase or a piggyback on
Refresh, and potentially changes what's shown in the AI insight panel
(Rule 4 territory, needs care). If picked up, it should go through
`/opsx:propose` as its own change rather than folding into an existing
one.

**Status**: open, undecided. Not blocking anything currently shipped.
