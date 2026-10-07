"""LLM client abstraction for the debate engine, and the debate's environment settings.

Reads DEBATE_LLM_PROVIDER (default: openai) and DEBATE_LLM_MODEL
(default: gpt-4o-mini) from environment. Supports openai, anthropic and
claude_cli providers without hard-wiring to any of them.

`claude_cli` runs the `claude` command (Claude Code) headless, so the debate
can use a Claude subscription login instead of an API key. Caveats: each call
spawns a process (slower than an API call), counts against the subscription's
usage limits, only works where Claude Code is installed and logged in, and
ignores DEBATE_MAX_TOKENS_PER_CALL and the temperature. DEBATE_LLM_EFFORT
(low, medium, high, xhigh, max) sets the reasoning effort for every agent;
unset uses the CLI's default. ANTHROPIC_API_KEY,
ANTHROPIC_AUTH_TOKEN and ANTHROPIC_BASE_URL are removed from the CLI's
environment, so a key or gateway configured for the other providers is never
picked up by it. (Other provider switches, e.g. for a cloud platform, are not
touched.)

Time and retry policy (harden-debate-runtime): every call, for every provider,
is bounded by DEBATE_LLM_CALL_TIMEOUT_SECONDS (default 60) including its retry
and raises `LLMCallTimeout` when it expires. The API providers retry through
their SDK, capped at one retry; `claude_cli` retries once, after a second, when
it failed fast (not on a timeout, not on a missing binary). The SDK clients are
built once per process and closed by `close_llm_clients()`.

`check_debate_config()` validates every debate setting without a network call;
an invalid value raises `DebateConfigError`, whose message names the variable
and never a credential. The run-level settings (DEBATE_RUN_TIMEOUT_SECONDS,
DEBATE_MAX_CONCURRENT_RUNS, DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS) are parsed
here too, so there is one place that reads them and one check that covers them.

Usage:
    client = LLMClient()
    response = await client.chat([{"role": "user", "content": "..."}])
    # response is a plain string
"""

import asyncio
import json
import logging
import math
import os
import shutil
import signal
import tempfile
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

PROVIDERS = ("openai", "anthropic", "claude_cli")

# Defaults of the debate settings; the README documents them. Judgement values,
# measured only for claude_cli (about 10 s per call): tune them from the run log line.
DEFAULT_CALL_TIMEOUT_SECONDS = 60
DEFAULT_RUN_TIMEOUT_SECONDS = 180
DEFAULT_MAX_CONCURRENT_RUNS = 2
DEFAULT_HOOK_TIMEOUT_SECONDS = 10
DEFAULT_MAX_TOKENS_PER_CALL = 1024

# Connect timeout of the SDK clients, and their own retry (it knows which errors are
# transient and honours Retry-After; the SDK default of 2 would burn the ceiling).
SDK_CONNECT_TIMEOUT_SECONDS = 5.0
SDK_MAX_RETRIES = 1
# claude_cli: one retry, after this pause, for a call that failed fast.
CLAUDE_CLI_MAX_ATTEMPTS = 2
CLAUDE_CLI_RETRY_DELAY_SECONDS = 1.0
# DEBATE_LLM_MODEL's own default is an OpenAI model name the CLI would reject,
# and the account's default model can be a slow, expensive one.
CLAUDE_CLI_DEFAULT_MODEL = "haiku"
# DEBATE_LLM_EFFORT values the CLI's --effort understands. Validated here
# because the CLI itself accepts any string and silently runs at its default.
CLAUDE_CLI_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
# Dropped from the CLI's environment: with any of these set it would use that
# credential/endpoint instead of the account login this provider exists for.
CLAUDE_CLI_STRIPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")
CLAUDE_CLI_MISSING_MESSAGE = (
    "DEBATE_LLM_PROVIDER=claude_cli needs the `claude` command "
    "(Claude Code) on PATH, logged in to your Claude account."
)


class DebateConfigError(ValueError):
    """An invalid or incomplete debate configuration. The message names the variable,
    never a credential value."""


class LLMCallTimeout(RuntimeError):
    """One LLM call, retry included, ran past DEBATE_LLM_CALL_TIMEOUT_SECONDS."""


class _TransientCliFailure(RuntimeError):
    """A claude_cli call that failed fast (non-JSON output, non-zero exit, is_error): worth one retry."""


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def _env_number(name: str, default: float, *, integer: bool = False) -> float:
    """A positive finite number from the environment; unset or blank means `default`."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        value = None
    if value is None or not math.isfinite(value) or value <= 0:
        raise DebateConfigError(f"{name} must be a positive {'integer' if integer else 'number'}.")
    return value


def run_timeout_seconds() -> float:
    return _env_number("DEBATE_RUN_TIMEOUT_SECONDS", DEFAULT_RUN_TIMEOUT_SECONDS)


def max_concurrent_runs() -> int:
    return int(_env_number("DEBATE_MAX_CONCURRENT_RUNS", DEFAULT_MAX_CONCURRENT_RUNS, integer=True))


def hook_timeout_seconds() -> float:
    return _env_number("DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS", DEFAULT_HOOK_TIMEOUT_SECONDS)


def _unknown_provider(provider: str) -> DebateConfigError:
    # The value is not echoed: it goes to the client, and a key pasted into the wrong variable
    # would travel with it.
    return DebateConfigError("Unknown DEBATE_LLM_PROVIDER. Supported: 'openai', 'anthropic', 'claude_cli'.")


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    max_tokens: int
    effort: str | None  # claude_cli only: reasoning effort for every agent. None = CLI default.
    call_timeout: float


def _read_settings() -> LLMSettings:
    provider = os.getenv("DEBATE_LLM_PROVIDER", "openai").lower()
    effort = (os.getenv("DEBATE_LLM_EFFORT") or "").lower() or None
    if provider == "claude_cli" and effort is not None and effort not in CLAUDE_CLI_EFFORT_LEVELS:
        raise DebateConfigError(
            f"Unknown DEBATE_LLM_EFFORT. Supported: {', '.join(CLAUDE_CLI_EFFORT_LEVELS)}."
        )
    return LLMSettings(
        provider=provider,
        model=os.getenv("DEBATE_LLM_MODEL", "gpt-4o-mini"),
        max_tokens=int(_env_number("DEBATE_MAX_TOKENS_PER_CALL", DEFAULT_MAX_TOKENS_PER_CALL, integer=True)),
        effort=effort,
        call_timeout=_env_number("DEBATE_LLM_CALL_TIMEOUT_SECONDS", DEFAULT_CALL_TIMEOUT_SECONDS),
    )


def _is_set(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def check_debate_config() -> None:
    """Raise `DebateConfigError` if the debate cannot run as configured. No network call.

    Credentials are checked for presence only (the SDKs accept other sources too:
    an unusual but valid setup would need its variable added here), never validated
    and never printed.
    """
    provider = os.getenv("DEBATE_LLM_PROVIDER", "openai").lower()
    if provider not in PROVIDERS:
        raise _unknown_provider(provider)
    _read_settings()  # effort and numeric LLM settings
    run_timeout_seconds()
    max_concurrent_runs()
    hook_timeout_seconds()
    if provider == "openai" and not _is_set("OPENAI_API_KEY"):
        raise DebateConfigError("DEBATE_LLM_PROVIDER=openai needs OPENAI_API_KEY to be set.")
    if provider == "anthropic" and not (_is_set("ANTHROPIC_API_KEY") or _is_set("ANTHROPIC_AUTH_TOKEN")):
        raise DebateConfigError(
            "DEBATE_LLM_PROVIDER=anthropic needs ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) to be set."
        )
    if provider == "claude_cli" and shutil.which("claude") is None:
        raise DebateConfigError(CLAUDE_CLI_MISSING_MESSAGE)


# ---------------------------------------------------------------------------
# SDK clients: one per provider and ceiling for the whole process
# ---------------------------------------------------------------------------

# ponytail: one client per (provider, ceiling), bound to the running event loop's
# connections; fine for one uvicorn loop. Credentials are read when it is built, so a
# changed key needs a restart.
_clients: dict[tuple[str, float], Any] = {}


def _sdk_client(provider: str, call_timeout: float) -> Any:
    key = (provider, call_timeout)
    client = _clients.get(key)
    if client is None:
        import httpx

        timeout = httpx.Timeout(call_timeout, connect=SDK_CONNECT_TIMEOUT_SECONDS)
        if provider == "openai":
            from openai import AsyncOpenAI  # type: ignore[import]

            client = AsyncOpenAI(timeout=timeout, max_retries=SDK_MAX_RETRIES)
        else:
            import anthropic as _anthropic  # type: ignore[import]

            client = _anthropic.AsyncAnthropic(timeout=timeout, max_retries=SDK_MAX_RETRIES)
        _clients[key] = client
    return client


async def close_llm_clients() -> None:
    """Close every SDK client built so far (application shutdown)."""
    clients = list(_clients.values())
    _clients.clear()
    for client in clients:
        try:
            await client.close()
        except Exception:
            logger.warning("Closing an LLM SDK client failed", exc_info=True)


class LLMClient:
    """Thin async wrapper around OpenAI, Anthropic or the Claude CLI."""

    def __init__(self) -> None:
        settings = _read_settings()
        self.provider: str = settings.provider
        self.model: str = settings.model
        self.max_tokens: int = settings.max_tokens
        self.effort: str | None = settings.effort
        self.call_timeout: float = settings.call_timeout

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Send a chat completion request; return the assistant's text.

        Bounded by `call_timeout` for the whole call, retry included.
        """
        started = time.monotonic()
        attempt = 0
        ceiling = asyncio.timeout(self.call_timeout)
        try:
            async with ceiling:
                while True:
                    attempt += 1
                    try:
                        return await self._chat_once(messages)
                    except _TransientCliFailure:
                        if attempt >= CLAUDE_CLI_MAX_ATTEMPTS:
                            raise
                        self._log("failed, retrying", attempt, started)
                        await asyncio.sleep(CLAUDE_CLI_RETRY_DELAY_SECONDS)
        except Exception as exc:
            timed_out = isinstance(exc, TimeoutError) and ceiling.expired()
            self._log("timed out" if timed_out else "failed", attempt, started)
            if timed_out:
                raise LLMCallTimeout(f"{self.provider} call timed out after {self.call_timeout:g}s") from None
            raise

    def _log(self, event: str, attempt: int, started: float) -> None:
        """Provider, attempt and elapsed time only: never prompt text or credentials."""
        logger.warning(
            "LLM call %s (provider=%s, attempt %d, elapsed %.1fs)",
            event, self.provider, attempt, time.monotonic() - started,
        )

    async def _chat_once(self, messages: list[dict[str, str]]) -> str:
        if self.provider == "openai":
            return await self._chat_openai(messages)
        if self.provider == "anthropic":
            return await self._chat_anthropic(messages)
        if self.provider == "claude_cli":
            return await self._chat_claude_cli(messages)
        raise _unknown_provider(self.provider)

    async def _chat_openai(self, messages: list[dict[str, str]]) -> str:
        client = _sdk_client("openai", self.call_timeout)
        resp = await client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=self.max_tokens,
            temperature=0.2,  # low temperature for consistent structured output
        )
        content = resp.choices[0].message.content
        return content or ""

    async def _chat_anthropic(self, messages: list[dict[str, str]]) -> str:
        # Anthropic expects system message separately
        system_msg = ""
        user_messages: list[dict[str, Any]] = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_messages.append({"role": m["role"], "content": m["content"]})

        client = _sdk_client("anthropic", self.call_timeout)
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=user_messages,
        )
        if system_msg:
            kwargs["system"] = system_msg

        resp = await client.messages.create(**kwargs)
        return resp.content[0].text if resp.content else ""

    async def _chat_claude_cli(self, messages: list[dict[str, str]]) -> str:
        claude = shutil.which("claude")
        if claude is None:
            raise RuntimeError(CLAUDE_CLI_MISSING_MESSAGE)

        system_msg = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        # ponytail: the debate agents only ever send [system, user]; any other
        # non-system messages are flattened into one prompt, losing turn
        # structure. Use --input-format stream-json if that ever matters.
        # NUL is dropped: argv can't carry it, and a scraped headline containing
        # one would otherwise break the agent (the API providers accept it).
        prompt = "\n\n".join(m["content"] for m in messages if m["role"] != "system")
        prompt = prompt.replace("\x00", "")

        cmd = [
            claude, "-p", "--output-format", "json",
            "--model", os.getenv("DEBATE_LLM_MODEL") or CLAUDE_CLI_DEFAULT_MODEL,
            # Text completion only: no tools, so the model can't act on the
            # machine. User settings (hooks, plugins, MCP servers) are skipped
            # — they added ~35k tokens per call and can inject context into
            # the prompt. --bare would do this too but never reads the login.
            "--tools", "",
            "--setting-sources", "project",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-session-persistence",
        ]
        if system_msg:
            cmd += ["--system-prompt", system_msg]
        if self.effort:
            cmd += ["--effort", self.effort]
        # The prompt goes in argv, last, after `--` (before any variadic option
        # such as --tools it would be swallowed as a tool name; after `--` a
        # prompt starting with "-" isn't parsed as a flag). Not over stdin:
        # `claude -p` waits only 3s for stdin before proceeding without it, and
        # the debate agents' synchronous work can stall the event loop past
        # that, so one agent silently got no prompt. It's market data, so
        # visibility in `ps` is fine; Linux caps one argument at 128 KiB.
        cmd += ["--", prompt]

        env = {k: v for k, v in os.environ.items() if k not in CLAUDE_CLI_STRIPPED_ENV}

        # Run from an empty directory so no project .claude/ or CLAUDE.md is
        # picked up. stdin is /dev/null so the CLI sees EOF at once.
        with tempfile.TemporaryDirectory() as empty_dir:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=empty_dir,
                env=env,
                # Own process group, so a timeout/cancel can kill the CLI *and*
                # anything it forked: a helper holding our stdout/stderr pipes
                # open would otherwise stall `wait()` (asyncio) or be orphaned
                # (uvloop).
                start_new_session=True,
            )
            try:
                # No timeout of its own: `chat` holds the ceiling and cancels this.
                stdout, stderr = await proc.communicate()
            finally:
                # A timeout or a cancelled run must not leave it running. The group is killed even
                # when the CLI itself has exited: a helper it forked can still hold our pipes.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)  # pgid == pid (new session); gone = fine
                except ProcessLookupError:
                    pass
                if proc.returncode is None:
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except TimeoutError:
                        pass

        stderr_text = stderr.decode(errors="replace")[:300]
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            raise _TransientCliFailure(
                f"claude CLI returned non-JSON output (exit {proc.returncode}): {stderr_text}"
            )
        if proc.returncode != 0 or data.get("is_error"):
            detail = data.get("result") or data.get("subtype") or stderr_text or "no details"
            raise _TransientCliFailure(f"claude CLI failed: {detail}")
        return data.get("result") or ""
