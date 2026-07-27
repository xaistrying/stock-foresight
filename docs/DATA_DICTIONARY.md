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
