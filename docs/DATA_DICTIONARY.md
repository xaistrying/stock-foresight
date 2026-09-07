# Data Dictionary

Schema and known quirks for the data ingested by
`backend/app/services/ticker_ingestion.py` (`POST /tickers/{ticker}/load`).
Source: [ticker_ingestion.py](../backend/app/services/ticker_ingestion.py),
[schema.py](../backend/app/db/schema.py). Design rationale:
`openspec/changes/data-ingestion-vnstock/design.md`.

## Tables

### `ohlcv`

| Column | Type | Notes |
| --- | --- | --- |
| `ticker` | TEXT NOT NULL | Part of primary key |
| `date` | TEXT NOT NULL | Date-only ISO (`YYYY-MM-DD`); see [Time-of-day quirk](#time-of-day-quirk) |
| `open` | REAL NOT NULL | |
| `high` | REAL NOT NULL | |
| `low` | REAL NOT NULL | |
| `close` | REAL NOT NULL | |
| `volume` | INTEGER NOT NULL | |

Primary key: `(ticker, date)`. Upserted via `ON CONFLICT(ticker, date) DO
UPDATE` on every load, so a reload for a ticker overwrites existing rows for
the same `(ticker, date)` instead of duplicating them.

### `tickers`

| Column | Type | Notes |
| --- | --- | --- |
| `ticker` | TEXT PRIMARY KEY | |
| `available_since` | TEXT | `min(date)` from the most recent load; see [ambiguity](#available_since-ambiguity) |
| `possibly_truncated_by_tier` | INTEGER | `0`/`1` heuristic flag; see [calibration caveat](#possibly_truncated_by_tier-calibration-caveat) |
| `last_loaded_at` | TEXT | ISO timestamp of the most recent successful load |

Upserted via `ON CONFLICT(ticker) DO UPDATE` on every load, first load and
reload alike.

### `features`

Engineered technical-analysis features and the prediction target, one row
per `(ticker, date)`, computed from `ohlcv` by
[feature_engineering.py](../backend/app/ml/feature_engineering.py). Design
rationale: `openspec/changes/feature-engineering-ta/design.md`.

**Indicator computation approach: hand-rolled (pandas/numpy), not a
library.** `pandas-ta` was considered and rejected — it has had no PyPI
release since 2021 and is known to break on current numpy (it imports
`numpy.NaN`, removed in numpy>=1.24). Ichimoku, RSI, MACD, Bollinger Bands,
ATR, and OBV are all short, well-known formulas, so hand-rolling with
`pandas`/`numpy` (both added to `backend/requirements.txt`) avoids taking on
an unmaintained dependency and keeps every parameter (periods, smoothing)
explicit in code rather than relying on a library's silent defaults. See
`openspec/changes/feature-engineering-ta/design.md` Decision 4.

| Column | Type | Parameters | Warm-up window | Notes |
| --- | --- | --- | --- | --- |
| `ticker` | TEXT NOT NULL | | | Part of primary key |
| `date` | TEXT NOT NULL | | | Part of primary key |
| `tenkan_sen` | REAL | period 9 | 9 rows | Ichimoku conversion line: `(max(high, 9) + min(low, 9)) / 2` |
| `kijun_sen` | REAL | period 26 | 26 rows | Ichimoku base line: `(max(high, 26) + min(low, 26)) / 2` |
| `senkou_span_a` | REAL | Tenkan/Kijun 9/26, shift 26 | 52 rows | `(tenkan_sen + kijun_sen) / 2` as of `date - 26`, forward-shifted to align with the current row — safe to store since it only uses data on or before `date` |
| `senkou_span_b` | REAL | period 52, shift 26 | 78 rows | `(max(high, 52) + min(low, 52)) / 2` as of `date - 26`, forward-shifted; longest lookback of any column — used as the reference window for `near_gap` |
| `chikou_signal` | REAL | offset 26 | 27 rows | Leakage-safe replacement for the textbook (backward-shifted) Chikou Span: `close(date) - close(date - 26)`, never `close(date + 26)`. See design Decision 6 |
| `rsi` | REAL | period 14, Wilder smoothing | 15 rows | Wilder's method: simple-mean seed over the first 14 deltas, then recursively smoothed — not an unseeded EWM |
| `macd_line` | REAL | fast/slow 12/26 | 26 rows | `EMA(close, 12) - EMA(close, 26)`, `adjust=False` |
| `macd_signal` | REAL | signal 9 | 34 rows | `EMA(macd_line, 9)`, `adjust=False` |
| `macd_histogram` | REAL | fast/slow/signal 12/26/9 | 34 rows | `macd_line - macd_signal` |
| `bb_upper` | REAL | period 20, 2 std | 20 rows | `SMA(close, 20) + 2 * population_std(close, 20)` |
| `bb_middle` | REAL | period 20 | 20 rows | `SMA(close, 20)` |
| `bb_lower` | REAL | period 20, 2 std | 20 rows | `SMA(close, 20) - 2 * population_std(close, 20)` |
| `atr` | REAL | period 14, Wilder smoothing | 15 rows | True Range = `max(high-low, \|high-prev_close\|, \|low-prev_close\|)`, then Wilder-smoothed (same seeding as RSI) |
| `obv` | REAL | | full ticker history | Cumulative signed volume from the ticker's earliest stored row; not a bounded window — see Decision 5 below |
| `target` | REAL | horizon 5 sessions | n/a (looks forward, not back) | Rule 1: `ln(close[t+5] / close[t])`, 5 TRADING SESSIONS ahead (row offset, not calendar days); `NULL` for a ticker's last 5 stored sessions (insufficient future data) — the row is still written with feature columns populated. Also `NULL` for the 5 sessions before a hard-flagged one; see [hard-flag nulling](#hard-flag-nulling-in-features) |
| `near_gap` | INTEGER NOT NULL | | | `1`/`0`; see semantics below |
| `computed_at` | TEXT NOT NULL | | | ISO timestamp set on every upsert; see caveat below |

Primary key: `(ticker, date)`. Upserted via `ON CONFLICT(ticker, date) DO
UPDATE` on every recompute, matching `ohlcv`/`tickers`' upsert pattern.
Recomputing a ticker's features always replaces its **entire** stored series
from the earliest `ohlcv` row, never incrementally — required for `obv`'s
correctness (design Decision 5), applied uniformly to all columns for
simplicity.

"Warm-up window" above is the number of leading rows (from the ticker's
first stored session) that must exist before that column's first non-null
value; a column is `NULL` for any row still inside its warm-up. `78` rows =
Ichimoku's Senkou Span B, computed from a 52-row window and then
forward-shifted 26 rows — the longest of any column, and the window
`near_gap` checks against.

#### `near_gap` semantics

`near_gap = 1` when the input window feeding a row's **longest** indicator
lookback (`senkou_span_b`'s 52-row window, forward-shifted 26 rows — i.e.
row positions `[date_row - 77, date_row - 26]`, 0-indexed within the
ticker's stored sequence) either:

- extends before the ticker's first stored row, or
- overlaps a session-to-session gap greater than 5 calendar days (M1's
  advisory gap-detection rule, re-derived in `detect_gaps`).

`near_gap` is **advisory only, not a filter** — it never blocks, drops, or
nulls out a row's indicator values. All indicator/target columns are still
computed and written for `near_gap = 1` rows using whatever sequential data
is actually available; this mirrors M1's posture of logging gaps without
repairing or filtering around them. Downstream consumers (M3 training) may
choose to exclude or downweight `near_gap = 1` rows — that choice is not
made here.

#### Hard-flag nulling in `features`

A `flag_tier = 'hard'` row in `ohlcv_quality_flags` nulls two disjoint spans
of `features`, in opposite directions along the series. Both are recomputed
from the sidecar on every recompute, so clearing a flag restores the values.

| Span | Columns nulled | Why |
| --- | --- | --- |
| The 5 rows (`TARGET_HORIZON`) **before** the flagged session | `target` only | `target(t)` spans `close[t]` to `close[t+5]`, so it carries the spurious step exactly when `t < d <= t + 5`. `target(d)` itself spans two closes on the far side of the step and stays valid |
| The flagged session **and** the 77 after it (78 = the longest indicator lookback) | every indicator column — everything but `target` and `near_gap` | A hard flag is a persistent level shift (the one measured case, `VHM` 2018-08-14, is a missed 2:1 split), so every rolling window reaching across it blends two price scales. Design Decision 9 |

The blackout starts at the flagged session, not after it: a 20-row window
ending on `d` already contains both `close[d-1]` and `close[d]`. It uses the
longest lookback uniformly rather than each column's own window length,
mirroring what `near_gap` does for warm-up.

Two consequences worth knowing when reading the table:

- An indicator `NULL` no longer means only "inside the warm-up window". Join
  against `ohlcv_quality_flags` to tell the two apart.
- `obv` is blacked out with the rest, but its contamination is **not** bounded
  by the 78 rows. It is a cumulative sum, so a spurious direction at the step
  shifts every later value permanently. The blackout hides the affected span;
  it does not repair `obv`.

`near_gap` is deliberately untouched — it describes calendar gaps, not price
discontinuities, and is the blackout's model rather than its subject. In the
`VHM` case every blacked-out row is already `near_gap = 1` anyway, since the
split fell 10 sessions after listing.

#### `computed_at` staleness caveat

`computed_at` records **when** a row was computed, not **what indicator
parameters** produced it — it is not a parameter-version column. If
indicator periods/definitions change later, rows whose `computed_at`
predates that change are the ones that are stale relative to the new
definition, assuming a reload triggers Decision 5's full per-ticker
recompute. See design Decision 8.

### `ticker_universe`

The set of symbols the system knows about, one row per symbol. Distinct from
`tickers`, which means "something we have loaded" — a `ticker_universe` row
exists for symbols never fetched and for symbols whose fetch failed. Design
rationale: `openspec/changes/hose-universe-ingestion/design.md` Decision 1.

The key column is `symbol`, not `ticker`. This table is the authority on what
a symbol *is*; `ohlcv`, `features`, and `tickers` key on `ticker` as the thing
being loaded. Joins read `ticker_universe.symbol = tickers.ticker`.

| Column | Type | Notes |
| --- | --- | --- |
| `symbol` | TEXT PRIMARY KEY | Exchange ticker symbol |
| `exchange` | TEXT | Current-state exchange from the listing (`HSX`, `HNX`, `UPCOM`); null for delisted symbols, which carry no exchange field |
| `exchange_is_unverified_fallback` | INTEGER NOT NULL DEFAULT 1 | `1` when `exchange` is current state standing in for unknown dated membership; see [dated exchange membership](#dated-exchange-membership-is-not-available) |
| `icb_code2` | TEXT | ICB industry classification from the listing; nullable — a missing code does not block ingestion |
| `listing_status` | TEXT NOT NULL | `listed` or `delisted` |
| `first_observed_session` | TEXT | `min(date)` from this symbol's `ohlcv`; null until first load |
| `last_observed_session` | TEXT | `max(date)` from this symbol's `ohlcv`; null until first load. For a delisted symbol this is years old by design, not a staleness fault |
| `observed_session_count` | INTEGER | Row count in `ohlcv` for this symbol; null until first load |
| `stale_close_fraction` | REAL | Fraction of sessions where `close == prev close`; see [stale-close fraction scope](#stale-close-fraction-scope) |
| `fails_liquidity_filter` | INTEGER | `0`/`1`; `stale_close_fraction` above threshold. Measurement retained so the threshold stays re-tunable without re-ingesting |
| `below_minimum_history` | INTEGER | `0`/`1`; too few observed sessions. Flagged, never deleted, so the exclusion is visible and reversible |
| `ingestion_state` | TEXT NOT NULL DEFAULT 'pending' | `pending`, `ok`, `features_failed` (fetch succeeded, feature recomputation raised), `failed` (unexpected exception), or `load_ticker`'s own failure status (`rate_limited`, `no_data`, `invalid_symbol`). Doubles as the batch runner's resume point — no separate checkpoint file. A resume retries every state except `ok`, `no_data` and `invalid_symbol`, since those last two will not change on a retry |
| `ingestion_last_error` | TEXT | Last failure message, null on success |
| `ingestion_attempted_at` | TEXT | ISO timestamp of the most recent attempt, successful or not |
| `updated_at` | TEXT NOT NULL | ISO timestamp of the most recent write to this row |

### `ohlcv_quality_flags`

Sidecar holding **only** OHLCV rows that failed a price-limit check, keyed
`(ticker, date)` to match `ohlcv`. Flag columns are not on `ohlcv` itself
because `ohlcv` is upserted wholesale on every reload, which would mean
recomputing and rewriting flags for every row of every load; design Decision
4.

| Column | Type | Notes |
| --- | --- | --- |
| `ticker` | TEXT NOT NULL | Part of primary key; matches `ohlcv.ticker` |
| `date` | TEXT NOT NULL | Part of primary key; matches `ohlcv.date` |
| `flag_tier` | TEXT NOT NULL | `hard` (excluded from modelling inputs) or `soft` (recorded for review only); see [flag tiers](#hard-implies-soft-in-flag_tier) |
| `flag_reason` | TEXT NOT NULL DEFAULT 'price_limit' | Why the row was flagged: `price_limit` (a move beyond the applicable daily limit — a missed split adjustment or a bad print), `invalid_close` (the close is not a positive finite price; `VKP` has one `0.0`), or `post_halt_resumption` (trading resumed after a gap longer than 30 calendar days, so the daily limit does not apply across it — soft only). Task 9.1 must count these apart rather than as one total |
| `log_return` | REAL NOT NULL | The measured session-over-session `ln(close / prev close)` that triggered the flag. May be `±inf` where a close is `0.0`. For `flag_reason = 'invalid_close'` with no computable return at all (the first stored session, or one after another invalid close) this is `0.0`, which means "no return could be computed" and **not** "the price did not move" — `flag_reason` is what carries the meaning there |
| `limit_exchange` | TEXT | Exchange whose daily price limit was applied; null for the hard tier, which uses the widest limit and needs no exchange |
| `limit_is_unverified_fallback` | INTEGER NOT NULL | `1` when the applied limit came from current-state exchange rather than verified dated membership |
| `flagged_at` | TEXT NOT NULL | ISO timestamp of the gate run that wrote this row |

Indexed on `flag_tier` (`idx_ohlcv_quality_flags_tier`), since the common
query is "all hard-flagged rows" when excluding them from feature and
volatility computation.

## Quirks and caveats

### Time-of-day quirk

vnstock returns each row's timestamp with a constant `07:00:00` time-of-day
component. This is stripped at ingestion time (`df["time"].dt.date`), not at
read time, so every downstream consumer (feature engineering, training, UI)
works with plain `YYYY-MM-DD` dates and never needs to know about or
re-strip this quirk itself.

### `available_since` ambiguity

`available_since` is computed as `min(date)` from whatever the load actually
returned. It does not distinguish between two different reasons a ticker's
history might start where it does:

- The ticker's **true listing date** (it genuinely didn't trade before this).
- The **community-tier ~8-year cap** cutting off earlier history that does
  exist, just not accessible via this data source's free tier.

This is not resolvable from a single API call, and is not resolved by this
change. Cross-reference `possibly_truncated_by_tier` as a hint, and treat
`available_since` alone as ambiguous until confirmed by an outside source
(e.g. the exchange's own listing records) or a future paid-tier data source.

### `possibly_truncated_by_tier` calibration caveat

Computed as:

```
possibly_truncated_by_tier = abs(available_since - (end - 8y)) <= 30 days
```

The 30-day tolerance was calibrated against observed truncation jitter on
**two manually-checked tickers** (VIB, TCB), not against the true population
distribution of listing dates. Consequence: this heuristic skews toward
**over-flagging** — it's more likely to mark a genuinely young ticker as
tier-truncated than to miss a real truncation.

This flag is a label only. It never gates, blocks, or filters any row from
being written to `ohlcv` — a wrong flag costs nothing at write time. Treat it
as a hint to check manually, not as ground truth, until recalibrated on a
larger sample.

### Count-truncates-from-end fetch behavior

The fetch call is:

```python
mkt.equity(ticker).ohlcv(start="2000-01-01", end=today, count=5000, source="vci")
```

`count` truncates the result **from `end` backward**, not from `start`
forward. In other words, raising `count` extends how far back the returned
history reaches; it does not skip more recent rows. This is why `count` is
always passed as an explicit, large value (5000) — omitting it was observed
to silently default to ~100 rows, a silent data-loss failure mode with no
error raised.

Separately, the community tier caps daily OHLCV at
`floor = max(end - 8y, ticker_real_start)`, confirmed on both `kbs` and `vci`
sources. A fixed `start="2000-01-01"` and a computed `start=today-8y` are
behaviorally equivalent under this cap (confirmed on VIB, `vci`) — the fixed
constant is used to avoid an unnecessary date-math dependency.

See [`backend/scripts/verify_vnstock_tier_limit.py`](../backend/scripts/verify_vnstock_tier_limit.py)
for the reproducible checks behind these findings, and the project's vnstock
skill for general library usage. A known, unresolved failure mode (an
unexplained `ValueError` on the second hop of a multi-call walk-back past the
tier limit) is deliberately reproduced but not fixed there — do not build
walk-back/chunking logic on top of this fetch without root-causing that
first.

### Dated exchange membership is not available

`ticker_universe.exchange` is **current state**, not history. Symbols migrate
between exchanges — verified in this repo's own data, `ACB` and `VND` moved
HNX -> HOSE and `VIB` moved UPCOM -> HOSE around 2020-21 — and their
pre-migration rows legally exceed HOSE's price limit. The listing API returns
only current exchange, and delisted rows carry no exchange field at all, so
dated membership cannot be reconstructed from the data source.

Rather than silently asserting current exchange as historical fact,
`exchange_is_unverified_fallback` records that the value is a fallback.
The soft flag tier is evaluated against it and marks its own rows the same
way (`ohlcv_quality_flags.limit_is_unverified_fallback`); the hard tier does
not depend on exchange at all, which is why the hard tier is what actually
gates data. Design Decision 2 and Decision 3.

### Stale-close fraction scope

`stale_close_fraction` is computed over the symbol's **full stored history**,
per the `ohlcv-quality-gate` requirement. The definition
(`(close == close.shift(1)).mean()`) is carried over from
`backend/scripts/screen_ticker_volatility.py`, but that script computes it
over its trailing `VOL_WINDOW = 250` sessions only. The two numbers will
therefore differ for a symbol whose liquidity changed over its life; this
table's value is the full-history one.

The comparison is exact float equality on `close`, and the first row of a
series compares against NaN and so counts as not-stale — both inherited from
the script's definition unchanged.

### Hard implies soft in `flag_tier`

The hard threshold (the widest VN exchange limit, UPCOM's ±15%, plus
tolerance) is strictly wider than every soft threshold (the symbol's own
exchange limit: HOSE ±7%, HNX ±10%, UPCOM ±15%). A row past the hard
threshold is therefore necessarily past its soft threshold too. Since the
primary key allows one row per `(ticker, date)`, `flag_tier` records the
**highest** tier reached: `hard` implies both, `soft` means soft only.

Consequence when counting: "rows flagged at all" is every row in the table,
"rows excluded from modelling" is `flag_tier = 'hard'`, and "rows flagged for
review but retained" is `flag_tier = 'soft'`. Do not read
`COUNT(flag_tier = 'soft')` as "all rows exceeding a soft limit".
