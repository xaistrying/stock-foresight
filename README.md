# stock-foresight

Stock Foresight is an analytics dashboard for Vietnamese stocks with a multi-agent debate engine that synthesises technical indicators, news context, and macro signals into a structured analysis verdict.

## Multi-Agent Debate Panel

The debate panel is behind a feature flag. To enable it:

```bash
# frontend/.env
VITE_DEBATE_PANEL_ENABLED=true
```

Also set your LLM provider API key:

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
- Slower than an API call: each call starts a process, and one Analyse takes roughly 45-50 s. It also counts against your subscription's usage limits.
- `DEBATE_MAX_TOKENS_PER_CALL` and the temperature are not applied.
- `DEBATE_LLM_EFFORT` applies to every agent; unset uses the CLI's default. An unknown value is rejected with an error (the CLI itself would silently ignore it). Measured on one prompt: Sonnet at `xhigh` added about 2-3 s per call, and a full debate took about 41 s.
- `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` are removed from the CLI's environment, so a key or gateway you configured for the other providers is never used by it.
- Each call runs with tools disabled, from an empty directory, ignoring your personal Claude Code hooks, plugins and `CLAUDE.md`.
- Restart the backend after changing `.env` (`uvicorn --reload` only watches `.py` files).

Analysis reports are exported to `reports/YYYY-MM-DD_<TICKER>.md` for NotebookLM ingestion.

## Quick Start

```bash
# Backend
python -m venv backend/.venv && source backend/.venv/bin/activate
pip install -r backend/requirements.txt
python backend/scripts/train_har_rv.py   # train volatility model (once)
uvicorn app.main:app --reload --app-dir backend

# Frontend
cd frontend && npm install && npm run dev
```

## Tests

```bash
pytest backend/tests          # 263 backend tests
cd frontend && npm run test   # 113 frontend tests
```
