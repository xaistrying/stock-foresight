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
| `target` | REAL | horizon 5 sessions | n/a (looks forward, not back) | Rule 1: `ln(close[t+5] / close[t])`, 5 TRADING SESSIONS ahead (row offset, not calendar days); `NULL` for a ticker's last 5 stored sessions (insufficient future data) — the row is still written with feature columns populated |
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

#### `computed_at` staleness caveat

`computed_at` records **when** a row was computed, not **what indicator
parameters** produced it — it is not a parameter-version column. If
indicator periods/definitions change later, rows whose `computed_at`
predates that change are the ones that are stale relative to the new
definition, assuming a reload triggers Decision 5's full per-ticker
recompute. See design Decision 8.

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
