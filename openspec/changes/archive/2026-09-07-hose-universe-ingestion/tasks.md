## 0. Prerequisite — durable vnstock/vnai fix

- [x] 0.1 Land a durable fix for the `vnstock`/`vnai` prompt-injection
      auto-write recorded in `docs/KNOWN_ISSUES.md` (currently patched only
      inside the gitignored `backend/.venv`, lost on any reinstall). Pick one
      of: post-install hook, `sitecustomize.py`, vendored fork, or version
      pin. Design Migration Plan step 0 — must precede any work that
      rebuilds the venv.
- [x] 0.2 Verify after the fix that a fresh venv build regenerates neither
      `AGENTS.md` nor any of the six home-directory AI-config files listed
      in `KNOWN_ISSUES.md`, and that `pytest backend/tests` still passes.
- [x] 0.3 Update the `KNOWN_ISSUES.md` entry's status from "mitigated
      locally, not durably fixed" to reflect the fix actually landed.

## 1. Schema

- [x] 1.1 Add the universe table: symbol, exchange, `icb_code2`, listing
      status, first/last observed session, stale-close fraction, filter
      flags, per-symbol ingestion state and last error. Additive only —
      do not alter `tickers`, `ohlcv`, or `features` (design Decision 1).
- [x] 1.2 Add the quality-flag sidecar table keyed `(ticker, date)` holding
      only flagged rows, with flag tier (hard/soft) and the measured return
      (design Decision 4).
- [x] 1.3 Document both tables in `docs/DATA_DICTIONARY.md`, matching the
      existing column-by-column table format.

## 2. Universe construction

- [x] 2.1 Add a universe service reading
      `vnstock.explorer.vci.listing.Listing().symbols_by_exchange()`,
      filtering to `type = STOCK` and excluding `CW`/`ETF`/`BOND`/`FU`/
      `UNIT_TRUST`/`DEBENTURE` rows.
- [x] 2.2 Persist HOSE (`exchange = HSX`) stock rows to the universe table
      with `icb_code2` and listing status. Expected count ~405; treat 0 or a
      count above the listing's total `STOCK` rows as a construction
      failure rather than persisting.
- [x] 2.3 Persist delisted stock rows (`exchange = DELISTED`, `type =
      STOCK`, ~229 symbols) marked as delisted. Note open question 2 — these
      carry no historical exchange field.
- [x] 2.4 Handle a null `icb_code2` by storing null and continuing, not by
      skipping the symbol.
- [x] 2.5 Add point-in-time reconstruction: given a date `D`, return symbols
      whose first observed session is on or before `D` (design Decision 2).
- [x] 2.6 Tests: instrument-type filtering, delisted inclusion, point-in-time
      reconstruction including a symbol listed after `D` and a symbol
      delisted before today.

## 3. Quality gate

- [x] 3.1 Add the quality-gate module with per-exchange daily price limits
      (HOSE ±7%, HNX ±10%, UPCOM ±15%) as named constants.
- [x] 3.2 Implement the hard gate at the widest limit (±15%) plus tolerance
      (design Decision 3). New threshold — cite in code comment that it
      implements no domain rule 1-6.
- [x] 3.3 Implement the soft flag at the symbol's current-exchange limit,
      recording it as an unverified-fallback evaluation where dated
      membership is unknown (`ticker-universe` spec requires the fallback be
      explicit).
- [x] 3.4 Implement stale-close fraction per symbol (fraction of sessions
      where `close == prev close`), reusing the definition in
      `backend/scripts/screen_ticker_volatility.py`.
- [x] 3.5 Persist hard/soft flags to the sidecar and the stale-close fraction
      to the universe entry.
- [x] 3.6 Ensure hard-flagged rows are excluded or neutralised in feature and
      volatility computation, so one spurious return cannot distort every
      window containing it.
- [x] 3.7 Verification against the known-answer case, the existing 15
      tickers: `VHM` 2018-08-14 (a −0.69 log return, `60.30 -> 30.23`)
      hard-flagged; the 24 `ACB` (−0.10),
      `VIB` (−0.12), `VND` (−0.10) pre-migration rows soft-flagged only, never
      hard; the other 11 tickers entirely clean. Assert exact counts.

## 4. Wire the gate into ingestion

- [x] 4.1 Call the quality gate from `load_ticker` before persistence
      decisions, so flags and stale fraction are written in the same
      operation as the load.
- [x] 4.2 Persist flagged rows rather than rejecting the whole load, keeping
      the data inspectable.
- [x] 4.3 Update the universe entry's first/last observed session and
      ingestion state on every successful load.
- [x] 4.4 Confirm `load_ticker` handles a delisted symbol whose last session
      is years old without treating the absence of recent sessions as an
      error.
- [x] 4.5 Keep the existing single-call fetch contract intact —
      `mkt.equity(ticker).ohlcv(start="2000-01-01", end=today, count=5000,
      source="vci")`, `vnstock.ui.Market`, no chunking (existing
      `ticker-data-ingestion` spec; design Context).
- [x] 4.6 Tests: gate runs on load, flags persist, delisted symbol loads
      cleanly, existing single-call requirement still asserted.
- [x] 4.7 Implement design Decision 9: null indicator columns for the longest
      indicator lookback (78 sessions, Senkou Span B) following a
      hard-flagged session, mirroring how `near_gap` treats warm-up. A
      hard-flagged step is a persistent level shift, so any window spanning
      it blends two price scales. No schema change — the flag sidecar
      already carries what is needed.
- [x] 4.8 Tests for 4.7: indicators null through the lookback after a
      flagged session; indicators computed normally beyond it; the existing
      target-nulling behaviour (the 5 rows before the flag) is unchanged.

## 5. Backfill, and correctness fixes from review

Reopened after a post-implementation review of groups 4-5. Task 5.4 is the
substantive one and **must land before 6.8**, the full ingest, because that
run is what first produces mid-life blackouts where the calendar-gap flag
does not happen to mask them.

- [x] 5.1 Backfill universe entries for the 15 already-loaded tickers,
      including observed ranges and stale fractions, without re-fetching.
- [x] 5.2 Confirm the backfill actually populates `ohlcv_quality_flags` and
      `ticker_universe.stale_close_fraction` — both were empty after group
      3, so this is the first exercise of the persistence path tasks 3.5/3.6
      assume. Expected: 1 hard flag, 24 soft flags, 15 stale fractions.
- [x] 5.3 Re-run feature computation for the 15 and confirm both flag
      effects now take hold — `VHM`'s four pre-split targets (currently
      ≈ −0.68 to −0.70 in `features`) become null, and its indicator columns
      are null through the 78 sessions after 2018-08-14. Note these rows are
      all already `near_gap = 1`, so the training set does not change; this
      verifies the mechanism, not a data fix.
- [x] 5.4 Fix the null-feature gating gap found in review. The blackout nulls
      indicator columns but deliberately leaves `near_gap` alone (correctly —
      `near_gap` means calendar gaps, and `MODEL_CARD.md` quotes its ~35%
      exclusion rate as a specific figure that overloading would invalidate).
      But both consumers gate on `near_gap` alone, so blacked-out rows slip
      through with all 14 features null:
      (a) `filter_clean_labeled` (`backend/app/ml/training.py`) selects
      `near_gap == 0 AND target IS NOT NULL`, so they enter training as
      all-NaN vectors carrying valid labels — XGBoost fits them rather than
      erroring. VHM has 11 such rows today (2018-11-16 to 2018-11-30).
      (b) `backend/app/api/predictions.py` returns `status: "near_gap"` only
      when that flag is set, then builds the feature matrix and calls
      `model.predict()` — so a blacked-out latest row yields a
      confident-looking percentage computed entirely from missing values.
      Not reachable today (no ticker's latest row is affected) but reachable
      as soon as any ticker has a missed split within its last 78 sessions.
      Fix by having both call sites require the indicator columns to be
      non-null, rather than adding a flag column — it cannot drift out of
      sync with the actual nulls, and it also covers the `_wilder_smooth`
      short-series case in `docs/KNOWN_ISSUES.md`. Do **not** set
      `near_gap = 1` for blacked-out rows.
- [x] 5.5 Tests for 5.4: a row with null indicators and `near_gap = 0` is
      excluded from the training filter; a ticker whose latest features row
      has null indicators reports no prediction available rather than
      returning a number; VHM's 11 rows specifically are excluded. Assert
      the exact count so a regression is visible.
- [x] 5.6 Fix `install()` in `backend/app/vnstock_guard.py`: it returns
      `True` even when every patch target is missing, contradicting its own
      docstring ("False if vnai is installed but could not be patched").
      The loop `continue`s past each missing target, warns, then falls
      through to `return True`. Verified: with all four targets deleted it
      still returns `True`. Track whether any target was actually patched
      and return accordingly. Matters at a vnstock/vnai upgrade — the exact
      scenario the guard exists to survive, and 4.0.7/2.5.9 are already
      available against the pinned 4.0.5/2.5.5.
- [x] 5.7 Give `persist_quality_gate_result` an optional `conn` parameter,
      matching `hard_flagged_dates`, which already takes one with a docstring
      warning that omitting it "would read the real database even where the
      caller has been pointed at another one." Its sibling has the same
      hazard unguarded. Not currently biting, but it is an inconsistency in
      the one place the author already identified as dangerous.
- [x] 5.8 Give the dashboard a fifth prediction state for 5.4's new
      `status: "indicators_unavailable"`. `PredictionDisplay` branches on
      `'near_gap'` then `'ok'` and leaves `state = null` for anything else,
      so the card would render its title over an empty body — the blank
      treatment the `dashboard-ui` requirement forbids sharing across
      outcomes. Unreachable until 6.8's ingest produces a mid-life missed
      split, which is why it lands with group 5, not after. `ChartPanel`
      needs no change: it already gates the predicted point on
      `status !== 'ok'`.
- [x] 5.9 Apply 5.4's fix to `GET /tickers/{ticker}/insight` as well
      (`backend/app/api/insight.py`), a third consumer the review missed.
      It gates on `near_gap` alone, then calls `model.predict()` and feeds
      the result to `_compute_advice`, so a blacked-out latest row yields
      Advice derived entirely from missing values — worse than the
      prediction case, since Advice is Rule 3/6 output. Mirror the existing
      near_gap branch: keep Confidence and Sentiment, `advice_text: null`,
      and a note. The panel already renders `note` whenever Advice is
      absent, so no frontend change follows from this one.

- [x] 5.10 Resolve design Decision 10 (price-aware limit). The dry run's
      delisted penny stocks drew 43 hard flags (`VKP`) against 1 across the
      whole original 15: at 0.3-0.5 its price grid is 0.1, so one step is
      25% and every move it can make "breached" the 15% limit, voiding its
      whole history through the blackout. Widen the limit to
      `max(limit, one observed grid step)`, estimating the grid per symbol
      from its own non-zero close-to-close steps (a tick table would say
      0.01 for that band and fix nothing). Guard against inferring a grid
      from too little history. Verify the known-answer 15 are unchanged.
- [x] 5.11 Resolve design Decision 11 (recursive indicators). The
      78-session blackout bounds only the rolling-window indicators;
      `rsi`/`atr` (Wilder), `macd_*` (EWM from series start) and `obv`
      (cumsum) carry a level shift past any fixed span — measured 54.5%
      `macd_signal` error on the first row past the blackout. Segment the
      series at a hard flag and recompute those independently on each side;
      leave `target` and `near_gap` whole-series. Replace the two tests that
      compared a flagged run against an equally-contaminated baseline.
- [x] 5.12 Fix the gate's blind spots and batch hazards found while
      dry-running: a `close = 0.0` skipped because its return was ±inf
      (`VKP` has one); a price limit applied across a months-long trading
      halt as though it were a session-over-session move; per-gap log
      warnings that would emit ~8,000 lines over 634 symbols; an empty
      fetched frame crashing on `date.fromisoformat(nan)`; `pd.NA` feature
      values sqlite3 cannot bind, which silently emptied `features` for a
      short series; `ingestion_state` written as `ok` before feature
      recomputation, so a resume skipped symbols whose features failed; and
      a refetch narrowing the gate's input to the fetched window rather than
      the stored history, which would have deleted `VHM`'s hard flag on
      every refresh (task 6.9).

## 6. Batch ingestion

- [x] 6.1 Add a batch ingestion script under `backend/scripts/` (matching
      where `screen_ticker_volatility.py` lives), driving the existing
      `load_ticker` — no second fetch implementation (design Decision 6).
- [x] 6.2 Handle `RateLimitError` by waiting and continuing rather than
      aborting the run.
      **Corrected 2026-09-07 after the first full attempt died at symbol 12
      of 634.** `RateLimitError` is the wrong mechanism to handle: vnai's
      limiter calls `sys.exit("Rate limit exceeded. ... Process terminated.")`
      from a context manager (`vnai/beam/quota.py:313`), so the rate limit
      arrives as `SystemExit` — a BaseException `except Exception` cannot
      see — and `load_ticker`'s `RateLimitError` branch never fires on the
      guest tier at all. Now handled in two layers: the run is *paced* to 8
      symbols a minute (under the 20 requests/minute guest cap at ~2 requests
      per load), and a rate-limit `SystemExit` is caught and waited out, with
      the message checked so a genuine exit still terminates. Do not
      "simplify" this back to catching `RateLimitError`.
- [x] 6.3 Make the run resumable from the universe table's per-symbol
      ingestion state, skipping already-ingested symbols by default.
- [x] 6.4 Record per-symbol failures and continue with remaining symbols.
- [x] 6.5 Recompute features only for symbols the run actually fetched or
      updated, never the whole universe (design Decision 7).
- [x] 6.6 Persist a run summary separating fetch failures from
      quality-gate/liquidity/minimum-history exclusions.
- [x] 6.7 Dry-run the script over a small subset (10-20 symbols, including at
      least one delisted and one short-history symbol such as `XDC`) before
      any full run. Record elapsed time per symbol, split between fetch and
      feature recomputation, and extrapolate the full run's duration — 619
      symbols at an unmeasured rate is the one cost in this change nobody
      has a number for, and design Decision 7 predicts recomputation
      dominates.
      **Done 2026-09-07, 14 symbols** (7 listed, 3 delisted incl. `VSP`/`VKP`/
      `VMI`, `XDC` at 68 rows, plus `ITA` which turned out to be outside the
      universe). Decision 7's prediction was wrong: recomputation is 0.2s per
      symbol, fetch 0.8-3.9s, and the binding constraint is vnstock's guest
      tier at **20 requests/minute** (~2 per symbol) — the run stopped for a
      rate limit after its tenth symbol. Full run ≈ 1 hour, throttle-bound.
      Also surfaced: a `close = 0.0` the gate used to skip, penny-stock hard
      flags (`VKP` 43), and 6 of 24 loaded symbols now failing the liquidity
      filter. See design Decisions 10 and 11.
- [x] 6.8 Execute the full batch ingestion over all 634 universe symbols —
      405 listed plus all 229 delisted (design open question 2, resolved:
      ingest everything, filter at query time, since delisted rows carry no
      historical exchange field).
      **Run 2026-09-07: 634 attempted, 599 succeeded, 1,043,790 OHLCV rows.**
      35 failures — 34 `no_data` (delisted names the source no longer serves)
      and 1 `error` (`HDO`, where vnstock's own `ohlc_to_df` cannot cast a
      NaN volume to int). **Zero rate-limit waits**: pacing at 8 symbols a
      minute kept the run entirely under the guest cap, so the reactive
      `SystemExit` handler never had to fire. 787s of actual work (fetch
      374s, features 174s) spread over ~80 minutes of pacing.
- [x] 6.9 Refresh the 15 already-ingested tickers as part of this first full
      run rather than skipping them. Their last sessions currently span
      2026-08-12 to 2026-08-28 while the other 619 would arrive current, and
      6.3's skip-already-ingested default would preserve that spread. A
      ragged last-session edge is survivable for volatility work but not for
      cross-sectional ranking, where it means comparing a stale ticker
      against a fresh universe on the same as-of date — a misalignment that
      manufactures apparent signal.
      Run with `--include-ingested`, which refreshed all 15 along with the
      rest. The spread closed from 16 days across the original 15 to
      **370 of 405 listed symbols at 2026-09-07**; the 35 behind are
      genuinely stale rather than skipped (19 at 2026-09-04, then a tail out
      to 2026-04-29 — symbols still listed but not currently trading). The
      known-answer verification passed *after* the refresh, which is the
      regression task 5.12 was fixed for: gating the fetched window instead
      of the stored history would have deleted `VHM`'s hard flag here.
- [x] 6.10 Add a last-session spread check reporting the distribution of
      `last_observed_session` across the modelling universe, so a ragged
      universe cannot be used unknowingly. Keep it permanently, not just for
      this run: the same drift reappears on every incremental ingest.

## 7. Thresholds and universe filters

Deliberately after group 6: both thresholds must be picked from the observed
distribution across the real universe, and `observed_session_count` /
`stale_close_fraction` are only populated by ingestion (task 4.3), not by
universe construction.

- [x] 7.1 Pick the minimum-history threshold empirically from the
      distribution of observed session counts across the ingested universe
      (design open question 1). New threshold — implements no domain rule
      1-6; record the chosen value and its basis.
      **250 sessions** (`MINIMUM_HISTORY_SESSIONS`). The distribution turned
      out to be no help: min 1, p10 1,182, median 1,987, max 2,022 — bimodal,
      with almost everything pinned at the ~8-year tier ceiling and a thin
      short tail, so there is no natural gap to cut at. Derived instead from
      the pipeline's own arithmetic: 78 sessions to the indicator warm-up, a
      60-session Advice volatility window, 30 clean rows for a single-ticker
      backtest. 250 leaves ~170 usable rows. Excludes 26 of 599.
- [x] 7.2 Re-examine `STALE_PRICE_WARN_THRESHOLD = 0.15` against the real
      distribution before enforcing it. The existing 15 large-caps measure
      0.056-0.116, so `VIB` and `ACB` already sit at ~75% of the cutoff —
      a threshold that originated as a warning in a 9-candidate screening
      script. Confirm or revise, and record which.
      **Confirmed at 0.15.** Full distribution across 599 ingested symbols:
      min 0.000, p25 0.115, median 0.224, p75 0.572, max 0.999. It excludes
      380 of 599 (63%), but looser cuts rescue less than the number suggests
      — 0.25 excludes 41%, 0.40 excludes 30%, and even 0.60 still excludes
      24%. Much of HOSE below the large caps genuinely is that thin.
      **Known weakness recorded in the code**: this measure conflates
      illiquidity with coarse-grid pricing (design Decision 10) — a symbol
      at 0.3 on a 0.1 grid cannot post a small move, so it is penalised
      twice. A measure that does not interact with the grid (zero-volume
      session fraction) is the better fix and is follow-up work; because the
      filter excludes on read and retains every measurement, revising it
      later costs a re-filter, not a re-ingest.
- [x] 7.3 Enforce the liquidity filter at the modelling-universe boundary,
      retaining the measured value per symbol so the threshold stays
      re-tunable without re-ingestion (design Decision 5).
      Done via `ticker_universe.modelling_universe()`, which is the read-time
      boundary: it excludes symbols failing the liquidity or minimum-history
      filters, keeps delisted symbols by default (excluding them is the
      survivorship bias this change removes), and leaves every row and
      measurement in place. Also added `modelling_universe(as_of=...)`,
      which requires the symbol to have been *trading* at that date —
      deliberately stricter than `universe_as_of`, whose spec'd "includes or
      precedes `D`" keeps a long-delisted symbol in the set. Both are
      documented so a caller picks knowingly.
- [x] 7.4 Flag below-minimum-history symbols rather than deleting them, so
      exclusions are visible and reversible.
      Applied at 250 sessions: 599 symbols measured, **26 flagged**, none
      deleted, every `observed_session_count` retained. Combined with the
      liquidity filter this leaves a modelling universe of **208 of 599
      ingested (35%)**.
- [x] 7.5 Tests: filters exclude from the default modelling universe while
      leaving data and measurements in place.
      Covers both filters, that flagging never deletes, that a never-ingested
      symbol is not mistaken for a too-short one, that delisted symbols stay
      in by default, and the as-of boundary.

## 8. Catalog switch

Deliberately after group 7: `GET /tickers` applies the universe's default
filters, which do not exist until 7.3/7.4 define them. Switching earlier
would serve all 634 symbols, delisted names included, to a frontend built
for nine.

- [x] 8.1 Change `GET /tickers` to derive from the universe table with
      default filters applied, replacing the `TRAINING_TICKERS` read
      (`ticker-catalog` MODIFIED requirement).
      One deviation, recorded in the delta spec: every `TRAINING_TICKERS`
      member is served whether or not it passes the filters, and whether or
      not the universe has a row for it. The model was trained on those
      nine, so the dashboard must be able to show and predict them; losing
      one to a re-tuned liquidity threshold (task 7.2) would leave the UI
      silently inconsistent with the model. None fails a filter today.
- [x] 8.2 Add a per-entry flag marking membership in `TRAINING_TICKERS`, and
      add exchange, industry classification, and listing status to each
      entry, using null where the universe has no value rather than omitting
      the field.
      `in_training_set`, `exchange`, `industry_code` (`icb_code2`) and
      `listing_status`, alongside the existing `loaded` /
      `features_computed` / `last_loaded_at`. Training tickers come first in
      their declared order so the dashboard's watchlist keeps the order it
      has always rendered in; the rest follow alphabetically.
- [x] 8.3 Confirm `GET /tickers` stays read-only and makes no vnstock call
      even with hundreds of unloaded symbols in the universe.
      Asserted with 600 seeded universe symbols and `mkt.equity` patched to
      raise.
- [x] 8.4 Tests: catalog derives from universe, training flag matches
      `TRAINING_TICKERS` exactly, delisted entries distinguishable, no
      side effects, no fetch for unloaded symbols.
      Plus the two deviation cases (a filtered-out training ticker and one
      absent from the universe) and the default filters excluding illiquid,
      too-short and not-yet-ingested symbols.
- [x] 8.5 Verify the frontend ticker panel still renders with a
      universe-sized catalog — the fixed 9-chip watchlist and the searched-
      ticker list were built for a 9-ticker catalog and now receive
      hundreds. Behaviour change only if it breaks; no redesign here.
      It did break: `TickerPanel` rendered one chip per catalog entry, so a
      universe-sized catalog put hundreds into the Watchlist's wrapping
      row — the same unbounded-list problem the searched-ticker group was
      split out for. Fixed by selecting the Watchlist on 8.2's
      `in_training_set` flag; the full catalog still feeds `knownTickers`,
      so searching a universe symbol resolves instead of re-loading it. No
      redesign, and the searched-ticker list is untouched. Test asserts one
      chip from a 301-entry catalog. The `GET /tickers` JSDoc contract in
      `frontend/src/api/tickers.js` is updated to match.

## 9. Documentation and close-out

- [x] 9.1 Record actual outcomes: symbols ingested, hard/soft flag counts,
      liquidity and minimum-history exclusions, failures. Compare the
      observed gate-trigger rate against the 0.08% measured on the original
      15, and classify hard flags into three categories, not two: missed
      split adjustments (a persistent level step, like VHM), genuine bad
      data (a spike that reverts), and post-suspension resumptions (which
      gap legitimately). Conflating resumptions with splits would skew
      Decision 9's reopening trigger.
      This number is Decision 9's named trigger: a rate far above the
      1-hard-flag-in-15-tickers measured here means the ~0.26% data cost is
      materially larger and detect-and-repair should be reconsidered.
      **Recorded 2026-09-07 via `backend/scripts/report_ingest_outcomes.py`,
      which recomputes all of it on demand rather than freezing it here:**
      599 ingested (405 listed, 194 delisted), 1,044,135 OHLCV rows, 35
      failures (34 `no_data`, 1 `error`). 2,761 hard flags across 183
      symbols, 2,806 soft. Flagged-row rate **0.533%, 6.7x** the 0.08%
      pre-expansion baseline — so **Decision 9's trigger has fired**.
      The three-way classification it demanded, which is what keeps that
      trigger honest: **1,127 `invalid_close`** (no price at all — resolved
      by Decision 12), **864 `missed_split`** (persistent level step, the
      `VHM` shape), **770 `bad_print`** (a spike that reverts). Conflating
      them would have read as a 6.7x split rate; the actual missed-split
      share is under a third of the flags. Filters: 380 fail liquidity, 26
      below minimum history, leaving 208 of 599. `near_gap` excludes 35.6%
      of rows at universe scale — indistinguishable from the ~35% MODEL_CARD
      records for the 9, which answers design open question 3.
- [x] 9.2 Update `docs/MODEL_CARD.md`'s scope notes — the "all 9 tickers are
      large-cap, liquid VN30 constituents" limitation and the small/mid-cap
      unvalidated note now describe the training set only, not the data
      available.
      Also records why the gap now matters operationally: a prediction
      served for a searched-in small-cap is the same extrapolation it always
      was, but far easier to request by accident, which is what
      `in_training_set` in `GET /tickers` exists to expose. Plus the two
      measured properties of the wider universe that bear on any retrain —
      the liquidity-filter fraction and the coarse price grid at low prices
      (design Decision 10).
- [x] 9.3 Append the resolution of design open questions 1-4 and Decision 9
      to the design doc, or record them as still open with what was learned.
      **Questions 1-4 all closed**: (1) minimum history = 250 sessions, with
      why the distribution could not decide it; (2) already resolved
      2026-08-28 (ingest all delisted, filter at query time); (3) answered
      *no* — `near_gap` excludes 35.6% at universe scale, matching the ~35%
      MODEL_CARD records for the 9; (4) HNX declined for now, schema
      unchanged so it stays cheap to revisit. A fifth item was added rather
      than resolved: the 8-year tier ceiling, which means the
      survivorship-free universe effectively begins in 2018 and bounds every
      claim made over this data.
      **Decision 9 reopened and superseded** by what the ingest measured:
      Decision 10 (price-grid-aware limits), Decision 11 (segmenting the
      recursive indicators, since the 78-session blackout never bounded
      them), Decision 12 (a zero close is absent data, not a level shift —
      1,127 flags across 42 symbols) and Decision 13, which is **left open
      deliberately**: 770 of the hard flags are reverting spikes rather than
      level shifts, and whether they should keep receiving the full
      blackout-and-segment treatment is a judgement call with a real data
      cost either way. It does not block anything already built; it decides
      how much of the universe survives filtering, so it wants an answer
      before anything trains on it.
- [x] 9.4 Preserve the diagnostic scripts behind
      `docs/DISCUSSION_model_direction.md` as durable scripts under
      `backend/scripts/`, so the pre-expansion baseline stays reproducible
      against the new data rather than remembered (that doc's "Reproducing
      these numbers" section).
      `backend/scripts/baseline_model_diagnostics.py`, read-only, covering
      Findings 1, 2 and 7. Verified to reproduce the doc's figures exactly:
      `sd(actual)` 0.0506, `sd(predicted)` 0.0076, `corr` 0.0095, the 6.7x
      dispersion ratio, the full per-fold table, `obv`'s 96 splits, and
      Finding 7's 0.411 / 0.21 / 0.70 correlations with 2.2 independent
      bets. `--doc-baseline` pins the 15 tickers loaded when the doc was
      written, so its numbers do not drift as the universe grows.
      **Scoped deliberately**: Findings 3-5 are experiments proposing the
      volatility/interval pivot, not baseline measurements — reproducing
      them means implementing a change this proposal lists as a non-goal.
      Finding 8's price-limit scan is superseded by the quality gate and
      `verify_quality_gate.py`, which asserts rather than prints. The doc's
      "the scripts are not preserved anywhere in this repo" note is
      updated.
