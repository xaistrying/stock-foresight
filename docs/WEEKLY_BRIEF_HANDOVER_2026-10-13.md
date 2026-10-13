# Weekly holdings brief: what was built, what was learned, what is still open (handover, 2026-10-13)

Written for the owner and for a later session that has none of this conversation. It consolidates
`docs/DISCUSSION_purpose_and_weekly_brief.md` (1,900+ lines, the full record) into one readable place, plus
everything done after it. Where the two disagree, this file is newer; the discussion doc keeps the evidence.

**Evidence labels used throughout.** *Measured*: a read-only query or a run on this machine's data.
*Simulated*: an AI model role-playing an investor or labelling titles; the same model family wrote the briefs, so it
finds reading errors and plausible reasoning, not real behaviour. *Inferred*: reasoned from code or documentation, not
tested. *Unverified*: stated so that nobody mistakes it for a fact.

---

## 1. Where things stand

- **Closed on 2026-10-13:** the weekly brief is built, reviewed and tested (full backend suite: 2,873 passed, 10
  skipped). Of four OpenSpec changes, three are fully applied and one is archived. **One task is deferred**: N3 task
  5.2, the first real run on the owner's own holdings.
- **Why 5.2 is deferred and the method is paused.** The way the brief gets your holdings today (a TOML file kept
  outside the repository, then a command run by hand) is correct for privacy but is heavy for a weekly habit. The
  owner asked to stop here and explore a holdings entry experience (a small database plus a UI panel) later. Section 9
  records that idea, its risks and the decisions it needs. Nothing for it is built.
- **The 4-week check has not started.** It starts at the first real run, which has not happened. No real holdings file
  exists. Nothing in this repository has been tested against a real investor.
- **Nothing was committed by the assistant.** HEAD is `c39fe93` (a commit made during the session by the owner).
  67 paths are uncommitted: 9 modified files and 58 new ones (the brief package, tests, scripts, three change folders,
  one synced spec).

## 2. What the product is (and is not)

**Purpose (decided 2026-10-11):** a *risk and awareness monitor* for the few stocks the owner holds, read about once a
week: how big a normal week is for each holding, what is scheduled, what changed, scored over time. It gives **no
buy, hold or sell verdict and no direction claim**. It replaced two earlier identities: a direction predictor (retired,
correlation about 0.01) and a three-agent debate verdict (being dismantled).

**The six non-negotiable domain rules** (`CLAUDE.md`, mirrored in `openspec/config.yaml`; never changed by this work):
1. Horizon is 5 *trading sessions*, scored against `ln(close[t+5] / close[t])`.
2. Never show a raw log return; show simple percentages.
3. Magnitude thresholds are volatility-relative.
4. Reliability is measured, never asserted; no figure is called Confidence; the band states its nominal coverage.
5. Label by provenance; mark language-model text; mark what the investor wrote and when.
6. Personal, non-commercial use; technical observation only; the tool never produces its own buy, sell or hold label;
   the investor's own rule text is shown verbatim and labelled as theirs; the tool's words about a level are limited to
   reached or not reached and the distance.

**What the brief prints, per run** (script `backend/scripts/weekly_brief.py`, after the market close):

```
title line (newest last bar; "the 5 sessions after <date>")
[WARNING: today's bar is provisional]         <- only during a session
Re-read triggers this run: your levels reached: n; ...     <- counts only, full copy only
Prices refreshed ... / units line / "does not predict direction"
--- TICKER · shares · cost · bought ---       <- full copy; "--- TICKER ---" only in the redacted copy
Close, value, gain/loss on price
THE WEEK JUST ENDED   move, last week's issued range and whether it held (or the week-1 recompute)
NEXT 5 TRADING DAYS   usual range in VND per share, "about 2 weeks in 3 stay inside"
DIVIDENDS             per-share cash dividends, share issues, when the feed was last fetched
COMPANY               needs a look / for information / scheduled; registered trades with size and benchmark
YOUR LEVELS           the investor's own words, checked against the close
footer + short disclaimer
```

It deliberately omits: verdicts, Agreement, model-written text, macro sentences, 52-week levels, yield, tax and fees,
a dividend-inclusive total (deferred, change N2b), foreign flow (deferred), a scoreboard, any frontend.

## 3. Decisions the owner made (consolidated)

| Date | Decision |
|---|---|
| 10-11 | Purpose = risk and awareness monitor; weekly use; retire Agreement and the vote; Fibonacci out of the headline; Rule 6 relaxed for personal use only. |
| 10-11/12 | Rules 4, 5 and 6 rewritten (`align-rules-with-weekly-brief`, archived); brief disclaimer added to `docs/DISCLAIMER.md` ("Brief version"). |
| 10-12 | Foreign-flow snapshots deferred. N2 split into N2a (built) and N2b (gated on the 4-week check). C1 and C2 (retire the debate engine, archive experiments) wait for the same check. |
| 10-12 | Holdings in a TOML file *outside* the repo; issued-brief log beside it; never in a database or through the API. **(Paused by the 10-13 idea in section 9.)** |
| 10-12 | The redacted copy keeps tickers and drops everything derived from holdings. |
| 10-12 | Personal use confirmed: the tool is used by the owner only, not commercially. |
| 10-12 | Defaults accepted for: narrow ignore patterns, VND range edges `close x exp(-/+ band/100)`, a provisional-bar warning at the top, a counts-only "Re-read triggers" line (whole-word banned list, 14 words), the level note on its own line, UNCLEAR threshold at 2 daily sigmas, "N older announcements no longer shown", "filed a notice of a sale of ..." wording (no buy/sell word, so no Rule 6 exemption), sizing on by default, 30-day settling window and 1% materiality, E1 margin 0.02. |
| 10-13 | Keyword classes capital, meeting and personnel enabled after a labelled check (labels written by an AI model at the owner's request). |

Five simulated readers (P1 to P5, one each) informed the investor-facing wording defaults. That is *simulated* input.

## 4. What was built

Four OpenSpec changes, all under `openspec/changes/` (E1 archived under `openspec/changes/archive/`).

| Change | Status | What it holds |
|---|---|---|
| `add-weekly-holdings-brief` (N1) | 42 of 42 tasks | The core: holdings loader, refresh, range, week-just-ended, levels, issued log, redaction, fixed sentences, runtime Rule 6 scan. |
| `add-dividend-and-ex-date-lines` (N2a) | 35 of 35 | The one feed adapter, dividends, share issues, ex-date window, adjustment-status check, combined week line, older-announcements line, week-1 recompute. |
| `add-announcement-tags-and-insider-sizing` (N3) | **29 of 30** (5.2 deferred) | COMPANY block, announcement tags, registered-trade lines, sizing against shares outstanding, benchmark, small-issue summary, triggers-line extension, sanitiser for third-party text. |
| `evaluate-band-against-trailing-stdev` (E1) | archived 10-13, 25 of 25 | A read-only, pre-registered study of the served band against simpler bands; spec synced as `band-baseline-comparison`. |

**Code** (about 4,700 lines in 33 modules under `backend/app/services/brief/`, plus `share_count/fetch.py`):
`holdings.py` (TOML loader, permission and path refusals), `issued_log.py`, `run.py`, `compose.py` (sections, trigger
counters, the runtime Rule 6 scan), `facts.py`, `week.py`, `week_move.py`, `levels.py`, `adjustment_status.py`,
`dividend_lines*.py`, `corporate_actions.py`, `feed_source.py` (the *only* file that may mention the company feed),
`announcements.py`, `announcement_keywords.py`, `third_party_text.py`, `insider.py`, `sizing.py`, `share_cache.py`,
`company_*.py`, `sections_*.py`, `wording*.py` (every fixed sentence, scanned by tests).
**Scripts:** `weekly_brief.py`, `evaluate_band_against_trailing_stdev.py`, `verify_announcement_classes.py`,
`brief_audit_query.py` (a read-only SELECT tool for the auditor agent; 20 tests).
**Tests:** 41 `test_brief_*.py` files plus four more; golden files for the briefs under `backend/tests/brief_golden/`.
Line coverage of the brief package about 96% (measured with a trace script; `pytest-cov` is not installed).
**Agents** (`.claude/agents/`): `brief-explainer`, `brief-auditor` (now without a raw `sqlite3` shell), `reader-sim`
(development only; its output is never evidence).
**Housekeeping done:** the `domain-rules` spec Purpose line, the stale Rule 6 docstring in `prompt_safety.py`, the
`band-baseline-comparison` Purpose line, `docs/DATA_DICTIONARY.md` and `docs/MODEL_CARD.md` updates.

**Outside the repository** (`~/stock-foresight-probes/`, not tracked): probe and snapshot scripts for the vendor
(`probe_ratio_summary.py`, `adjustment_lag.py`, `lag_retro.py`), their outputs, and `labels/` (the title sample, the
labels file and its provenance note, all mode 600). The company feed log (`backend/data/company_feed_log.db`) now holds
10 tickers (SAB, VPB, VIB, FPT, VNM, HPG, MWG, VCB, KBC, SSI); it is gitignored.

## 5. How it fits together, and the privacy model

```
holdings.toml (outside repo, 0600) ─┐
                                    ▼
refresh each ticker (load_ticker; survives the vnai limiter exit) ─▶ compute_range (existing HAR-RV band)
                                    │                                  │
company_feed_log.db ─(one adapter, read-only)─▶ facts ─▶ sections ─▶ compose ─▶ runtime Rule 6 scan ─▶ stdout / --out
share-count (vendor, optional) ─────┘                                                  │
issued-brief log (JSONL beside the holdings file, market figures only) ◀───────────────┘ (after the brief is written)
```

Guards that exist and are tested: the holdings file is refused if group/world readable, owned by another user, inside
the repo, or on a Windows drive; the log opens without following symlinks; no language-model client is imported; the
company feed text appears in exactly one file; every fixed sentence and the whole rendered brief pass a buy/sell/hold
scan (the investor's own level text is exempt by *position*, after a review found a substring bypass); third-party text
goes through one sanitiser and appears only in quotes; the **redacted copy** (made to hand to a helper agent) shows no
shares, cost, levels, weights, values, log-derived week text, announcement titles or counterparty names, and a leakage
test proves no holdings-derived number survives. The issued log stores no levels.

## 6. What was measured (evidence)

- **The band is volatility clustering, not magic.** Study E1 (*measured*, run once, pre-registered, 208 symbols, test
  years 2020 to 2026, 334,341 out-of-time windows): against a trailing 20-session band the HAR band is `NOT_BETTER`
  (relative gain +0.6%, 97.5% interval -0.4% to +1.7%: neither shown better nor worse; the pre-registered 2% margin is
  ruled out); against a fitted constant band it is `HAR_BETTER` (+9.0%, +7.0% to +11.1%, positive in 7 of 7 years).
  Pooled coverage: HAR 67.6%, trailing 67.9%, constant 66.1%. Consequence, pre-agreed: a follow-up *may* swap in the
  simpler trailing band; it does not stop the brief. Not proposed yet.
- **Recomputing last week's band is safe for the percentage, not for prices** (*measured*): 5 of 6 issued bands in
  `debate_log` equal the recompute to two decimals (the sixth differed because the issued run used a provisional
  close). A later ex-date rescales earlier closes by a constant, which leaves the band percentage unchanged but shifts
  VND levels: SAB's 2026-07-28 ex-date (3,000 VND) gives a board move of -7.65% against -1.30% excluding the dividend.
  Hence the combined week line and the adjustment-status check.
- **The vendor adjusts history quickly, but the lag has no lower bound** (*measured*): MWG's 1,000 VND dividend (ex
  2026-10-07) was already applied by 10-12 (at most 3 sessions); stock factor is exactly `1/(1+ratio)`, cash factor
  `(P-D)/P`. Over 59 stored events the status check gave 36 ADJUSTED, 20 UNCLEAR, 0 NOT_YET_ADJUSTED, 3 with no stored bar.
- **Announcement-to-ex-date lag** (*measured*, 44 cash dividends, 9 tickers): maximum 85 days (SAB), all other tickers
  21 days or fewer; the 120-day `MAX_LAG_DAYS` margin stands.
- **Share issues** (*measured*, 40 stored `ISS` rows): bonus 10, stock dividend 8, private placement 8, employee 13,
  rights offer 1. Only a bonus or stock dividend with an ex-date and a ratio above 0 changes a holder's share count. An
  earlier rule (any `ISS` with an ex-date) was wrong and was replaced.
- **Vendor share count** (*measured*): `Company(source="vci", symbol=S).ratio_summary()` returns `year_report`,
  `quarter`, `number_of_shares_mkt_cap`, `ratio_type` (RATIO_TTM, plus RATIO_YEAR rows with quarter 5: filter them
  out). The latest quarterly row is *live*, not "as of the quarter". `overview()` has four duplicate `issue_share`
  columns; during VPB's stock dividend they disagreed with `ratio_summary()`, which is why disagreement withholds a size.
- **Registered insider trades** (*measured*, 341 stored rows): direction readable in all; a quantity is stated in 247
  (94 absent); **76% are published after their window has ended**, so "planned, not yet executed" would usually be
  false; the brief uses three window states (not started, under way, ended).
- **Keyword classes** (*simulated* labels, claimed titles only): capital 38/38 correct, meeting 28/28, personnel 7/7
  (enabled); dividend 21/23 and results 21/30 (stay disabled). Recall is unmeasured: 329 filings match no class.
- **Simulated readers** across five rounds (about 100 readers): the verdict caused worry and was never a decision
  driver; a calendar fact (ex-date) changed an action; pre-written rules were followed 5 of 5 in the clean cases. All
  *simulated*; same-model caricatures; the project's own rule says they are not evidence.

## 7. Reviews that ran, and what they changed

Two read-only reviews ran on N1 and one on N2a/N3 before the next change was built.
- **N1 code review** blocked on one bug: a second run on the same bar read the first run's own log entry, silently
  dropping the re-adjusted-price warning in exactly the documented "real run, then redacted copy" workflow. Fixed with a
  test that re-runs on the same bar.
- **N1 security review:** the issued log's privacy promises were not enforced (mode only set on creation, symlinks
  followed, path unchecked), a pre-existing log could stay world-readable, one `U+2028` in a level text could disable
  the log, stdout could carry vendor promo text, and `--out` could truncate the holdings file. All fixed; the log no
  longer stores levels at all (nothing read them).
- **N3 security review:** a one-character level text (for example "l") hid "sell" from the Rule 6 scan under the
  earlier substring removal; invisible Unicode and look-alike quotes passed the sanitiser; the redacted copy would
  have carried third-party names (visible instructions) to a language model; a non-limiter `SystemExit` from the
  vendor call could kill the brief; the redacted size line leaked one bit about the issued log. All fixed.
- **Agent tool risk:** `brief-auditor` had `Bash(sqlite3:*)`, and the `sqlite3` CLI can read any file with
  `readfile()`. Replaced by `brief_audit_query.py` (three fixed databases, read-only, one SELECT, an authoriser).

## 8. Concerns, ranked

**High (needs an owner decision)**
1. **Real feed text is in git history.** Earlier versions of the discussion doc, already pushed to `origin/main`
   (commit `308aa45`), quoted a stored insider-trade title naming a private individual with a share quantity, and two
   company announcement titles. The working tree now holds placeholders; **history still has the originals.** Whether
   the GitHub repository is public is unchecked (`gh` is not installed). Rewriting history is outward-facing and hard
   to reverse, so it was not done. If it is public, treat the named person's data as personal data and ask your data
   protection or legal contact. Not legal advice. Also older and unchanged: a press headline in
   `docs/DISCUSSION_describe_not_vote_redesign.md` and a real-looking sample row in `backend/tests/company_feed_helpers.py`.
2. **The personal-use premise is the owner's statement, unverified.** Rule 6, the vendor licence (vnstock 4.0.5 is
   "personal, research, non-commercial"), and the "not to be shared" mark on the feed log all rest on it. The session ran
   under organisation-level instructions and the git identity is a personal address; confirm account and machine
   ownership before anyone else receives output or it runs on employer equipment.

**Medium**
3. **`ratio_summary()` terms are unchecked** and sizing is on by default. It is a VCI-only route. The brief already
   names every held ticker to the vendor through the price refresh, so sizing adds little disclosure, and
   `--no-sizing` omits it. vnai analytics (*inferred* from reading the source, never observed) post function arguments
   (the ticker), a machine fingerprint and a commercial-use probability to the vendor.
4. **`brief-auditor` keeps `Read`**, and an agent definition cannot limit it to one path. A Read deny rule for
   `~/.config/stock-foresight/**` in the owner's own settings would close that; it is not set.
5. **Investor level text is printed unquoted** (spec-mandated), ahead of the attribution; text imitating the tool's
   voice is possible but self-inflicted. A reviewer suggested quoting it; undecided.
6. **Heuristics and policy constants resting on little data:** the adjustment-status check (20 of 59 are "unclear", by
   design; a large market move on the ex-day can fool it), the 30-day settling window and the 1% materiality
   threshold (one example), the 15:15 ICT provisional cutoff (from the review, unverified), `MAX_LAG_DAYS` (10
   tickers), the keyword classes (claimed titles only).
7. **Nothing has been validated with a real investor.** The kill criteria after 4 real weeks: (1) the owner cannot name
   one week where the brief showed something the broker app and its notices did not, or opened it unprompted in fewer
   than 3 of 4 weeks; (2) the band is no better than a constant ±2.5% or a trailing band (E1 answered half of this).
   The first real run has not happened, so the clock has not started.
8. **The labels for the keyword classes were written by an AI model**, not the owner; a spot-check of about a dozen
   judgement calls is cheap and outstanding.

**Lower**
9. Unverified: the vendor's adjustment lag has no lower bound (needs a prospective daily watch; the feed holds no future
   ex-dates today); rights-issue behaviour; whether a registration's date is filing or report date; the meaning of
   `DDIND`, `DDINS`, `DDRP` beyond one documented group; the vendor calls have no timeout of their own.
10. Test fixtures use real tickers and a few measured dates and amounts from the vendor feed (no titles). Real tickers
    are public; the numbers come from a personal-use log.
11. The work was written largely by AI agents under review; the code reviews were read-only and by the same model
    family. A human read of the four ignore patterns, the permission checks and the Rule 6 scan is worth an hour.
12. The change set is large and uncommitted (67 paths). `ruff`, `black` and `mypy` are not installed, so style and
    type checks were by hand; a few lines run 120 to 140 characters.

## 9. Deferred: how the owner enters holdings (explore later)

**The pain.** Hand-writing `~/.config/stock-foresight/holdings.toml`, setting modes, then running commands is too
heavy for a weekly habit.

**The idea (owner, 2026-10-13).** Keep holdings in a database that is never pushed, with a place in the UI to note
them. **Assistant's view (not built, not decided):** worth doing, as its own change.
- A separate `holdings.db` (never `app.db`, which is rebuildable and which pytest's lifespan touches), following the
  `company_feed_log.db` precedent (own file, gitignored, own init). Preferably *outside* the repo
  (`~/.local/share/stock-foresight/holdings.db`, mode 600) so agents working in the repo cannot open it; the
  alternative `backend/data/holdings.db` is simpler but readable by anything with the Read tool, and N1's "refuse a
  path inside the repo" rule would need an exception.
- A "Your position" panel beside the selected ticker (shares, cost, purchase date, levels with entry dates).
- The brief core is unchanged: only the loader changes, reusing the same `Holding` validation. The script keeps
  running as a script; a "last brief" view could show its output. A "Run now" button is a later stage because vnai's
  rate limiter calls `sys.exit` and would kill the API server (the reason the feed snapshot is a script).
- **The real cost is the API.** The security review had said holdings should never go through the API. Today: CORS is
  restricted to the two local dev origins (good), there is **no Host-header allowlist** (DNS-rebinding hole), no
  authentication. Mitigations proposed: Host allowlist (`localhost`, `127.0.0.1`), JSON-only requests (forces a
  preflight), CRUD only with no export route, redacted copies still produced only by the script, a single-user WSL
  machine accepted as the trust boundary.
- **Decisions it needs:** DB location (outside the repo recommended); keep the TOML file as a fallback until the UI
  is in use (recommended) or drop it; "Run now" in this change or later (later recommended).
- It would reverse the 2026-10-12 decision "never in a database, never through the API"; record that as a deliberate
  change if taken. Until then the file method works and is documented below.

## 10. If you run the brief now (the deferred task 5.2)

1. Holdings file: copy the hypothetical template from `backend/.venv/bin/python backend/scripts/weekly_brief.py --help`
   to `~/.config/stock-foresight/holdings.toml` (directory mode 700, file mode 600, Linux side of WSL).
2. Give the brief your tickers' announcements, by hand:
   `backend/.venv/bin/python backend/scripts/snapshot_company_feed.py --tickers AAA,BBB --tickers-per-minute 4 --no-rss`
3. After the 15:15 close: `... weekly_brief.py --no-sizing`, then `... weekly_brief.py --no-refresh`.
4. Record in N3's `design.md` counts and states only (holdings count, statuses shown, feed read or never fetched,
   provisional warning, trade sized or fallback), tick 5.2, and the 4-week clock starts. Do it outside any agent
   session; give helper agents only a `--redact --no-refresh --out <path outside the repo>` copy.

## 11. Open items and how to continue

**Owner decisions pending:** rewrite git history or not (and check the repo's visibility); quote the investor's level
text; add a Read deny rule for the holdings directory; the holdings-entry method (section 9); whether to spot-check the
keyword labels; whether to propose the trailing-band swap that E1 allows.

**Tasks pending:** N3 5.2 (first real run); sync the specs and archive N1, then N2a, then N3 (`openspec archive <name>`;
N2a and N3 modify requirements N1 creates, so the order matters; archived specs get a "TBD" Purpose line to replace);
N2b (dividend-inclusive net line, running share count) and C1/C2 (retire the debate engine and experiments) wait for the
4-week check; a prospective lag measurement needs an announced ex-date (`~/stock-foresight-probes/adjustment_lag.py`).

**Commit plan (not done):** separate commits for the brief package and tests, the OpenSpec changes and spec sync, the
agent definitions, and the docs. Run the full suite first (`backend/.venv/bin/python -m pytest backend/tests -q`; the
suite touches the real `app.db` through the TestClient lifespan and the feed log is redirected by `conftest`).

**Starting point for a new session:** read `CLAUDE.md`, this file, then `docs/DISCUSSION_purpose_and_weekly_brief.md`
(section "Status record" and the sections added 2026-10-12 and 2026-10-13); the change folders under
`openspec/changes/` each have a `design.md` with owner decisions and review fixes. Tool notes: the `openspec` CLI is an
nvm node binary not on PATH in non-interactive shells; a Bash hook rejects `.env*` paths and uppercase `$VARS`.
