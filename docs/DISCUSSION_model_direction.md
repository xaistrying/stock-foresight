# Discussion: 5-session direction is not predictable; volatility is (2026-08-28)

Raised by the owner opening a session on "improving model accuracy," on the
premise that the M3 pooled XGBoost regressor (47.8% pooled out-of-fold
hit-rate) was under-performing because it was untuned. Investigation found
something different, and the session ended somewhere other than where it
started. This records the evidence, because all of it currently exists
only in a terminal session.

Nothing here is decided. This is a findings document plus open options.

## Summary

1. The model is not weakly predictive — it is **flat**. Out-of-fold
   correlation with reality is 0.0095.
2. The mechanism is a feature-representation defect: 95.6% of the model's
   gain comes from features that cannot generalize out-of-sample.
3. **Fixing that does not rescue directional prediction.** Tested; it
   does not.
4. Direction is not predictable at **any** horizon from 5 to 252 sessions.
5. **Volatility is predictable** — correlation ~0.48, stable across every
   fold and every ticker.
6. Model class matters far less than features for volatility. A linear
   model is competitive with tuned XGBoost.
7. Portfolio-level risk is computable and would need the owner's holdings.
8. Cross-sectional (relative) signal is the one directional effect that
   survived, and it needs a much larger universe to exploit.

---

## Finding 1: the model is flat, not weak

`useTickerFreshness`-style internal checks aside, the `backtest_predictions`
table tells the story directly. Excluding GAS (added later by the
per-ticker backtest button), across the 9 M3 training tickers:

| | value |
| --- | --- |
| `sd(actual)` | 0.0506 |
| `sd(predicted)` | 0.0076 |
| `corr(predicted, actual)` | **0.0095** |

Predictions are dispersed ~6.7x too narrowly. R² is roughly 0.0001. This
is the signature of least-squares regression on a target with
near-zero signal-to-noise: the model correctly concludes it cannot
predict, and collapses toward a constant.

**Why that produces a sub-50% hit rate**, which was the part that looked
anomalous in `MODEL_CARD.md`:

| fold | base rate up | model predicted up | hit-rate | mean prediction | corr |
| --- | --- | --- | --- | --- | --- |
| 0 | 59.1% | 8.3% | 42.2% | −0.0052 | −0.035 |
| 1 | 44.8% | 87.7% | 45.5% | +0.0038 | −0.040 |
| 2 | 48.6% | 48.5% | 50.1% | −0.0002 | +0.060 |
| 3 | 45.7% | 29.5% | 53.0% | −0.0056 | +0.155 |

When output is a nearly-flat line near zero, the *sign* of every
prediction is set by where that constant sits, not by the input. Fold 0
sat just below zero, so 92% of predictions read "down" — into a market
that rose 59% of the time. Fold 1's constant flipped positive, into a
falling market.

**Consequence for `MODEL_CARD.md`.** The card reports hit-rate trending
42.2% -> 53.0% across folds and honestly says it cannot distinguish
"more training data" from "regime change." That ambiguity can now be
partly resolved: it leans regime. Fold 3's 53.0% is mostly drift
alignment, not skill.

**Consequence for Rule 4.** Confidence reads the most recent ~60
backtested predictions, which all come from fold 3 — the single fold
where the constant happened to match the market. The Confidence values
currently shown in the UI (e.g. 65% for VIB) inherit that. Rule 4 is
not wrong, but what feeds it is less stable than the number's
presentation implies.

## Finding 2: the mechanism — 95.6% of gain from non-generalizing features

Feature importance pulled from the persisted `pooled_xgb_model.json`:

| feature | gain % | units |
| --- | --- | --- |
| `macd_signal` | 12.8 | price |
| `senkou_span_b` | 9.6 | price |
| `bb_middle` | 8.1 | price |
| `senkou_span_a` | 8.1 | price |
| `chikou_signal` | 7.5 | price difference |
| `bb_upper` | 7.3 | price |
| `atr` | 6.6 | price |
| `macd_line` | 6.6 | price |
| `bb_lower` | 6.5 | price |
| `macd_histogram` | 6.3 | price |
| `tenkan_sen` | 5.8 | price |
| `kijun_sen` | 5.1 | price |
| `obv` | 5.1 | cumulative volume (96 splits — the most of any feature) |
| **subtotal** | **95.6** | **non-stationary / scale-dependent** |
| `rsi` | 4.4 | bounded 0-100 — the only scale-free feature |

Two independent failure modes follow.

**(a) The features encode calendar time.** `obv` is a cumulative sum from
each ticker's earliest stored row (`DATA_DICTIONARY.md` flags it as "not
a bounded window," design Decision 5). For TCB:

| year | mean `obv` |
| --- | --- |
| 2018 | 6.2M |
| 2020 | 54.1M |
| 2022 | 678.4M |
| 2024 | 912.5M |
| 2026 | 1,459.9M |

Monotonic, 235x, never revisiting a past value — a near-perfect proxy
for the date. Trees cannot extrapolate: every test-fold row exceeds
every training value, so all land in the same terminal leaf and the
output is pinned to that leaf's mean. That reproduces Finding 1's
signature exactly.

**(b) The features encode ticker identity.** `bb_middle` ranges over
clean rows:

| ticker | range |
| --- | --- |
| VIB | 3.2 – 20.7 |
| HPG | 6.6 – 29.0 |
| TCB | 8.8 – 38.2 |
| SAB | 40.7 – 97.7 |
| VNM | 51.4 – 81.5 |

A split at 40 separates SAB/VNM from the rest exactly. Design Decision 3
deliberately excluded a ticker-identity feature so the model could not
memorise per-ticker base rates; the price-level features reintroduce it
through the back door. **The stated protection did not hold.**

## Finding 3: fixing the features does not rescue direction

This was the obvious next hypothesis, and it was tested rather than
assumed. Same walk-forward protocol, stationary/scale-free features
(`(close-X)/close` distances, `%B`, bandwidth, `atr/close`,
multi-horizon trailing volatility, normalised momentum, RSI):

```
fwd 5-session return, stationary features:
  -0.046, +0.059, -0.017, -0.083    mean = -0.022
```

Still zero, still sign-unstable. Finding 2 correctly explains the
*mechanism* of the sub-50% hit rate; it does not imply a working model
is recoverable. Clean features produce an honestly-zero model.

Cross-sectional (daily-demeaned) direction was also tested and also
fails: naive +0.004, model −0.011.

## Finding 4: no horizon works

Directional predictability swept from 5 to 252 sessions, stationary
features, walk-forward, purge = horizon:

| horizon | indep. windows/ticker | model corr | sign stable? | hit% | base% | edge |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | 280 | +0.003 | no | 49.8 | 50.0 | −0.1 |
| 10 | 139 | +0.024 | no | 50.3 | 51.4 | −1.1 |
| 21 | 66 | +0.031 | no | 50.7 | 52.3 | −1.7 |
| 63 | 21 | −0.035 | no | 50.8 | 53.6 | −2.8 |
| 126 | 10 | −0.061 | no | 46.1 | 56.8 | −10.6 |
| 252 | 4 | +0.022 | no | 59.2 | 60.6 | −1.4 |

Three independent reasons this is conclusive:

- **No horizon holds its correlation sign across all four folds.**
- **`edge` (hit − base) is negative everywhere.** The model never beats
  "always predict up." The 252-session row is the trap: 59.2% hit-rate
  looks like a result until you see the 60.6% base rate.
- **The effective sample collapses.** Overlapping windows leave ~4
  independent observations per ticker at 252 sessions. Results there
  are unfalsifiable regardless of value.

**One exception worth keeping.** Cross-sectional momentum (relative,
daily-demeaned) was weakly positive and *grew* with horizon: +0.025,
+0.037, +0.046, +0.056 at 5/10/21/63 sessions. It is the only
directional effect that behaved consistently. It cannot be exploited
with 15 tickers — a top decile of 1.5 stocks — see Finding 7.

## Finding 5: volatility is predictable

Target: forward 5-session realized volatility. Same walk-forward folds.

| approach | mean corr | R² |
| --- | --- | --- |
| rolling 20d std | 0.410 | 0.168 |
| HAR-RV regression (log, 5/20/60) | 0.441 | 0.195 |
| HAR + Parkinson/Garman-Klass range | 0.464 | 0.216 |
| linear regression, all vol features | **0.479** | **0.230** |
| XGBoost, untuned defaults | 0.446 | 0.199 |
| XGBoost, tuned (depth 2, mcw 100) | 0.471 | 0.222 |
| XGBoost, depth 6 | 0.430 | 0.185 |

Unlike direction, this is **stable**: positive in all four folds, and
positive for all 15 tickers individually (+0.257 to +0.518). Direction's
per-ticker correlations range −0.097 to +0.056 — random in sign.

## Finding 6: features matter more than model class here

Two observations from the table above, both relevant to a question the
owner raised directly ("why would basic statistics be sufficient?"):

- **The tuning search walked toward linearity.** Best config was
  depth 2 / `min_child_weight` 100 — the most regularised in the grid.
  Depth 6 was worst. A plain linear regression on log-volatility then
  edges out the tuned model (0.479 vs 0.471, within fold noise).
  Interpretation: log-volatility is close to linear-additive in its
  predictors, so a linear model is the correctly-shaped tool. Trees
  approximate a straight line with a staircase. This is a claim about
  *this target's structure*, not about ML generally.
- **The gains came from features.** rolling std 0.410 -> 0.479 is
  driven mostly by adding Parkinson / Garman-Klass range estimators.
  `high` and `low` are stored in `ohlcv` and currently unused —
  volatility is computed close-to-close only, which is several times
  less statistically efficient.

Also note: tuning moved results by more (0.430 -> 0.471) than the
model-class choice did. The M3 decision to defer tuning was reasonable,
but the deferral is now the cheapest remaining lever *for this target*.

## Finding 7: portfolio risk needs holdings, and is computed not predicted

Raised by the owner asking what happens if the system is given the
volume and price of tickers actually purchased.

**Cost basis has no predictive value** and must not enter the feature
set — it is a personal constant a tree could memorise. What holdings
unlock is portfolio-level risk, which requires no prediction at all.

Correlation of daily log returns across the 15 loaded tickers:

- Bank cluster (TCB, VIB, ACB, BID, CTG): mean pairwise **0.619**
- All pairs: mean **0.411** (min 0.21, max 0.70)
- Genuine diversifiers: SAB, VHM, GAS

5-session portfolio volatility, equal weight:

| portfolio | actual | if uncorrelated | understated by |
| --- | --- | --- | --- |
| TCB+VIB+ACB | 3.74% | 2.49% | 51% |
| + BID+CTG (5 banks) | 3.70% | 1.99% | 86% |
| TCB+VNM+FPT | 3.11% | 2.30% | 35% |
| 5 across sectors | 3.09% | 1.92% | 61% |
| all 15 | 3.05% | 1.18% | 158% |

Going from 3 banks to 5 banks changed risk from 3.74% to 3.70% — two
extra positions bought essentially zero diversification. Approximate
independent bets (`n / (1 + (n−1)ρ̄)`): 3 banks ≈ 1.3, 5 banks ≈ 1.4,
5 across sectors ≈ 1.9, all 15 ≈ 2.2.

**Out-of-sample caveat.** Covariance from a trailing 120 sessions
predicting next-5-session portfolio volatility:

| | corr with realized | mean bias |
| --- | --- | --- |
| full covariance | +0.216 | +17.9% |
| ignoring correlation | +0.230 | −35.2% |

Correlation does **not** help rank which weeks are risky — it fixes the
*level*. Ignoring it understates risk by ~35% systematically, which for
position sizing means sizing ~1.5x too large. This implies the right
architecture is: forecast each ticker's volatility (the part that
predicts well), estimate the correlation matrix separately on a long
window (slow-moving), and combine — not forecast portfolio volatility
directly.

**Design note on cost basis.** Entry price is a sunk cost and irrelevant
to any optimal decision. Displaying unrealized P&L prominently is a
well-documented driver of the disposition effect (selling winners early,
holding losers). If the goal is better decisions, risk and concentration
belong on the decision surface and cost basis belongs in a quieter P&L
view. Quantities are what drive every risk number; cost basis is
optional.

## Finding 8: universe size is what the surviving signal needs

Raised by the owner proposing to ingest the full HOSE universe.

`Listing().symbols_by_exchange()` returns: **405 HOSE (HSX) ordinary
stocks**, 313 HNX, 818 UPCOM, and — significantly — **1,637 DELISTED**
symbols. Every row carries `icb_code2` (industry classification).

- **Cross-sectional momentum becomes exploitable.** Finding 4's +0.05
  effect starves at 15 tickers (top decile = 1.5 stocks) and works at
  405 (top decile = 40). Information ratio scales roughly as
  `IC x sqrt(breadth)`; nominal breadth 15 -> 405 is an order-of-
  magnitude change, though ρ̄ = 0.411 means effective breadth is far
  below nominal and any IR estimate should be haircut accordingly.
- **A factor model becomes possible and necessary.** A 405x405
  covariance is 82,215 parameters from ~2,000 observations. `icb_code2`
  enables market + sector + idiosyncratic decomposition instead.
- **The held-out-ticker test M3 deferred becomes real** (design
  Decision 3 deferred ticker-identity features until "enough tickers
  exist for a meaningful held-out-ticker generalization test").
- **Small/mid-cap coverage**, which `MODEL_CARD.md` flags as an
  explicit unvalidated gap.

It does **not** make single-ticker direction predictable. It changes
which questions are answerable.

### Data-quality findings for a larger universe

**Survivorship bias is the fatal trap and is avoidable here.** Ingesting
only currently-listed tickers and backtesting 2018-2026 silently
excludes every company that failed or delisted; cross-sectional
strategies are especially vulnerable. The 1,637 DELISTED rows mean
point-in-time universe construction is possible — unusual for retail
data. **Not yet verified**: whether OHLCV history is actually
retrievable for delisted symbols, only that they appear in the catalog.
Worth testing before designing around it, since retrofitting is a
full re-ingest.

**Prices are split/dividend adjusted** — checked using HOSE's ±7% daily
price limit as ground truth. 25 violations in ~30,000 rows (0.08%)
across the 15 loaded tickers, no corporate-action jumps.

| ticker | violations | worst | reading |
| --- | --- | --- | --- |
| VHM | 1 | 2018-08-14: −0.69 log return | missed 2:1 split, not corrupt data — see note |
| VND | 12 | 2021-07-06: −10% | pre-HOSE (HNX, ±10%) |
| ACB | 7 | 2020-03-23: −10% | pre-HOSE (HNX, ±10%) |
| VIB | 5 | 2020-03-09: −12% | pre-HOSE (UPCOM, ±15%) |
| other 11 | 0 | — | clean |

**Correction, added 2026-08-28 after implementing the gate**: VHM's row is
not corrupt data. The close steps `60.30 -> 30.23` and *stays* halved — a
**missed 2:1 split adjustment**. Every price on either side of the step is
correct; only the single return across it is spurious. The −69% figure
quoted above and elsewhere in this document is the *log return*; the price
change is −50%. This matters because the remedy differs: a corrupt row
should be discarded, whereas a missed split contaminates one return *and*
every level-based indicator whose lookback window spans the step
(`bb_middle` 20 sessions, `kijun_sen`/`macd` 26, `senkou_span_b` 78).

VHM escapes the second problem only by timing: it listed 2018-07-31 and
split 10 sessions later, and its first `near_gap = 0` row is 2018-11-16 —
so the whole contaminated span sits inside the warm-up band already
excluded. A mid-life split on a long-listed ticker would get no such
protection, and `near_gap` does not flag price discontinuities. Across 405
Vietnamese tickers, which pay stock dividends frequently, this is expected
to recur.

Two further implications: **exchange membership changes over time**, so a
price-limit validation rule must know which exchange a ticker was on at
that date; and at 0.08% incidence, 405 tickers implies a few hundred
gate-triggering rows.

`backend/scripts/screen_ticker_volatility.py`'s existing stale-price
check (`STALE_PRICE_WARN_THRESHOLD = 0.15`) becomes essential rather
than advisory — its own docstring warns that a thinly-traded ticker "may
look like a calm, easy-to-predict series while actually just being
thinly traded," which at 405 names stops being a footnote.

## Finding 9: cross-sectional momentum at scale — does not hold as characterized (2026-09-11)

`cross-sectional-momentum-evaluation` change. Answers the question Finding
8 raised and left open: with the 208-symbol modelling universe
`hose-universe-ingestion` (archived 2026-09-07) unlocked — a top decile of
roughly 21 rather than 1.5 — does Finding 4's cross-sectional momentum
effect (+0.025 at 5 sessions, growing to +0.056 at 63, measured on 15
tickers) actually work at a workable scale? Measured by
`backend/scripts/evaluate_cross_sectional_momentum.py`: the same signal
definition (`ret_h = ln(close[t]/close[t-h])`, cross-sectionally demeaned,
forward target `ln(close[t+h]/close[t])`, also demeaned), the same
walk-forward protocol (`compute_fold_boundaries` from `training.py`,
reused unmodified, `N_FOLDS=5` -> 4 evaluation folds), read-only,
reproducible (bit-identical output across two consecutive runs against an
unchanged database on 2026-09-11, no randomness used or seeded).

**Verdict: no, not as originally characterized.** A small, sign-stable
effect survives at the two shortest horizons; the effect is not usable at
the scale or in the shape Finding 8 anticipated, for three compounding
reasons below.

**Universe and coverage.** All 208 modelling-universe symbols
(`ingestion_state='ok'`, `fails_liquidity_filter=0`,
`below_minimum_history=0`) have enough stored history (>=127 sessions) to
produce at least one valid signal/target pair at the longest horizon
tested (63 sessions) — no evaluation-side exclusions were needed beyond
the universe filters already in place.

**Effective breadth barely moved (task 7.4).** ρ̄, recomputed directly on
the 208-symbol universe's own daily log returns (203 symbols with
sufficient shared history to measure pairwise correlation): **0.310**
(min −0.12, max 0.91) — materially lower than the 15-ticker figure of
**0.411** measured in Finding 7. That drop did not translate into the
breadth gain Finding 8 anticipated, though: effective breadth
(`n / (1 + (n-1)ρ̄)`) is **3.2 of 203 nominal symbols**, against **2.2 of
15** on the original universe. Nominal breadth grew ~13.5x (15 -> 203);
effective breadth grew only ~1.5x (2.2 -> 3.2). Whatever market-wide
factor dominates HOSE names swallows almost all of the nominal
diversification a 208-symbol universe appears to offer.

**Per-horizon results** (pooled and per-fold; same 4-fold walk-forward
structure as Finding 1/4's tables):

| horizon (sessions) | pooled corr | corr sign-stable? | pooled decile spread | spread sign-stable? |
| --- | --- | --- | --- | --- |
| 5 | +0.0302 | yes (4/4 folds +) | +0.0058 | yes (4/4 folds +) |
| 10 | +0.0439 | yes (4/4 folds +) | +0.0129 | yes (4/4 folds +) |
| 21 | +0.0044 | **no** (2/4 folds negative) | +0.0077 | yes (4/4 folds +, barely) |
| 63 | +0.0040 | **no** (2/4 folds negative, incl. most recent) | +0.0115 | **no** (most recent fold −0.0101) |

Per-fold correlation, chronological (fold 0 earliest):

| horizon | fold 0 | fold 1 | fold 2 | fold 3 |
| --- | --- | --- | --- | --- |
| 5 | +0.0305 | +0.0379 | +0.0247 | +0.0224 |
| 10 | +0.0415 | +0.0644 | +0.0408 | +0.0136 |
| 21 | +0.0190 | −0.0004 | −0.0122 | +0.0159 |
| 63 | +0.0444 | +0.0029 | −0.0017 | −0.0311 |

**This reverses Finding 4's shape, not just its scale.** The original
15-ticker measurement grew *with* horizon — weakest at 5 sessions,
strongest at 63 (+0.025 -> +0.056). At 208 symbols it is the opposite: the
short horizons (5, 10) are the ones with a small, sign-stable positive
effect; the long horizons (21, 63) — where the original measurement
looked strongest, and which motivated "it needs a much larger universe to
exploit" — are the ones that fail to replicate, going sign-unstable in
both correlation and, at 63 sessions, decile spread too.

**Why "no" rather than a qualified yes at 5/10 sessions.** Three
compounding reasons, matching the multiple-comparisons and breadth risks
design.md's Risks section named in advance of running this:
1. Of 8 cells (4 horizons x 2 metrics), only 4 — the 5- and 10-session
   correlation and decile-spread cells — are both positive and
   sign-stable. Four-of-eight is not the ratio a real, broad-based effect
   should produce, and is within reach of chance alone across this many
   noisy measurements.
2. Even the surviving cells are economically tiny once effective breadth
   is applied: IC ≈ 0.03-0.04 with effective breadth ≈ 3.2 gives an
   information ratio (IC x sqrt(breadth)) of roughly 0.05-0.07 — far below
   what a usable cross-sectional strategy needs, and nowhere near
   "exploitable," the word Finding 8 used based on nominal breadth alone.
3. The 63-session horizon, which the original 15-ticker figure (+0.056)
   made the strongest case for pursuing at scale, is the one result here
   with both metrics sign-unstable and its most recent fold negative on
   both — the opposite of what Finding 8's extrapolation implied.

**What this confirms/updates about `docs/MODEL_CARD.md` (task 7.3).**
Nothing already published in `MODEL_CARD.md` is contradicted — it does not
report cross-sectional momentum. This finding forecloses one candidate
follow-up to that card (a cross-sectional ranking feature built on
Finding 4's 15-ticker figures, per Finding 8's "becomes exploitable"
framing) rather than revising anything already there.

**If the 5/10-session result were pursued anyway** (task 7.2) — stating
its caveats up front, not implied away: a ranking/screening surface does
not exist today and would need to be built from scratch; portfolio
construction guidance (position sizing, rebalancing cadence, transaction
costs, all against an effective breadth of ~3 independent bets rather than
208 nominal names) is entirely unaddressed by this evaluation; and
holdings data is not collected anywhere in this system. None of this is a
recommendation to build any of it — it is what a later, separate proposal
would have to answer before doing so, per this change's explicit
out-of-scope list.

**Reproducing this finding**: `backend/scripts/evaluate_cross_sectional_momentum.py`,
read-only against `backend/data/app.db`, no writes, no randomness, no
touch of `backend/data/models/pooled_xgb_model.json`. Verified to
reproduce bit-identical output across two consecutive runs against an
unchanged database on 2026-09-11.

---

## Consequences for the non-negotiable domain rules

None of this has been actioned. Listing what each rule would face:

- **Rule 1** (target = `ln(close[t+5]/close[t])`). Survives a pivot to
  reporting an interval — same target, different statistic reported.
  Does not survive a pivot to volatility as the primary target. Needs
  an explicit ruling either way.
- **Rule 2** (never show raw log return). Unaffected.
- **Rule 3** (thresholds = `0.5 x rolling_std(60)`). **Improved.** The
  threshold quantity becomes forecast rather than trailing. The
  volatility-relative design the config calls non-provisional is
  preserved and better served.
- **Rule 4** (Confidence = backtested hit-rate over ~60). **Cannot
  survive unchanged** under any volatility pivot — hit-rate is a
  directional concept and there would be no directional prediction to
  score. Becomes either interval calibration ("the actual landed inside
  the predicted band X% of the time") or a regime-classification
  hit-rate, which preserves Rule 4's shape most closely.
- **Rule 5** (Sentiment is a technical proxy). Unaffected. `insight.py`
  already reads indicators as scale-free comparisons (`rsi >= 55`,
  `macd_histogram > 0`, `tenkan > kijun`) — signs and thresholds, never
  levels. Only the model consumes raw magnitudes.
- **Rule 6** (never frame as investment advice). **Easier** — a
  zero-centred range is harder to misread as a recommendation than
  "Signal: down." But note that outputting position sizes is a
  materially different posture and would deserve its own framing
  decision.

The owner has stated this application is for personal use, which makes
rules 1-6 design choices rather than compliance constraints. Rule 6 is
still worth keeping on its own merits: false precision costs the person
using it.

## Options, none decided

1. **Do nothing.** Keep the directional model, accept it as a
   pipeline-proving exercise, and treat `MODEL_CARD.md`'s honest
   "indistinguishable from chance" framing as sufficient disclosure.
   Cheapest; leaves a UI that shows a number with no demonstrated value.
2. **Feature-stationarity fix only.** Address Finding 2 without
   changing the product. Produces an honestly-flat model and a truthful
   Confidence number. Does not make anything predictable.
3. **Pivot the primary output to volatility / expected range.** Report
   dispersion (knowable) instead of centre (not knowable). Chart's
   single predicted point becomes a cone. Requires a Rule 4 decision,
   and a Rule 1 ruling depending on framing.
4. **Add holdings and become a portfolio-risk tool.** Finding 7. Needs
   a new holdings table, a correlation/factor layer, and a decision on
   how prominently cost basis appears.
5. **Expand the universe and pursue cross-sectional signal.** Finding
   8. Independent of 3 and 4; a prerequisite for the only directional
   effect that survived testing.

3, 4 and 5 are complementary rather than competing. 5 has one-way doors
in its ingestion design (point-in-time membership, delisted names,
price-limit gating) that are cheap now and expensive to retrofit.

## Reproducing these numbers

**Preserved 2026-09-07 (`hose-universe-ingestion` task 9.4):**
`backend/scripts/baseline_model_diagnostics.py` re-measures Findings 1, 2
and 7 against the current database. Read-only, so it is safe to run at any
time. Verified to reproduce the figures below exactly on the day it was
written: `sd(actual)` 0.0506, `sd(predicted)` 0.0076, `corr` 0.0095, the
6.7x dispersion ratio, the whole per-fold table (42.2 / 45.5 / 50.1 /
53.0%), `obv`'s 96 splits, and — with `--doc-baseline`, which pins the 15
tickers loaded when this was written rather than following the database —
Finding 7's 0.411 mean pairwise correlation (min 0.21, max 0.70) and 2.2
independent bets.

Findings 3-5 are deliberately not in that script: they are experiments
proposing a model change, not baseline measurements, so reproducing them
means implementing the pivot. Finding 8's price-limit scan is superseded by
the quality gate, reproducible via
`backend/scripts/verify_quality_gate.py`, which asserts the known-answer
counts rather than printing them.

The original figures were produced ad hoc against `backend/data/app.db` in
a session scratchpad. Methods, as recorded before the script existed:

- Findings 1-2: SQL over `backtest_predictions` (per-fold `AVG`/`corr`
  via `AVG(xy)-AVG(x)AVG(y)` over `sd`), and
  `xgb.Booster.get_score(importance_type="gain")` on
  `backend/data/models/pooled_xgb_model.json`.
- Findings 3-5: walk-forward with 5 pooled chunks / 4 boundaries and a
  purge of `horizon` rows per ticker, matching `training.py`'s existing
  protocol; volatility targets regressed in logs.
- Finding 7: `pandas.DataFrame.corr()` and `cov()` on aligned daily log
  returns; 120-session trailing covariance for the out-of-sample test.
- Finding 8: `vnstock.explorer.vci.listing.Listing().symbols_by_exchange()`;
  price-limit scan over `ohlcv`.

Preserving these as a durable script under `backend/scripts/` (alongside
`screen_ticker_volatility.py`) is worth doing before any of the options
above is actioned, so the baseline is reproducible rather than
remembered. — **Done**, see the top of this section.

**Finding 9** (cross-sectional momentum at scale) is reproducible via
`backend/scripts/evaluate_cross_sectional_momentum.py`, preserved from the
start rather than ad hoc, per the same discipline this section documents
for the earlier findings. Read-only; verified bit-identical across two
consecutive runs on 2026-09-11.

**Update 2026-10-07**: Option 3 (pivot to volatility) was taken by
`multi-agent-debate-analyst` (archived 2026-10-05), which replaced the
directional prediction with a HAR-RV volatility band and a three-agent debate.
The consequences for the domain rules are proposed in
`align-rules-and-disclaimer`; the review that prompted the follow-up work is
`docs/DISCUSSION_post_pivot_review.md`.

**Status**: Option 3 taken; the other options were not pursued. The
XGBoost directional model is retired as a product output and is still served
by `/prediction` and `/insight` until `retire-direction-model` removes it.
