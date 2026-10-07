# stock-foresight

Stock Foresight is an analytics dashboard for Vietnamese stocks with a multi-agent debate engine that synthesises technical indicators, news context, and macro signals into a structured analysis verdict.

## Multi-Agent Debate Panel

The debate panel is always shown. Set your LLM provider API key to run it:

```bash
# backend/.env or shell environment
DEBATE_LLM_PROVIDER=openai        # or: anthropic
DEBATE_LLM_MODEL=gpt-4o-mini      # or: claude-3-5-haiku-20241022
OPENAI_API_KEY=sk-...             # if using openai
ANTHROPIC_API_KEY=sk-ant-...      # if using anthropic
```

### No API key: use a Claude subscription (`claude_cli`)

If you have a Claude account but no API key, the backend can run the debate through the `claude` command (Claude Code) instead:

```bash
# backend/.env or shell environment
DEBATE_LLM_PROVIDER=claude_cli
DEBATE_LLM_MODEL=haiku            # optional, default haiku; also: sonnet, opus
DEBATE_LLM_EFFORT=xhigh           # optional reasoning effort: low, medium, high, xhigh, max
```

Requirements and trade-offs:

- `claude` must be on the `PATH` of the process that runs the backend, and logged in (`claude` once, interactively, to sign in).
- Slower than an API call: each call starts a process, and one Analyse took roughly 45-50 s in one measurement (see [Time limits](#time-limits-concurrency-and-the-run-log)). It also counts against your subscription's usage limits.
- `DEBATE_MAX_TOKENS_PER_CALL` and the temperature are not applied.
- `DEBATE_LLM_EFFORT` applies to every agent; unset uses the CLI's default. An unknown value is rejected with an error (the CLI itself would silently ignore it). Measured on one prompt: Sonnet at `xhigh` added about 2-3 s per call, and a full debate took about 41 s.
- `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` are removed from the CLI's environment, so a key or gateway you configured for the other providers is never used by it.
- Each call runs with tools disabled, from an empty directory, ignoring your personal Claude Code hooks, plugins and `CLAUDE.md`.
- Restart the backend after changing `.env` (`uvicorn --reload` only watches `.py` files).

Analysis reports are exported to `reports/YYYY-MM-DD_<TICKER>.md` for NotebookLM ingestion. The response says whether the export worked (`report_saved`, `report_file`), and the panel only claims a saved report when it did.

### Time limits, concurrency and the run log

A debate run is made of up to 8 LLM calls in four steps, so it is bounded and observable. All of these are optional environment settings (backend `.env` or shell; restart the backend after changing them):

```bash
DEBATE_LLM_CALL_TIMEOUT_SECONDS=60        # one LLM call, its retry included, for every provider
DEBATE_RUN_TIMEOUT_SECONDS=180            # a whole Analyse; past it the answer is HTTP 504 and no verdict
DEBATE_MAX_CONCURRENT_RUNS=2              # runs at once per backend process; one more is HTTP 429, not queued
DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS=10   # each post-run hook (the outcome log write)
```

- A second request for a ticker that is already running **joins** that run instead of starting another (a double click or a second tab costs nothing extra). Closing the browser does not stop a run: it finishes and writes its report.
- The API providers retry once through their SDK; `claude_cli` retries once after a second when a call fails fast, and never after a timeout.
- A bad value, an unknown provider, a missing API key (checked for presence only, never printed) or a missing `claude` command is reported **before** a run starts, as HTTP 503 naming the variable. The panel shows that message.
- Each run writes one line to the backend log, `.run/backend.log` under `make up` (`tail -f .run/backend.log`):
  `Debate run ticker=VCB provider=claude_cli model=haiku status=ok round1_ms=… round2_ms=… synthesis_ms=… total_ms=… joined=1 hook_failures=0`
  (`status` is `ok`, `timeout` or `error`; a stage that did not finish reads `n/a`).
- **Measured latency** (`claude_cli`, model `sonnet`, one run on 2026-10-07): round 1 8.4 s, round 2 8.5 s, synthesis 7.2 s, total 24.1 s, about 8 s per stage, well inside the 60 s per-call and 180 s per-run limits. The older 45-50 s figure was a different model and effort setting. API-provider latency has not been measured, and the 60 s / 180 s / 2 defaults are judgement values: read the run line after more real runs and tune them.
- There is no authentication and the limits are per process. The backend binds to `127.0.0.1` under `make up`; do not expose it to a network (see `docs/KNOWN_ISSUES.md`).

## Quick Start

```bash
# Backend
python -m venv backend/.venv && source backend/.venv/bin/activate
pip install -r backend/requirements.txt
python backend/scripts/train_har_rv.py   # a fresh clone has no HAR model, so no range is served until this has run; validates out of time, writes har_rv_model.json (replaces the .pkl)
uvicorn app.main:app --reload --app-dir backend

# Frontend
cd frontend && npm install && npm run dev
```

## Tests

```bash
pytest backend/tests          # 899 backend tests
cd frontend && npm run test   # 271 frontend tests
```
