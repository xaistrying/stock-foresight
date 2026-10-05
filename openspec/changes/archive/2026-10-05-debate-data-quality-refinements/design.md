## Context

`multi-agent-debate-analyst` (archived 2026-10-05) is the baseline. Two real reports (VPB, SAB) were read after it shipped and their figures re-derived from the database and live feeds: every number matched, but three behaviours were wrong or fragile. All three are already fixed in code; this change records them so the main specs match.

Times below are **Vietnam time (UTC+7)**. The dev server runs on UTC+8, so report file timestamps are an hour ahead (the VPB report file reads 15:48 but was generated at 14:48).

## Goals / Non-Goals

**Goals:**
- Make the market-wide foreign-flow vote independent of *when* a debate is run, at least between mid-session and after-close.
- Make the export's split label say what it means.
- Stop look-alike headlines from taking `[sector]` slots (cap: 4) from relevant ones.

**Non-Goals:**
- A true rolling 5–10 session foreign-flow window (needs daily snapshots stored by a post-close job; unchanged from the archived design, Decision 7).
- Finer-than-supersector sector matching (e.g. a beer company's "sector" still includes seafood exporters).
- Changing the ±10% foreign-flow threshold or the 4/2/10 headline slots.
- Measuring whether any stance was *right* (needs the realised 5-session return; see `docs/DISCUSSION_prediction_outcome_tracking.md`).

## Decisions

### Decision 1: the foreign-flow signal votes only after the board has settled (a time rule)

The VCI price board's foreign values are cumulative-so-far during the session and kept moving after it. The same market read, as a share of gross foreign turnover:

| Vietnam time | Net / gross | Share |
|---|---|---|
| 13:35 | −84B / 912B | −9.2% |
| 14:48 | −245B / 1,328B | −18.4% |
| 15:12, 15:16, 15:17, 15:19, 15:20 | −365B / 1,488B | −24.55% (identical) |

At the ±10% threshold, −9.2% votes neutral and −18.4% votes bearish, which flipped VPB's Macro stance (and so its verdict: OBSERVE vs SPLIT) depending on run time.

**Chosen**: the figure is always shown to the LLM, but **counts in the stance vote only when the board has settled**: not before 15:15 on a weekday (09:00 open → 15:15). Before then it is labelled "provisional: session in progress or just closed, not counted in the stance vote"; after, "latest session, final". The clock is read before the fetch (a fetch can take up to 20 s), the clock must be timezone-aware (a naive value would be read in the server's own zone), and the prompts tell the model not to infer a direction from a provisional signal and not to let provisional data move a Round 2 stance.

**Why 15:15**: HOSE matches 09:00–14:45 (ATC last) with put-through to 15:00. The first post-15:00 reading taken was 15:12 and it never changed after; where it settles inside 15:00–15:12 was **not measured**, so the margin runs to 15:15.

**Alternatives considered**
- *Widen the neutral band*: still lets partial data decide the vote; moves the flip point instead of removing it.
- *Minimum gross turnover before voting*: arbitrary, and still time-dependent.
- *Read the board's own trading-status field*: only the closed state could be observed, so the open-state values are unverified.
- *Drop the signal*: loses the one sentiment input that is not price-derived; the figure is useful context even when provisional.

**Threshold note** (design rule): the ±10% share-of-turnover threshold is **new and provisional**, not covered by domain rules 1–6 and not backtested (unchanged from the archived change). The 15:15 settle time is new, for the same reason.

### Decision 2: a three-way split is labelled by its positions, not by a count

`agreement_level == "split"` is exactly the 1-1-1 case for three agents, so there is no group of agreeing agents to count; the export printed `(0 of 3 agents)`, which read as if nobody agreed. It now prints `Split (3 different positions)`, the wording the panel already uses. `majority` and `unanimous` keep `(N of 3 agents)`. New label wording, not a domain rule.

### Decision 3: sector tags prefer phrases and exclude look-alikes

The `[sector]` tag takes up to 4 slots, so noise displaces relevant news (VPB's 4 slots held a Korean-banks cyberattack story and a lender's asset-sale story). Measured on live feeds before/after, VPB's four slots went from 2 relevant + 2 noise to 4 relevant.

**Chosen**
- **Banking keywords**: drop bare `ngân hàng` and `huy động`; use phrases (`tín dụng`, `nợ xấu`, `lãi suất huy động`, `tiền gửi`, `ngành/nhóm/cổ phiếu/các ngân hàng`, `hệ thống ngân hàng`, `ngân hàng thương mại`, `lợi nhuận ngân hàng`, `ldr`, `nim`), **full peer-bank brand names** (Vietcombank, Techcombank, VPBank …) and a "bank … báo lãi/lợi nhuận/lãi quý/tăng vốn/chia cổ tức/phát hành trái phiếu" pattern. Bare short tickers (ACB, VIB, OCB, SHB, MSB) are deliberately **not** brands: they also appear as symbols in stock lists ("PNJ, FPT và MSB …") and mis-tagged one for VPB.
- **Foreign banks** are excluded for banking (country names matched case-sensitively; Britain omitted because `Anh` is also the pronoun *anh*).
- **Non-financial sectors** ignore headlines whose subject is a bank (a lender's asset sale matched food & beverage through `nhà máy nông sản`). Banking, insurance, financial services and real estate keep them. The World Bank, ADB, the State Bank and central banks are exempt (outlooks and policy are not "a bank as subject"; State Bank stories still reach `[market]` through the market keywords).

**Alternatives considered**: keep the bare keywords and let the LLM discard noise (it does, but the slot cap means noise still pushes relevant headlines out); a company-alias table for `[ticker]` (no data source for company names).

## Risks / Trade-offs

- **[Settle time unmeasured between 15:00 and 15:12]** → margin to 15:15; log post-close readings over the next sessions to calibrate (open question).
- **[Exchange holidays are unknown]** → a weekday holiday is treated as settling 09:00–15:15, which only withholds the vote from a final figure; the safe direction.
- **[A mid-session debate has one fewer vote]** → by design and labelled; a mid-session and an after-close run of the same day can differ.
- **[Bank news recall]** → a bank headline with no phrase, brand or earnings word (e.g. "Ngân hàng X mở chi nhánh") is no longer sector news; peer results are the useful case and are covered.
- **[Supersector granularity]** → technology's `công nghệ` and food & beverage's seafood terms still match loosely; not addressed here.

## Open Questions

1. Where exactly does the board settle after the close? (Log timestamped post-close readings; tighten 15:15 if it is earlier.)
2. Do the tagged headlines need company aliases ("VPBank" for VPB) to feed `[ticker]`, or is the brand-name sector match enough?
