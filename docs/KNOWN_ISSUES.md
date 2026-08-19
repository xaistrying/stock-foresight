# Known Issues / Backlog

Real, confirmed issues not yet scheduled into a milestone. Not a wishlist —
only add an item here once it's actually been reproduced, the same standard
M2/M3's design docs hold every other claim to.

---

## `_wilder_smooth` crashes on short OHLCV series

**Found**: M3, task 8.1, while running `pytest backend/tests`.

**Symptom**: `_wilder_smooth` in `backend/app/ml/feature_engineering.py`
raised `IndexError: iloc cannot enlarge its target object` when computing
RSI/ATR against a series shorter than the warm-up period (~15 rows for
period=14). Caught by `recompute_features_for_ticker`'s existing error
handling ("Feature recomputation failed for `<ticker>`") — didn't crash
the caller, but the ticker's `features` rows silently ended up empty.

**Likely trigger in practice**: a newly-listed ticker loaded with very
little trading history — plausible once M5's ticker panel lets users load
arbitrary tickers, including recent IPOs.

**Fix applied**: `_wilder_smooth` now guards `len(values) < period` and
returns an all-NaN `Float64` series (matching length/index) instead of
raising. This is option 1 of the three originally laid out below (null
just the affected column, row stays otherwise intact) — chosen because it
matches the module's existing `near_gap` philosophy: a too-short row is
unreliable regardless and already flagged as such, so a missing indicator
value is consistent with how the rest of the pipeline already treats it.

**Process note**: this was fixed and regression-tested inline, not via the
`/opsx:propose fix-short-series-feature-computation` route this entry
originally called for. The three-way trade-off (null column vs. refuse row
vs. minimum-row threshold) was real, but got resolved ad hoc mid-session
rather than through a formal design decision — worth knowing if the choice
ever needs revisiting, since it wasn't vetted the way M2/M3's other design
decisions were.

**Regression tests**: `test_wilder_smooth_returns_nan_series_when_too_short`
and `test_wilder_smooth_seed_at_exact_boundary_still_works` in
`backend/tests/test_feature_engineering.py`.

**Status**: fixed, closed.

---

## `vnstock` auto-writes prompt-injection content into AI-tool config files

**Found**: M3, while investigating why `backend/AGENTS.md` kept reappearing
after every `pytest backend/tests` run.

**Symptom**: `vnstock/__init__.py` (installed package, not this repo's code)
has an unconditional module-level call, `setup_agent(async_mode=True)`, that
fires on every `import vnstock` — including transitively, any time backend
code or tests import `app.services.ticker_ingestion` /
`app.ml.feature_engineering`. This calls into `vnai` (a mandatory dependency
of `vnstock`, pulled in automatically), which writes a file called
"Vnstock Vibe Onboarding" into:

- this project's `AGENTS.md` (both `backend/AGENTS.md` and repo-root
  `AGENTS.md` were seen)
- **six global, cross-project AI-tool config paths in the user's home
  directory**: `~/.clauderc`, `~/.cursorrules`, `~/.windsurfrules`,
  `~/.clinerules`, `~/.github/copilot-instructions.md`,
  `~/.gemini/config/AGENTS.md` — created from scratch if missing, or
  **appended to** if a file already exists there (confirmed via reading
  `vnai/beam/agents.py`'s `setup_agent_environment`).

The written content is addressed directly to AI coding assistants (not
human readers) and instructs them to: silently capture and persist an API
key typed into a prompt (to `~/.vnstock/api_key.json` or via
`setup_api_key(...)`), auto-install packages and create a shared
`~/.venv` without asking, and run agent-generated scripts without
confirmation. Separately, `vnstock/__init__.py`'s own module docstring
contains text aimed at AI assistants urging an unconditional switch to a
paid `vnstock_data` package and invoking an unreviewed
`migrate_to_sponsor()` function against the project root. Some `vnai` code
paths (`vnai/beam/agents.py`) also fetch "skill" content live from
`vnstocks.com/api/skills/...`, base64+XOR-obfuscated, gated on an API key —
so delivered content isn't fixed at install time.

**Confirmed real, not a one-off**: reproduced live — deleting
`backend/AGENTS.md`, then re-running `pytest backend/tests`, causes it to
reappear with a fresh timestamp, byte-identical to the original.

**Fix applied (local only)**: commented out the `setup_agent(async_mode=True)`
call at the bottom of the installed
`backend/.venv/lib/python3.14/site-packages/vnstock/__init__.py`. The
`setup_agent()` function itself is left intact (still callable explicitly);
only the automatic self-invocation on import is disabled. Verified: full
test suite still passes (34/34) and none of the six home-directory files
or either `AGENTS.md` regenerate after the patch.

**Important limitation**: this patch lives inside `.venv`, which is
gitignored and not shared between environments. It will be **silently
lost** the next time `backend/requirements.txt` is reinstalled into a
fresh virtualenv, or if `vnstock` is upgraded/reinstalled — nothing in the
repo currently reapplies it automatically. Whoever rebuilds the venv next
needs to either reapply this patch manually or land a durable fix (a
`sitecustomize.py`/post-install hook, a vendored/patched fork, or pinning
to a pre-`vnai` `vnstock` release if one exists).

**Also removed this session** (already-injected files found across the
machine, not just this project): the six home-directory config files
above (all were pure `vnai`-generated content, 3160 bytes, nothing of the
user's own — safe to delete outright), plus both `AGENTS.md` copies in
this repo. Left untouched, deliberately: `~/.agents/skills/hallmark/`
(a real Claude Code skill), `~/AetherForecast/.agents/rules/` (a
different project's own real rules), and `~/vnstock-agent-guide/` (the
actual upstream repo this injection content originated from — legitimate
there).

**Status**: mitigated locally (this `.venv` only), not durably fixed.
Needs a decision: patch-on-install script, vendored fork, version pin, or
report upstream to the `vnstock`/`vnai` maintainers.

## Uncaught `tenacity.RetryError` for a well-formed ticker with no real data

**Found**: while designing M5's ticker-panel error states, testing
`load_ticker`'s exception handling.

**Symptom**: a well-formed ticker symbol (3-12 characters, passes vnstock's
format validation) that corresponds to no real data raised
`tenacity.RetryError`, not `ValueError` — `load_ticker`'s
`except ValueError` didn't see it, and the request crashed unhandled.

**Confirmed live**: `mkt.equity("ZZZ").ohlcv(...)` raises
`tenacity.RetryError`; `e.last_attempt.exception()` returns the real
underlying `ValueError("Không tìm thấy dữ liệu. Vui lòng kiểm tra lại mã
chứng khoán hoặc thời gian truy xuất.")`. Confirmed separately that a
malformed-symbol `ValueError` (the `invalid_symbol` case) is *not*
wrapped in `RetryError` — it still surfaces as a plain `ValueError`, so
the two cases remain distinguishable after unwrapping.

**Fix applied**: `load_ticker` now catches `(ValueError, RetryError)`
together; when the caught exception is `RetryError`, it unwraps via
`e.last_attempt.exception()` before passing to `_classify_load_error`,
otherwise it passes the exception through directly. `_classify_load_error`
gained a third match, `"Không tìm thấy dữ liệu"` → `status: "no_data"`,
alongside the existing `invalid_symbol` matches.

**Status**: fixed, closed, and now covered by a test —
`test_well_formed_ticker_with_no_data_reports_status_no_data` in
`backend/tests/test_ticker_ingestion.py`. (This entry previously said
"not yet covered"; that's no longer accurate as of this check.)
