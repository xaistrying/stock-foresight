## Context

M1 is the first thing built in this repo: `backend/` is currently empty.
This design establishes the ingestion path (vnstock → SQLite) that M2
(feature engineering) and M3 (training) will read from, and the schema
that `docs/DATA_DICTIONARY.md` will document.

No existing specs or schema constrain this work — decisions below are new,
not modifications. None of the 6 non-negotiable domain rules apply: this
change is pure data ingestion, upstream of the prediction target, UI
display, and advice/confidence logic. Each decision below is new (not yet
covered by a prior design), per the rule requiring that citation.

## Goals / Non-Goals

**Goals:**
- One endpoint, `POST /tickers/{ticker}/load`, that works identically for a
  ticker's first load and any subsequent reload.
- Durable, self-healing storage: reloading a ticker never produces
  duplicate or conflicting rows.
- Make the community-tier ~8-year history cap visible as data (`tickers`
  columns) rather than silently truncating with no trace.
- Flag likely fetch problems (multi-day gaps) without blocking ingestion.

**Non-Goals:**
- Fetching beyond the ~8-year tier limit (walk-back/chunking). Shelved
  after an unexplained `ValueError` on a second-hop attempt; not
  reattempted until root-caused.
- VN30/index-based universe (batch) seeding — M5.
- Delta-fetch / staleness-aware refresh that skips already-fresh data — M5,
  once batch-seeding cost makes a full refetch expensive.
- Real rate-limit handling/backoff — scaffolding only in M1; the try/except
  around `RateLimitError` is not exercised at single-ticker scale.
- Resolving the ambiguity in `available_since` (true listing date vs. tier
  boundary) — not resolvable from a single API call; left as a labeled
  ambiguity for a human or a future data source to resolve.

## Decisions

**D1. Single fetch call, no chunking/walk-back.**
`mkt.equity(ticker).ohlcv(start="2000-01-01", end=today, count=5000,
source="vci")`, one call per request. Alternative considered: multi-hop
walk-back to exceed the 8-year cap — tried previously, produced an
unexplained `ValueError` on the second hop, shelved as an unresolved
failure mode, not reattempted. Revisit only if M3 backtesting shows 8
years is insufficient signal.

**D2. `count` is always explicit and large (5000).**
Omitting `count` was observed to silently default to ~100 rows — a silent
data-loss failure mode with no error raised. Always passing an explicit
large value removes that failure mode entirely; 5000 comfortably exceeds
8 years of trading sessions (~2000 rows).

**D3. `start` is a fixed constant (`"2000-01-01"`), not `today - 8y`.**
Confirmed behaviorally equivalent to a computed offset in this project's
testing, since the tier cap binds regardless of how far back `start`
requests. A fixed constant avoids a date-math dependency for no behavioral
gain.

**D4. `source="vci"` exclusively.**
Both available sources enforce the identical 8-year cap, so there's no
depth advantage to switching. Using one source consistently for both
initial load and every reload avoids cross-vendor rounding/adjustment
discontinuities that would otherwise appear as spurious jumps in the
return series.

**D5. Single endpoint serves both first-load and reload; both tables
upserted every call.**
`ON CONFLICT(ticker, date) DO UPDATE` on `ohlcv`, and an upsert on
`tickers`, run identically whether the ticker is new or already loaded.
Alternative considered: a separate refresh/delta endpoint — rejected for
M1 as premature; M5 batch-seeding is where fetch cost first matters enough
to justify delta logic.

**D6. Time-of-day (07:00:00) stripped at ingestion, not at read time.**
vnstock returns timestamps with a constant 07:00:00 time-of-day component
(a quirk of the source). Stored as date-only ISO TEXT so every downstream
consumer (M2 features, M3 training, UI) works with plain dates without
each needing to know about or re-strip this quirk.

**D7. Gap check logs, does not fail ingestion.**
A >5-calendar-day gap between consecutive stored sessions for a ticker is
logged as a heuristic signal of a likely fetch problem. It's deliberately
not a hard failure because genuine VN holiday clusters (e.g. Tet) can
plausibly exceed 5 days and are not errors. New heuristic, not tied to any
domain rule.

**D8. `possibly_truncated_by_tier` is a label only — never gates writes.**
Computed as `abs(available_since - (end - 8y)) <= 30 days`. The 30-day
tolerance is sized against ~10 days of observed truncation jitter across
two manually-checked tickers (VIB, TCB) — not against the true population
distribution of listing dates, which is unmeasured. Consequence of that
calibration gap: this heuristic is more likely to over-flag a genuinely
young ticker as tier-truncated than to miss a real truncation. Because
it's a label, not a gate, that asymmetry costs nothing at write time — it
only affects what a human or downstream UI is told to double-check. New
heuristic, not tied to any domain rule.

**D9. `RateLimitError` wrapped in try/except as scaffolding.**
At M1's single-ticker, on-demand scale, this path is not expected to be
exercised. It exists so the exception has a defined landing spot ahead of
M5, when VN30 batch seeding will need real enforcement (backoff, queuing,
or similar) — that logic is explicitly deferred, not designed here.

## Risks / Trade-offs

- [Risk] `available_since` is ambiguous (true listing date vs. tier
  boundary) and not resolvable from one API call → Mitigation: expose both
  `available_since` and `possibly_truncated_by_tier` as separate columns so
  the ambiguity is visible in data rather than silently baked into a
  single field; document the ambiguity in `docs/DATA_DICTIONARY.md`.
- [Risk] `possibly_truncated_by_tier`'s 30-day tolerance is calibrated on
  only 2 tickers and skews toward over-flagging → Mitigation: label-only
  design (D8) means a wrong flag never blocks or corrupts a write; treat
  the flag as a hint to check manually, not ground truth, until recalibrated
  on a larger sample.
- [Risk] Gap-check heuristic (>5 calendar days) may flag legitimate VN
  holiday clusters as suspicious → Mitigation: log-only (D7), never fails
  ingestion; a human reviewing logs can distinguish a known holiday period
  from a real fetch problem.
- [Risk] No real rate-limit handling means a burst of manual reloads could
  hit vnstock's limit with no graceful recovery → Mitigation: accepted for
  M1 given single-ticker, on-demand usage; explicitly flagged as an M5
  concern once batch seeding increases call volume.
- [Trade-off] Single `source="vci"` forgoes any cross-checking between
  vendors that might catch data-quality issues → accepted because both
  sources share the same tier cap (no depth gain) and consistency across
  reloads (D4) was judged more valuable than cross-vendor validation for
  v1.

## Migration Plan

Additive only — new tables (`ohlcv`, `tickers`) in a database that does not
yet exist (`backend/data/app.db` is created fresh by this change). No
existing rows or schema to migrate. Rollback is deleting the new tables/db
file; no other system depends on them yet.

## Open Questions

- None blocking implementation. The `available_since` ambiguity and the
  `possibly_truncated_by_tier` calibration gap are known limitations
  (documented above and in `docs/DATA_DICTIONARY.md`), not open questions —
  they're accepted as-is for v1 per the proposal.
