"""Tests for LLMClient's `claude_cli` provider.

The provider shells out to the `claude` binary (Claude Code, headless) so the
debate can run on a Claude subscription login instead of an API key. These
tests put a fake `claude` executable on PATH rather than mocking subprocess
calls, so argv, stdin, the working directory, exit codes and timeouts all go
through the real subprocess plumbing.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import pytest

from app.services.debate import llm_client
from app.services.debate.llm_client import LLMClient

# Behaviour is switched by FAKE_CLAUDE_MODE; every call records what it was
# given (argv, stdin, cwd and what is in it) to FAKE_CLAUDE_LOG.
FAKE_CLAUDE = """#!PYTHON
import json, os, sys, time

mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
stdin = sys.stdin.read()
with open(os.environ["FAKE_CLAUDE_LOG"], "w") as f:
    json.dump(
        {
            "pid": os.getpid(),
            "argv": sys.argv[1:],
            "stdin": stdin,
            "cwd": os.getcwd(),
            "cwd_entries": os.listdir("."),
            "anthropic_env": sorted(k for k in os.environ if k.startswith("ANTHROPIC_")),
        },
        f,
    )

if mode == "slow":
    time.sleep(10)
if mode == "descendant":
    # Like a CLI that forks a helper which inherits our stdout/stderr pipes.
    import subprocess
    helper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    with open(os.environ["FAKE_CLAUDE_LOG"] + ".helper", "w") as f:
        f.write(str(helper.pid))
    time.sleep(10)
if mode == "badjson":
    print("this is not json")
    sys.exit(0)
if mode == "jsonlist":
    print("[1, 2]")
    sys.exit(0)
if mode == "error":
    print(json.dumps({"is_error": True, "result": "There's an issue with the selected model (x)."}))
    sys.exit(1)
if mode == "error_nodetail":
    print(json.dumps({"is_error": True, "subtype": "error_max_turns"}))
    sys.exit(1)
print(json.dumps({"is_error": False, "result": "bull\\n- RSI 62 supports momentum"}))
"""

MESSAGES = [
    {"role": "system", "content": "Be terse."},
    {"role": "user", "content": "Ticker: SAB"},
]


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """Put a fake `claude` alone on PATH; returns a reader for its last call."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(FAKE_CLAUDE.replace("PYTHON", sys.executable))
    script.chmod(0o755)
    log = tmp_path / "call.json"

    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "claude_cli")
    monkeypatch.delenv("DEBATE_LLM_MODEL", raising=False)
    monkeypatch.delenv("DEBATE_LLM_EFFORT", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    return lambda: json.loads(log.read_text())


def _alive(pid: int) -> bool:
    """A zombie waiting to be reaped counts as dead."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


async def _all_dead_within(pids, seconds=3.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not any(_alive(p) for p in pids):
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.mark.asyncio
async def test_claude_cli_returns_the_result_text(fake_claude):
    text = await LLMClient().chat(MESSAGES)

    assert text == "bull\n- RSI 62 supports momentum"


@pytest.mark.asyncio
async def test_claude_cli_passes_system_prompt_as_flag_and_user_message_after_double_dash(fake_claude):
    await LLMClient().chat(MESSAGES)

    argv = fake_claude()["argv"]
    assert argv[argv.index("--system-prompt") + 1] == "Be terse."
    # Last, after `--`: before any variadic option (--tools takes a list) it
    # would be swallowed as a tool name, and a prompt starting with "-" would
    # be parsed as a flag.
    assert argv[-2:] == ["--", "Ticker: SAB"]


@pytest.mark.asyncio
async def test_claude_cli_never_hands_the_prompt_over_stdin(fake_claude):
    # `claude -p` waits only 3s for stdin, then proceeds without it and exits
    # 1. The debate agents run synchronous work on the event loop, which can
    # delay a stdin write past that — one agent silently fell back to a
    # canned reply. The prompt therefore goes in argv and stdin is /dev/null.
    await LLMClient().chat(MESSAGES)

    assert fake_claude()["stdin"] == ""


@pytest.mark.asyncio
async def test_claude_cli_prompt_arrives_intact_whatever_it_contains(fake_claude):
    # No shell is involved, so quotes, $VARS, backticks, newlines and unicode
    # (the technical agent's prompt contains "±") are all literal.
    prompt = '- bullet "quoted" \'single\' $HOME `cmd`\nVolatility ±3.10%'

    await LLMClient().chat([{"role": "user", "content": prompt}])

    assert fake_claude()["argv"][-1] == prompt


@pytest.mark.asyncio
async def test_claude_cli_is_isolated_from_user_and_project_config(fake_claude):
    await LLMClient().chat(MESSAGES)

    call = fake_claude()
    argv = call["argv"]
    # No tools: the model only completes text, it can't act on the machine.
    assert argv[argv.index("--tools") + 1] == ""
    # User settings carry hooks/plugins/MCP servers that otherwise inflate
    # every call (~35k tokens measured) and can inject context into prompts.
    assert argv[argv.index("--setting-sources") + 1] == "project"
    for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flag in argv
    # Run from an empty directory so no project .claude/ or CLAUDE.md is read.
    assert call["cwd_entries"] == []
    assert call["cwd"] != os.getcwd()


@pytest.mark.asyncio
async def test_claude_cli_always_uses_the_login_never_an_api_key(fake_claude, monkeypatch):
    # backend/.env is loaded into os.environ; an ANTHROPIC_* value there would
    # otherwise make the CLI bill the API (or a gateway) instead of using the
    # subscription login this provider exists for.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder-key")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "placeholder-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gateway.example.invalid")

    await LLMClient().chat(MESSAGES)

    # Only the credential/endpoint variables: a shell exporting ANTHROPIC_MODEL
    # and the like must not break this.
    assert not set(llm_client.CLAUDE_CLI_STRIPPED_ENV) & set(fake_claude()["anthropic_env"])


@pytest.mark.asyncio
async def test_claude_cli_defaults_to_haiku_when_no_model_is_set(fake_claude):
    # DEBATE_LLM_MODEL's own default is an OpenAI model name; the CLI would
    # reject it, and the account default can be a slow, expensive model.
    await LLMClient().chat(MESSAGES)

    argv = fake_claude()["argv"]
    assert argv[argv.index("--model") + 1] == "haiku"


@pytest.mark.asyncio
async def test_claude_cli_uses_debate_llm_model_when_set(fake_claude, monkeypatch):
    monkeypatch.setenv("DEBATE_LLM_MODEL", "sonnet")

    await LLMClient().chat(MESSAGES)

    argv = fake_claude()["argv"]
    assert argv[argv.index("--model") + 1] == "sonnet"


@pytest.mark.asyncio
async def test_claude_cli_passes_the_configured_reasoning_effort(fake_claude, monkeypatch):
    monkeypatch.setenv("DEBATE_LLM_EFFORT", "XHIGH")  # case-insensitive

    await LLMClient().chat(MESSAGES)

    argv = fake_claude()["argv"]
    assert argv[argv.index("--effort") + 1] == "xhigh"
    assert argv.index("--effort") < argv.index("--")  # before the prompt


@pytest.mark.asyncio
async def test_claude_cli_leaves_effort_to_the_cli_default_when_unset(fake_claude):
    await LLMClient().chat(MESSAGES)

    assert "--effort" not in fake_claude()["argv"]


def test_claude_cli_rejects_an_unknown_effort_instead_of_silently_ignoring_it(monkeypatch):
    # The CLI itself accepts any string and just runs at its default effort
    # (measured: "extra-high" produced no thinking and no error), so a typo
    # would silently do nothing.
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "claude_cli")
    monkeypatch.setenv("DEBATE_LLM_EFFORT", "extra-high")

    with pytest.raises(ValueError, match=r"DEBATE_LLM_EFFORT.*xhigh"):
        LLMClient()


def test_effort_setting_does_not_affect_the_other_providers(monkeypatch):
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("DEBATE_LLM_EFFORT", "extra-high")

    LLMClient()  # must not raise


@pytest.mark.asyncio
async def test_claude_cli_error_surfaces_the_cli_message(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "error")

    with pytest.raises(RuntimeError, match="issue with the selected model"):
        await LLMClient().chat(MESSAGES)


@pytest.mark.asyncio
async def test_claude_cli_non_json_output_raises(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "badjson")

    with pytest.raises(RuntimeError, match="non-JSON"):
        await LLMClient().chat(MESSAGES)


@pytest.mark.asyncio
async def test_claude_cli_json_that_is_not_an_object_raises_runtime_error(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "jsonlist")

    with pytest.raises(RuntimeError, match="non-JSON"):
        await LLMClient().chat(MESSAGES)


@pytest.mark.asyncio
async def test_claude_cli_failure_without_a_result_still_says_why(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "error_nodetail")

    with pytest.raises(RuntimeError, match="error_max_turns"):
        await LLMClient().chat(MESSAGES)


@pytest.mark.asyncio
async def test_claude_cli_prompt_with_a_nul_byte_is_cleaned_not_fatal(fake_claude):
    # A scraped headline can contain anything; argv can't carry NUL, and the
    # API providers would have accepted it, so it must not break the agent.
    await LLMClient().chat([{"role": "user", "content": "head\x00line"}])

    assert fake_claude()["argv"][-1] == "headline"


@pytest.mark.asyncio
async def test_claude_cli_timeout_raises_instead_of_hanging(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "slow")
    monkeypatch.setattr(llm_client, "CLAUDE_CLI_TIMEOUT_SECONDS", 0.5)

    with pytest.raises(RuntimeError, match="timed out"):
        await LLMClient().chat(MESSAGES)

    assert await _all_dead_within([fake_claude()["pid"]])


@pytest.mark.asyncio
async def test_claude_cli_timeout_kills_descendants_and_does_not_wait_for_them(
    fake_claude, monkeypatch, tmp_path
):
    # Killing only the direct child leaves a helper holding the stdout/stderr
    # pipes open: on asyncio that stalls the call until the helper exits, on
    # uvloop it orphans the helper. Both are avoided by killing the group.
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "descendant")
    monkeypatch.setattr(llm_client, "CLAUDE_CLI_TIMEOUT_SECONDS", 0.5)

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="timed out"):
        await LLMClient().chat(MESSAGES)
    assert time.monotonic() - started < 5  # not "as long as the helper lives" (10s)

    helper_pid = int((tmp_path / "call.json.helper").read_text())
    assert await _all_dead_within([fake_claude()["pid"], helper_pid])


@pytest.mark.asyncio
async def test_claude_cli_cancelled_request_kills_the_child(fake_claude, monkeypatch):
    # A client that disconnects mid-debate cancels the request task; the CLI
    # must not keep running (and spending the subscription) on its own.
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "slow")
    task = asyncio.create_task(LLMClient().chat(MESSAGES))

    call = None
    for _ in range(100):  # wait for the fake to have started and logged
        try:
            call = fake_claude()
            break
        except (FileNotFoundError, ValueError):
            await asyncio.sleep(0.05)
    assert call is not None

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await _all_dead_within([call["pid"]])


@pytest.mark.asyncio
async def test_claude_cli_missing_binary_raises_an_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))  # no `claude` here
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "claude_cli")

    with pytest.raises(RuntimeError, match="Claude Code"):
        await LLMClient().chat(MESSAGES)


@pytest.mark.asyncio
async def test_unknown_provider_error_lists_claude_cli(monkeypatch):
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "nope")

    with pytest.raises(ValueError, match="claude_cli"):
        await LLMClient().chat(MESSAGES)
