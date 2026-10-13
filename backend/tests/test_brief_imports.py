"""The brief calls no language model: nothing in its import graph loads a model client (spec: "The brief is
produced by a hand-run script and calls no language model")."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys

import pytest

from .test_brief_support import BACKEND, brief_isolation  # noqa: F401

PACKAGE = BACKEND / "app" / "services" / "brief"
SCRIPT = BACKEND / "scripts" / "weekly_brief.py"
# `news_feeds` (httpx and defusedxml only) is reached by the eligibility chain and is not a model client.
BANNED_MODULES = (
    "anthropic", "openai", "google.generativeai", "claude_agent_sdk", "app.services.debate.llm_client",
    "app.services.debate.engine", "app.services.debate.runner", "app.services.debate.synthesiser",
    "app.services.debate.news",
)
BANNED_TEXT = re.compile(
    r"anthropic|openai|claude_agent_sdk|google\.generativeai|llm_client|debate\.(engine|runner|synthesiser)\b|debate\.news\b"
)

PROBE = """
import importlib.util, json, sys
sys.path.insert(0, {backend!r})
import app.services.brief.run
spec = importlib.util.spec_from_file_location("weekly_brief_probe", {script!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
banned = {banned!r}
loaded = sorted(
    name for name in sys.modules
    if any(name == b or name.startswith(b + ".") for b in banned)
)
print(json.dumps(loaded))
"""


def _loaded_banned_modules() -> list[str]:
    code = PROBE.format(backend=str(BACKEND), script=str(SCRIPT), banned=list(BANNED_MODULES))
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=120, cwd="/",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_a_fresh_interpreter_loads_no_language_model_module():
    assert _loaded_banned_modules() == []


def test_the_probe_would_see_one():
    """The scan is live: an interpreter that loads a banned module is reported."""
    code = PROBE.format(backend=str(BACKEND), script=str(SCRIPT), banned=["app.services.debate"])
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=120, cwd="/")

    assert "app.services.debate" in json.loads(result.stdout.strip().splitlines()[-1])


def _imported_names(path) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names += [node.module or "", *[f"{node.module}.{alias.name}" for alias in node.names]]
    return names


@pytest.mark.parametrize("path", [*sorted(PACKAGE.glob("*.py")), SCRIPT], ids=lambda p: p.name)
def test_no_source_imports_a_model_client(path):
    offenders = [
        name for name in _imported_names(path)
        if any(name == banned or name.startswith(banned + ".") for banned in BANNED_MODULES)
    ]

    assert offenders == []


@pytest.mark.parametrize("path", [*sorted(PACKAGE.glob("*.py")), SCRIPT], ids=lambda p: p.name)
def test_no_source_even_names_a_model_client(path):
    assert BANNED_TEXT.search(path.read_text(encoding="utf-8")) is None


def test_the_static_pattern_lets_news_feeds_pass_and_catches_the_rest():
    assert BANNED_TEXT.search("from app.services.debate.news_feeds import x") is None
    for text in ("import anthropic", "from openai import X", "app.services.debate.engine", "debate.news import", "claude_agent_sdk"):
        assert BANNED_TEXT.search(text), text
