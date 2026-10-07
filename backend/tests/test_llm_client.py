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
import logging
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.services.debate import llm_client
from app.services.debate.llm_client import (
    DebateConfigError,
    LLMCallTimeout,
    LLMClient,
    check_debate_config,
    close_llm_clients,
)

# Behaviour is switched by FAKE_CLAUDE_MODE; every call records what it was
# given (argv, stdin, cwd and what is in it) to FAKE_CLAUDE_LOG.
FAKE_CLAUDE = """#!PYTHON
import json, os, sys, time

mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
stdin = sys.stdin.read()
with open(os.environ["FAKE_CLAUDE_LOG"] + ".count", "a") as f:
    f.write("x")  # one mark per attempt
with open(os.environ["FAKE_CLAUDE_LOG"] + ".count") as f:
    attempt = len(f.read())
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
if mode == "orphan":
    # The CLI itself exits at once, but a helper it forked keeps our stdout/stderr pipes open.
    import subprocess
    helper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    with open(os.environ["FAKE_CLAUDE_LOG"] + ".helper", "w") as f:
        f.write(str(helper.pid))
    sys.exit(0)
if mode == "badjson":
    print("this is not json")
    sys.exit(0)
if mode == "jsonlist":
    print("[1, 2]")
    sys.exit(0)
if mode == "error" or (mode == "flaky" and attempt == 1):
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
    monkeypatch.delenv("DEBATE_LLM_CALL_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    monkeypatch.setattr(llm_client, "CLAUDE_CLI_RETRY_DELAY_SECONDS", 0.05)  # keep retry tests fast
    return lambda: json.loads(log.read_text())


@pytest.fixture(autouse=True)
def _no_cached_sdk_clients():
    llm_client._clients.clear()
    yield
    llm_client._clients.clear()


def _attempts() -> int:
    """How many times the fake `claude` was started (one mark per attempt)."""
    return len(Path(os.environ["FAKE_CLAUDE_LOG"] + ".count").read_text())


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
    monkeypatch.setenv("DEBATE_LLM_CALL_TIMEOUT_SECONDS", "0.5")

    started = time.monotonic()
    with pytest.raises(LLMCallTimeout, match="timed out"):
        await LLMClient().chat(MESSAGES)

    assert time.monotonic() - started < 3  # the ceiling plus a small margin, not the fake's 10 s
    assert await _all_dead_within([fake_claude()["pid"]])


@pytest.mark.asyncio
async def test_claude_cli_timeout_kills_descendants_and_does_not_wait_for_them(
    fake_claude, monkeypatch, tmp_path
):
    # Killing only the direct child leaves a helper holding the stdout/stderr
    # pipes open: on asyncio that stalls the call until the helper exits, on
    # uvloop it orphans the helper. Both are avoided by killing the group.
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "descendant")
    monkeypatch.setenv("DEBATE_LLM_CALL_TIMEOUT_SECONDS", "0.5")

    started = time.monotonic()
    with pytest.raises(LLMCallTimeout, match="timed out"):
        await LLMClient().chat(MESSAGES)
    assert time.monotonic() - started < 5  # not "as long as the helper lives" (10s)

    helper_pid = int((tmp_path / "call.json.helper").read_text())
    assert await _all_dead_within([fake_claude()["pid"], helper_pid])


@pytest.mark.asyncio
async def test_claude_cli_timeout_kills_a_helper_that_outlives_the_cli_itself(fake_claude, monkeypatch, tmp_path):
    # The CLI has already exited (returncode set) but a descendant holds the pipes, so the call
    # hangs until the ceiling: the group must be killed even then, not only while the CLI is alive.
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "orphan")
    monkeypatch.setenv("DEBATE_LLM_CALL_TIMEOUT_SECONDS", "0.5")

    with pytest.raises(LLMCallTimeout):
        await LLMClient().chat(MESSAGES)

    helper_pid = int((tmp_path / "call.json.helper").read_text())
    assert await _all_dead_within([helper_pid])


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


# ===========================================================================
# harden-debate-runtime: ceiling, retries, client reuse, configuration check
# ===========================================================================


def test_the_call_ceiling_defaults_to_60_seconds_and_is_configurable(monkeypatch):
    monkeypatch.delenv("DEBATE_LLM_CALL_TIMEOUT_SECONDS", raising=False)
    assert LLMClient().call_timeout == 60

    monkeypatch.setenv("DEBATE_LLM_CALL_TIMEOUT_SECONDS", "20")
    assert LLMClient().call_timeout == 20


def test_the_timeout_error_is_a_runtime_error_so_callers_that_catch_it_keep_working():
    assert issubclass(LLMCallTimeout, RuntimeError)


@pytest.mark.asyncio
async def test_a_timeout_is_not_retried(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "slow")
    monkeypatch.setenv("DEBATE_LLM_CALL_TIMEOUT_SECONDS", "0.5")

    with pytest.raises(LLMCallTimeout):
        await LLMClient().chat(MESSAGES)

    assert _attempts() == 1


@pytest.mark.asyncio
async def test_a_fast_failure_is_retried_once_and_the_second_attempts_text_returned(
    fake_claude, monkeypatch, caplog
):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "flaky")  # exits 1 on the first attempt only

    with caplog.at_level(logging.WARNING, logger=llm_client.logger.name):
        text = await LLMClient().chat(MESSAGES)

    assert text == "bull\n- RSI 62 supports momentum"
    assert _attempts() == 2
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "claude_cli" in warnings[0] and "attempt 1" in warnings[0]


@pytest.mark.asyncio
async def test_at_most_two_attempts_and_the_final_failure_is_logged_without_the_prompt(
    fake_claude, monkeypatch, caplog
):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "error")

    with caplog.at_level(logging.WARNING, logger=llm_client.logger.name):
        with pytest.raises(RuntimeError, match="issue with the selected model"):
            await LLMClient().chat(MESSAGES)

    assert _attempts() == 2
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2  # the retry and the final failure
    assert "attempt 2" in warnings[1]
    assert not any("Ticker: SAB" in w or "Be terse." in w for w in warnings)


@pytest.mark.asyncio
async def test_a_missing_binary_is_not_retried(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "claude_cli")
    monkeypatch.setattr(llm_client, "CLAUDE_CLI_RETRY_DELAY_SECONDS", 5)  # a retry would cost 5 s

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="Claude Code"):
        await LLMClient().chat(MESSAGES)

    assert time.monotonic() - started < 2


def _install_fake_sdk(monkeypatch, provider, hang=False):
    """Replace the `openai` / `anthropic` module with a stub; returns the clients it built."""
    built = []

    async def create(**_kwargs):
        if hang:
            await asyncio.sleep(30)
        if provider == "openai":
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="sdk reply"))])
        return SimpleNamespace(content=[SimpleNamespace(text="sdk reply")])

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
            endpoint = SimpleNamespace(create=create)
            self.chat = SimpleNamespace(completions=endpoint)  # openai
            self.messages = endpoint  # anthropic
            built.append(self)

        async def close(self):
            self.closed = True

    module_name, class_name = ("openai", "AsyncOpenAI") if provider == "openai" else ("anthropic", "AsyncAnthropic")
    monkeypatch.setitem(sys.modules, module_name, SimpleNamespace(**{class_name: FakeClient}))
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", provider)
    return built


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
async def test_two_calls_share_one_sdk_client_built_with_the_ceiling_and_one_retry(monkeypatch, provider):
    monkeypatch.setenv("DEBATE_LLM_CALL_TIMEOUT_SECONDS", "20")
    built = _install_fake_sdk(monkeypatch, provider)

    assert await LLMClient().chat(MESSAGES) == "sdk reply"
    assert await LLMClient().chat(MESSAGES) == "sdk reply"  # a second instance, as each agent has its own

    assert len(built) == 1
    assert built[0].kwargs == {"timeout": httpx.Timeout(20.0, connect=5.0), "max_retries": 1}


@pytest.mark.asyncio
async def test_a_different_ceiling_gets_its_own_client(monkeypatch):
    built = _install_fake_sdk(monkeypatch, "openai")

    monkeypatch.setenv("DEBATE_LLM_CALL_TIMEOUT_SECONDS", "20")
    await LLMClient().chat(MESSAGES)
    monkeypatch.setenv("DEBATE_LLM_CALL_TIMEOUT_SECONDS", "30")
    await LLMClient().chat(MESSAGES)

    assert len(built) == 2


@pytest.mark.asyncio
async def test_closing_the_clients_closes_each_and_the_next_call_builds_a_new_one(monkeypatch):
    built = _install_fake_sdk(monkeypatch, "openai")
    await LLMClient().chat(MESSAGES)

    await close_llm_clients()

    assert built[0].closed
    await LLMClient().chat(MESSAGES)
    assert len(built) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
async def test_a_hung_sdk_call_is_cut_off_at_the_ceiling(monkeypatch, provider):
    monkeypatch.setenv("DEBATE_LLM_CALL_TIMEOUT_SECONDS", "0.3")
    _install_fake_sdk(monkeypatch, provider, hang=True)

    started = time.monotonic()
    with pytest.raises(LLMCallTimeout, match="timed out"):
        await LLMClient().chat(MESSAGES)

    assert time.monotonic() - started < 3


# --- configuration check ----------------------------------------------------

FAKE_KEY = "sk-test-fake-0123456789"
SETTINGS = (
    "DEBATE_LLM_PROVIDER", "DEBATE_LLM_MODEL", "DEBATE_LLM_EFFORT", "DEBATE_MAX_TOKENS_PER_CALL",
    "DEBATE_LLM_CALL_TIMEOUT_SECONDS", "DEBATE_RUN_TIMEOUT_SECONDS", "DEBATE_MAX_CONCURRENT_RUNS",
    "DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
)


@pytest.fixture
def configured(monkeypatch):
    """A valid OpenAI setup: every debate setting at its default, a fake credential present."""
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)


def _error_of(check) -> str:
    with pytest.raises(DebateConfigError) as caught:
        check()
    return str(caught.value)


def test_a_valid_configuration_passes(configured):
    check_debate_config()


def test_the_config_error_is_a_value_error_so_existing_handlers_keep_working():
    assert issubclass(DebateConfigError, ValueError)


COUNT_SETTINGS = ("DEBATE_MAX_TOKENS_PER_CALL", "DEBATE_MAX_CONCURRENT_RUNS")  # whole numbers
SECONDS_SETTINGS = (  # fractional values are fine
    "DEBATE_LLM_CALL_TIMEOUT_SECONDS", "DEBATE_RUN_TIMEOUT_SECONDS", "DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS",
)
BAD_NUMBERS = ["abc", "0", "-1", "nan", "inf"]
BAD_SETTINGS = [(name, value) for name in (*COUNT_SETTINGS, *SECONDS_SETTINGS) for value in BAD_NUMBERS] + [
    (name, "2.5") for name in COUNT_SETTINGS
]


@pytest.mark.parametrize("name, value", BAD_SETTINGS)
def test_a_bad_number_is_refused_with_the_variable_named_and_no_credential(configured, monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    message = _error_of(check_debate_config)

    assert name in message
    assert FAKE_KEY not in message


def test_a_blank_number_means_the_default(configured, monkeypatch):
    monkeypatch.setenv("DEBATE_RUN_TIMEOUT_SECONDS", "  ")

    check_debate_config()


def test_an_invalid_effort_is_refused_for_claude_cli(fake_claude, monkeypatch):
    monkeypatch.setenv("DEBATE_LLM_EFFORT", "turbo")

    assert "DEBATE_LLM_EFFORT" in _error_of(check_debate_config)


def test_an_unknown_provider_is_refused_instead_of_becoming_a_neutral_verdict(configured, monkeypatch):
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "opneai")

    message = _error_of(check_debate_config)

    assert "DEBATE_LLM_PROVIDER" in message and FAKE_KEY not in message


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_a_missing_openai_key_is_named_and_no_value_is_printed(configured, monkeypatch, blank):
    if blank is None:
        monkeypatch.delenv("OPENAI_API_KEY")
    else:
        monkeypatch.setenv("OPENAI_API_KEY", blank)

    assert "OPENAI_API_KEY" in _error_of(check_debate_config)


def test_anthropic_accepts_either_credential_and_names_both_when_neither_is_set(configured, monkeypatch):
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("OPENAI_API_KEY")

    message = _error_of(check_debate_config)
    assert "ANTHROPIC_API_KEY" in message and "ANTHROPIC_AUTH_TOKEN" in message

    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", FAKE_KEY)
    check_debate_config()


def test_claude_cli_needs_the_binary_on_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "claude_cli")
    monkeypatch.setenv("PATH", str(tmp_path))

    assert "claude" in _error_of(check_debate_config)


def test_claude_cli_passes_when_the_binary_is_present(fake_claude):
    check_debate_config()


@pytest.mark.parametrize(
    "name, value, provider",
    [
        ("DEBATE_LLM_EFFORT", "turbo", "claude_cli"),
        ("DEBATE_MAX_TOKENS_PER_CALL", "abc", "openai"),
        ("DEBATE_LLM_CALL_TIMEOUT_SECONDS", "0", "openai"),
    ],
)
def test_constructing_the_client_with_a_bad_value_raises_the_config_error(
    configured, monkeypatch, name, value, provider
):
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", provider)
    monkeypatch.setenv(name, value)

    assert name in _error_of(LLMClient)
