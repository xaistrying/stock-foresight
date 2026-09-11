## Context

`docs/DISCUSSION_model_direction.md` (Finding 4) measured cross-sectional
momentum as the only directional effect that held its sign across all
tested horizons, on the original 15-ticker universe:

| horizon (sessions) | cross-sectional corr |
| --- | --- |
| 5 | +0.025 |
| 10 | +0.037 |
| 21 | +0.046 |
| 63 | +0.056 |

That measurement was scratchpad code, never preserved (that document's own
"Reproducing these numbers" section says so explicitly), and it could not
evaluate the effect as a usable strategy — a top decile of 15 tickers is
1.5 stocks. `hose-universe-ingestion` (archived 2026-09-07) exists to
remove exactly that constraint: 208 symbols now pass the modelling-universe
filters (`ingestion_state = 'ok' AND fails_liquidity_filter = 0 AND
below_minimum_history = 0`), a top decile of roughly 21.

This change asks the deferred question at the scale the prior change was
built for, and commits to nothing about what happens if the answer is yes.

## Goals / Non-Goals

**Goals:**
- Measure cross-sectional momentum at 5/10/21/63-session horizons across
  the 208-symbol modelling universe, on the same walk-forward protocol
  `training.py` already uses.
- Report a decile-ranking construction and sign stability across folds,
  not just a pooled correlation.
- Report effective breadth (from measured ρ̄), so a raw correlation number
  is never presented without the caveat that narrows it.
- Leave a durable, re-runnable script and a plain, dated verdict appended
  to `docs/DISCUSSION_model_direction.md`.

**Non-Goals:**
- Retraining or replacing `pooled_xgb_model.json`. This produces a
  standalone verdict, not a new production model.
- Any UI or API change. No ranking or screening surface is built here even
  if the effect holds — that is a real product decision for a later
  proposal.
- Any Rule 1-6 change. This is read-only offline analysis with no served
  output.
- A definitive judgment on portfolio construction (position sizing,
  execution, transaction costs). The decile spread is a research signal
  of whether relative predictability exists, not a trading rule.

## Decisions

### Decision 1: Reuse `compute_fold_boundaries`; generalize the purge, don't reimplement it

`compute_fold_boundaries` (pooled, expanding-window, 4-6 folds) is reused
unmodified — it has no horizon dependency, so it needs no change to serve
multiple horizons.

`purge_training_rows` is a different matter: it calls
`_label_dates_by_ticker`, which is hard-coded to `TARGET_HORIZON` (5) via
`shift(-TARGET_HORIZON)`. This evaluation needs the purge at 5, 10, 21, and
63 sessions. Rather than duplicating `purge_training_rows` four times or
editing the shared, production-serving function to take a horizon
parameter it does not otherwise need, this change adds a local, horizon-
parameterized variant of `_label_dates_by_ticker` inside the new script,
computing forward-shifted label dates from each candidate horizon rather
than the fixed constant. `compute_fold_boundaries` and the general purge
*logic* (drop rows whose true label date lands at or after the boundary)
are the parts reused; the one horizon-coupled helper is generalized
locally rather than forced into the training module's public surface for
a use case training.py itself does not have.

*Alternative considered*: parameterizing `_label_dates_by_ticker` and
`purge_training_rows` in place, in `training.py`. Rejected — it would add
a parameter to production training code for a caller that is explicitly
not production, expanding that module's surface for one offline script's
benefit. If a second consumer ever needs multi-horizon purging, that is
the point to revisit this.

### Decision 2: Signal definition mirrors the discussion doc exactly

The cross-sectional signal is `ret_h = ln(close[t] / close[t-h])` at each
horizon `h`, demeaned across all universe symbols sharing date `t` — the
same definition the original scratchpad measurement used (recorded in
`docs/DISCUSSION_model_direction.md` Finding 4's methods note). The
forward target is `ln(close[t+h] / close[t])`, also cross-sectionally
demeaned.

*Alternative considered*: a more sophisticated momentum construction
(risk-adjusted, volume-weighted, sector-neutralized using `icb_code2` now
available from the universe ingestion). Rejected for this change — the
goal is to reproduce and scale-test the specific effect already measured,
not to search for a better one. A sector-neutral variant is a reasonable
follow-up if the plain version holds.

### Decision 3: Decile construction, not a continuous score

Each fold's test period ranks universe symbols by their demeaned signal on
each date, and reports the average forward return of the top decile minus
the bottom decile — the standard cross-sectional evaluation construction,
distinct from and complementary to the raw correlation. Both are reported
together; the design does not treat one as sufficient on its own, per the
`cross-sectional-momentum-evaluation` spec's requirement that both be
present.

### Decision 4: Effective breadth from measured ρ̄, computed on the actual 208

The earlier ρ̄ ≈ 0.41 figure was measured on the original 15-ticker
universe and is explicitly not reused here — Decision 4 in this document
is precisely to recompute it on the 208-symbol universe, since a larger,
more sector-diverse universe could plausibly shift it in either direction
(more sectors could lower it; the universe still being one country's
equity market could keep it elevated). Effective breadth is estimated as
`n / (1 + (n-1)ρ̄)` (the standard approximation used informally in this
project's earlier discussion), reported alongside, not instead of, the raw
correlation and decile figures.

### Decision 5: Verdict lands in `docs/DISCUSSION_model_direction.md`, not a new file

The verdict is appended as a new dated section in the same document this
change's motivation comes from, continuing that document's existing
pattern (it already has one such appended follow-up, "Follow-up: Stale is
not just rare" style sections exist elsewhere in this project's discussion
docs). This keeps the full arc — direction is flat, volatility works,
cross-sectional needed scale, here is whether scale delivered — in one
place rather than fragmented across files.

## Risks / Trade-offs

- **A positive result invites scope creep toward "just ship it."** →
  Mitigated by this change's proposal explicitly naming ranking/screening
  UI, portfolio construction, and holdings work as separate, out-of-scope
  follow-ups requiring their own proposal — the verdict states
  prerequisites, it does not become a UI change by momentum.
- **A negative result could be quietly reframed until something scores
  positive.** → The spec requires all four horizons reported together
  (no post-hoc horizon selection) and requires a negative result to be
  stated plainly. The verdict is written once the evaluation script's
  output is final, not iterated against until a headline number appears.
- **Multiple-comparisons risk**: four horizons and two metrics (correlation,
  decile spread) per horizon is eight numbers, some of which will look
  positive by chance alone. → The sign-stability-across-folds requirement
  is the primary defense (matches how the original single-ticker findings
  were judged, not the pooled correlation alone); the verdict should
  explicitly discuss this risk rather than treat any single positive cell
  as sufficient.
- **The purge-logic generalization (Decision 1) is new code, unlike
  everything else reused from `training.py`, and could have a subtle bug
  a multi-horizon context makes easy to miss.** → Tasks include a
  known-answer check: at horizon 5, the locally generalized purge should
  reproduce results equivalent to calling the existing
  `purge_training_rows`/`_label_dates_by_ticker` machinery, verified
  directly rather than assumed from code inspection.
- **208 symbols is still small for a decile construction** (≈21 per
  decile) → Named explicitly in the verdict rather than treated as
  adequate by default; Decision 4's effective-breadth figure is the
  intended honest counterweight to a headline correlation number.

## Open Questions

1. **Sector neutralization.** `icb_code2` is available from the universe
   ingestion and unused here (Decision 2). Worth a follow-up evaluation if
   the plain version shows a real effect, to see whether it strengthens or
   was itself proxying for a sector effect.
2. **What decile count to use as universe size grows.** Deciles are chosen
   here for a 208-symbol universe; if HNX is ever added (still declined
   per the archived change's design open question 4), the same construction
   should be revisited rather than assumed to scale unchanged.
