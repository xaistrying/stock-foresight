## 1. Universe and data loading

- [x] 1.1 Query the current modelling universe from `ticker_universe`
      (`ingestion_state = 'ok' AND fails_liquidity_filter = 0 AND
      below_minimum_history = 0`) at run time — no hard-coded ticker list.
- [x] 1.2 Load each universe symbol's `ohlcv` history (close, for momentum
      signals) and confirm coverage: report how many of the 208 have data
      spanning enough sessions for the longest horizon (63) plus fold
      purge, and how many are excluded from this evaluation for
      insufficient span (distinct from the ingestion-time minimum-history
      filter, which is calibrated to the production pipeline's own
      warm-up needs, not this evaluation's 63-session horizon).
- [x] 1.3 Test: universe membership is read live; a symbol added to or
      removed from the modelling universe changes what 1.1 returns without
      code changes.

## 2. Multi-horizon purge (design Decision 1)

- [x] 2.1 Implement a local, horizon-parameterized label-date helper
      mirroring `_label_dates_by_ticker`'s logic (`backend/app/ml/
      training.py`) but taking the horizon as an argument instead of the
      fixed `TARGET_HORIZON` constant. Do not modify `training.py`.
- [x] 2.2 Implement the purge using this helper, following
      `purge_training_rows`'s logic (drop rows whose true label date lands
      at or after the fold boundary).
- [x] 2.3 Known-answer check: at horizon = `TARGET_HORIZON` (5), confirm
      this local implementation's purge output is equivalent to calling
      the existing `_label_dates_by_ticker` / `purge_training_rows` pair
      directly on the same data. This is the test that the generalization
      didn't introduce a subtle bug design Decision 1's risk entry flags.
- [x] 2.4 Reuse `compute_fold_boundaries` unmodified for fold construction.

## 3. Signal computation

- [x] 3.1 Compute `ret_h = ln(close[t] / close[t-h])` per symbol per date,
      for h in (5, 10, 21, 63).
- [x] 3.2 Compute the forward target `ln(close[t+h] / close[t])` per
      symbol per date, same horizons.
- [x] 3.3 Cross-sectionally demean both the signal and the forward target
      per date, across all universe symbols with a value on that date
      (design Decision 2).
- [x] 3.4 Test: demeaning is verified cross-sectional (against same-date
      peers), not a per-symbol historical mean — assert this on a small
      synthetic fixture where the two would disagree.

## 4. Walk-forward evaluation

- [x] 4.1 For each of the four horizons, run the walk-forward evaluation:
      for each fold boundary, purge (task group 2), then compute the
      correlation between demeaned signal and demeaned forward target in
      that fold's test period.
- [x] 4.2 Report per-fold correlation, not only the pooled figure, so sign
      instability is visible the way the original single-ticker findings
      reported it.
- [x] 4.3 Compute the decile-ranking construction (design Decision 3): rank
      symbols by demeaned signal within each test-period date, and report
      the average forward-return spread between the top and bottom decile,
      per fold.
- [x] 4.4 Report all four horizons together in the same output — no horizon
      is selected or highlighted after seeing which one scores best
      (spec requirement; design Risk "post-hoc horizon selection").

## 5. Effective breadth

- [x] 5.1 Compute the modelling universe's mean pairwise cross-sectional
      return correlation (ρ̄) directly from the 208-symbol universe's own
      data — do not reuse the ~0.41 figure measured earlier on 15 symbols.
- [x] 5.2 Compute an effective-breadth estimate from ρ̄ using
      `n / (1 + (n-1)ρ̄)` (design Decision 4), and report it alongside every
      correlation and decile figure, not as a separate, easy-to-skip
      section.

## 6. Durable script and verification

- [x] 6.1 Implement the evaluation as a script under `backend/scripts/`,
      runnable the same way existing scripts there are invoked (e.g.
      `report_ingest_outcomes.py`), with no undocumented setup step.
- [x] 6.2 Confirm re-running the script against an unchanged database
      reproduces the same figures (spec requirement). Document any
      intentional randomness with a fixed seed.
- [x] 6.3 Confirm the script makes no write to any table and does not read
      or write `backend/data/models/pooled_xgb_model.json` (spec
      requirement; this is read-only analysis).
- [x] 6.4 Run the script and capture its full output for task 7.

## 7. Verdict

- [x] 7.1 Append a new, dated section to `docs/DISCUSSION_model_direction.md`
      (design Decision 5) reporting: per-horizon correlation and decile
      spread (pooled and per-fold), effective breadth at the current
      universe size, and an explicit statement of whether the effect holds
      at scale — stated plainly whether the answer is yes, no, or
      inconclusive (spec requirement; design Risk "quietly reframed until
      positive").
- [x] 7.2 If the effect holds: name concrete prerequisites for using it —
      a ranking/screening surface that does not exist today, portfolio
      construction guidance, holdings data not yet collected — without
      committing to building any of them here.
- [x] 7.3 If the effect does not hold, or the multiple-comparisons/breadth
      caveats materially undercut it: state that as the finding, and note
      what (if anything) about `docs/MODEL_CARD.md`'s existing framing this
      confirms or updates.
- [x] 7.4 Note whether the recomputed ρ̄ (task 5.1) differs materially from
      the ~0.41 figure measured on the original 15 tickers, as its own
      small finding regardless of the main verdict.
