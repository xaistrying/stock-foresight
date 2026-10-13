## Why

The owner has narrowed the product to a **weekly risk-and-awareness check on the stocks they hold**, with no tool-made direction call (`docs/DISCUSSION_purpose_and_weekly_brief.md`, decisions 1 to 3; Rules 4 to 6 were rewritten for it by the archived `align-rules-with-weekly-brief`). No code produces that brief yet: today the output is a per-ticker debate report built for a different purpose, and nothing refreshes prices first, converts the band to VND on a position, remembers what range was issued last week, or checks the investor's own levels. The brief is the smallest thing that can be used weekly for four weeks, and those four weeks of real briefs are the evidence the cleanup changes (C1, C2) wait for.

## What Changes

Domain-rule honoring (config rule for proposals):

- **Rule 1** honored: ranges are 5 TRADING SESSIONS ahead. With no trading calendar in the repo, every date is anchored on the last stored bar ("the 5 sessions after <date>"), never "Monday to Friday". "The week just ended" is the last 5 stored sessions. Inside/outside is scored on `|ln(close[t+5] / close[t])|`, the same measure the band is fitted to.
- **Rule 2** honored: raw log values are never printed; the brief prints simple percentages and VND prices.
- **Rule 3** honored: no fixed price-move threshold is introduced. Levels are the investor's own prices; the tool reports a distance, not a trigger it chose. The only fixed numbers are non-price (calendar-day staleness, a rounding tolerance on a stored close).
- **Rule 4** honored: the only reliability figure is the model's nominal coverage, printed through `coverage_phrase` and never typed; the fixed sentence "It does not predict direction." is in every brief; nothing is called Confidence; for an `uncalibrated` ticker the band is shown with no coverage sentence.
- **Rule 5** honored: the investor's levels are printed verbatim, labelled as theirs with the entry date; no language-model text exists in the brief.
- **Rule 6** honored, no text change: the tool's own words on a level are reached / not reached and the distance; no buy, sell or hold label; the short brief disclaimer from `docs/DISCLAIMER.md` ("Brief version") is shown on every brief. No rule text in `CLAUDE.md` or `openspec/config.yaml` is edited and no existing spec is amended.

What the change adds:

- **A script and a package**: `backend/scripts/weekly_brief.py` (thin) over `backend/app/services/brief/` (small modules; sections are pure functions that return lines, so later changes add sections without rewriting these). Mirrors `snapshot_company_feed.py`. Started by hand, after the market close. Calls no language model.
- **Holdings file outside the repo**: TOML, read with `tomllib`, default under the user's config directory (directory mode 700, file mode 600). The script **refuses** a file that is group- or world-readable, not owned by the user, or inside the repository. Narrow `.gitignore` patterns (`holdings*.toml`, `holdings*.jsonl`, `holdings*.json`) are added as a backstop. Holdings are never stored in `app.db` or any database and never pass through the API.
- **Issued-brief log**: a JSONL file beside the holdings file, appended once per holding per run with the issued close, band percent, band VND low/high, last-bar date, model version and the levels as checked. It is not under `reports/`. It is what makes "last week's range held / did not" answerable.
- **Refresh before compute**: each held ticker goes through `load_ticker`, wrapped to survive vnai's limiter (a `SystemExit` recognised by the existing `_is_rate_limit_exit`); a failed refresh degrades to "refresh failed; last bar <date>" with a per-holding stale warning.
- **A loud header**: when the run is during the session, a provisional-bar warning is the first line after the title and the close is marked "(provisional)" in the position line (the run still happens); and a counts-only line "Re-read triggers this run: your levels reached: <n>." near the top, present even at 0, with no judgement words (N3 extends the same line).
- **The brief** (v5.3 minus the parts owned by later changes): header, HOLDINGS LISTED with its upper-bound sentence (two or more holdings), a position block, THE WEEK JUST ENDED, NEXT 5 TRADING DAYS in VND per share and on the shares, YOUR LEVELS, footer limited to the investor's levels, and the short brief disclaimer. Plain wording is defined for **every** non-ok range status, so no holding silently vanishes.
- **A best-effort detector for re-adjusted prices**: when the stored close for the last issued bar differs from the close that was issued, the brief warns that levels set earlier may be on the old price basis, and states the detector's limit.
- **`--redact`**: same brief with everything derived from holdings removed (tickers kept), so the three helper agents can be pointed at it.
- **Guards**: a new buy/sell/hold guard over the brief's own text (the investor's verbatim rule block stripped first); an import scan proving no language-model client is loaded; a brief-disclaimer guard that ties the copy to `docs/DISCLAIMER.md` and to the model's coverage; tests that holdings never enter the repo, a database or the API, and that the file permission refusal works. Tests use injected paths and temporary databases and never touch the real `backend/data/app.db`.
- **Last task**: re-read `.claude/agents/brief-explainer.md`, `brief-auditor.md` and `reader-sim.md` against the real format and fix what differs.

**Not in this change** (each is owned by a later change or deferred; see `design.md` for the ordering): dividends, ex-dates, share issues, the net line and the week-1 recompute fallback (N2a, N2b); announcements, type tags, insider sizing and the company block (N3); foreign flow; any verdict or model text; Fibonacci; 52-week levels; yield; tax and fees; the scoreboard; any frontend. The optional "biggest weekly fall or rise" line stays off. The existing `TRANSACTION_VERBS` guard in `test_debate_export_api.py` is **not narrowed** here: its only user is the debate export test, which never sees the brief, and it goes away with the debate retirement (C1).

## Capabilities

### New Capabilities
- `weekly-holdings-brief`: the weekly brief, its holdings file and permission rules, the issued-brief log, refresh behaviour, the wording for every range status, the redacted copy, and the guards over its text and imports.

### Modified Capabilities
<!-- none. domain-rules and volatility-range are used as they are: compute_range, coverage_phrase and docs/DISCLAIMER.md are read, not changed. The company-feed spec and its isolation test are untouched; the brief package must not mention the feed (N2a amends that). -->

## Impact

- **New files**: `backend/app/services/brief/*.py`, `backend/scripts/weekly_brief.py`, `backend/tests/test_brief_*.py`. **Edited**: `.gitignore` (one line). Nothing else in `app/`, no route, no migration, no frontend, no `docs/` edit.
- **Reads**: `backend/data/app.db` through `compute_range`, `read_recent_closes` and `load_ticker` (refresh writes OHLCV rows, as every manual refresh does); `backend/data/models/har_rv_model.json` through `load_model`. **Writes outside the repo**: the issued-brief log (mode 600). The vendor is called once per held ticker per run; vnai's analytics will see the held tickers on those calls (accepted by the owner's own refresh habit; noted, not mitigated).
- **Dependencies and ordering**: depends on `align-rules-with-weekly-brief` (archived, done). **N2a** (`add-dividend-and-ex-date-lines`) and **N3** (`add-announcement-tags-and-insider-sizing`) build on this change's section functions, issued-brief log and holdings fields, so N1 applies first; N2a is also where the company-feed spec and isolation test are amended. N2b waits on the 4-week check. **E1** (`evaluate-band-against-trailing-stdev`) is independent and can run in parallel.
- **Personal-use premise**: confirmed by the owner on 2026-10-12 (this project is used by the owner themself, not commercially); recorded in `design.md` as the owner's statement, not verified by the tool, and Rule 6 is unchanged. Holdings are still personal financial data, the vendor licence is personal and non-commercial, and the company-feed log is marked "not to be shared": if anyone else will receive a brief, Rule 6 requires restoring the old rule or obtaining sign-off first. This is a flag, not legal advice.

## Exit gate (kill criteria, carried from the review)

This change is judged after **4 weeks of real use**, and this gate decides whether C1 and C2 proceed:

1. **Stop or rethink** if the owner cannot name one week where the brief showed something the broker app and its notices did not, **or** opened it unprompted in fewer than 3 of the 4 weeks.
2. **Stop or rethink** if, over the modelled tickers, the band is no better than a constant ±2.5% range or a trailing 20-day-standard-deviation band. E1 tests this and is independent of this change.

Meeting the gate is the owner's judgement, recorded in `docs/DISCUSSION_purpose_and_weekly_brief.md`; no code in this change enforces it. The brief log starts the clock: week 1 is the first line in the issued-brief log.
