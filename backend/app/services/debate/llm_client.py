"""LLM client abstraction for the debate engine.

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

Usage:
    client = LLMClient()
    response = await client.chat([{"role": "user", "content": "..."}])
    # response is a plain string
"""

import asyncio
import json
import os
import shutil
import signal
import tempfile
from typing import Any

# Per-call ceiling for the claude_cli provider. A headless call takes a few
# seconds; this only catches a hung process.
CLAUDE_CLI_TIMEOUT_SECONDS = 120
# DEBATE_LLM_MODEL's own default is an OpenAI model name the CLI would reject,
# and the account's default model can be a slow, expensive one.
CLAUDE_CLI_DEFAULT_MODEL = "haiku"
# DEBATE_LLM_EFFORT values the CLI's --effort understands. Validated here
# because the CLI itself accepts any string and silently runs at its default.
CLAUDE_CLI_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
# Dropped from the CLI's environment: with any of these set it would use that
# credential/endpoint instead of the account login this provider exists for.
CLAUDE_CLI_STRIPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")


class LLMClient:
    """Thin async wrapper around OpenAI, Anthropic or the Claude CLI."""

    def __init__(self) -> None:
        self.provider: str = os.getenv("DEBATE_LLM_PROVIDER", "openai").lower()
        self.model: str = os.getenv("DEBATE_LLM_MODEL", "gpt-4o-mini")
        self.max_tokens: int = int(os.getenv("DEBATE_MAX_TOKENS_PER_CALL", "1024"))
        # claude_cli only: reasoning effort for every agent. Unset = CLI default.
        self.effort: str | None = (os.getenv("DEBATE_LLM_EFFORT") or "").lower() or None
        if (
            self.provider == "claude_cli"
            and self.effort is not None
            and self.effort not in CLAUDE_CLI_EFFORT_LEVELS
        ):
            raise ValueError(
                f"Unknown DEBATE_LLM_EFFORT '{self.effort}'. "
                f"Supported: {', '.join(CLAUDE_CLI_EFFORT_LEVELS)}."
            )

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Send a chat completion request; return the assistant's text."""
        if self.provider == "openai":
            return await self._chat_openai(messages)
        if self.provider == "anthropic":
            return await self._chat_anthropic(messages)
        if self.provider == "claude_cli":
            return await self._chat_claude_cli(messages)
        raise ValueError(
            f"Unknown DEBATE_LLM_PROVIDER '{self.provider}'. "
            "Supported: 'openai', 'anthropic', 'claude_cli'."
        )

    async def _chat_openai(self, messages: list[dict[str, str]]) -> str:
        from openai import AsyncOpenAI  # type: ignore[import]

        client = AsyncOpenAI()
        resp = await client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=self.max_tokens,
            temperature=0.2,  # low temperature for consistent structured output
        )
        content = resp.choices[0].message.content
        return content or ""

    async def _chat_anthropic(self, messages: list[dict[str, str]]) -> str:
        import anthropic as _anthropic  # type: ignore[import]

        # Anthropic expects system message separately
        system_msg = ""
        user_messages: list[dict[str, Any]] = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_messages.append({"role": m["role"], "content": m["content"]})

        client = _anthropic.AsyncAnthropic()
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
            raise RuntimeError(
                "DEBATE_LLM_PROVIDER=claude_cli needs the `claude` command "
                "(Claude Code) on PATH, logged in to your Claude account."
            )

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
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=CLAUDE_CLI_TIMEOUT_SECONDS
                )
            except TimeoutError:
                raise RuntimeError(
                    f"claude CLI timed out after {CLAUDE_CLI_TIMEOUT_SECONDS}s"
                ) from None
            finally:
                # Timeout or a cancelled request must not leave it running.
                if proc.returncode is None:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)  # pgid == pid (new session)
                    except ProcessLookupError:
                        pass
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
            raise RuntimeError(
                f"claude CLI returned non-JSON output (exit {proc.returncode}): {stderr_text}"
            )
        if proc.returncode != 0 or data.get("is_error"):
            detail = data.get("result") or data.get("subtype") or stderr_text or "no details"
            raise RuntimeError(f"claude CLI failed: {detail}")
        return data.get("result") or ""
