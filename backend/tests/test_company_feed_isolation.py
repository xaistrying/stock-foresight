"""The company feed is started only by hand and read by nothing else (`company-feed`: "The snapshot runs
only by hand"; "No route exposes the log"; "News agent unchanged").

One reader is allowed, by exact path: the weekly brief's adapter, `app/services/brief/feed_source.py`, which
imports the store module's read helpers only (`add-dividend-and-ex-date-lines`). A second brief file that names
or imports the feed fails these tests.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.db import company_feed_log
from app.services.debate import runner

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND / "app"
PACKAGE = APP / "services" / "company_feed"
OWN_FILES = {APP / "db" / "company_feed_log.py"}
ADAPTER = APP / "services" / "brief" / "feed_source.py"  # the one reader of the feed outside its package
BRIEF = APP / "services" / "brief"
SCRIPT = BACKEND / "scripts" / "snapshot_company_feed.py"


def _app_sources_outside_the_package() -> list[Path]:
    return [
        path for path in APP.rglob("*.py")
        if "__pycache__" not in path.parts and PACKAGE not in path.parents and path not in OWN_FILES
    ]


def test_no_module_outside_the_package_references_the_company_feed():
    """Scenario: No other caller."""
    offenders = [
        str(path.relative_to(BACKEND)) for path in _app_sources_outside_the_package()
        if path != ADAPTER and "company_feed" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_the_news_agent_and_the_debate_runner_do_not_know_the_log():
    for name in ("news_feeds.py", "news.py", "runner.py", "engine.py"):
        assert "company_feed" not in (APP / "services" / "debate" / name).read_text(encoding="utf-8"), name


def test_no_route_reads_the_log():
    """Scenario: No route exposes the log."""
    from app.main import app

    paths = [getattr(route, "path", "") for route in app.routes]
    endpoint_modules = {getattr(getattr(route, "endpoint", None), "__module__", "") for route in app.routes}

    assert not any("company" in path or "snapshot" in path for path in paths)
    assert not any(module.startswith("app.services.company_feed") for module in endpoint_modules)


def test_no_post_run_hook_is_the_snapshot():
    import app.main  # noqa: F401  registers the debate hooks

    assert not any(getattr(hook, "__module__", "").startswith("app.services.company_feed") for hook in runner._hooks)


def test_no_startup_or_background_task_starts_it():
    main_source = (APP / "main.py").read_text(encoding="utf-8")

    assert "snapshot" not in main_source and "company_feed" not in main_source


def test_only_the_adapter_and_the_script_import_the_package_outside_it():
    """Scenario: No other caller / A second brief file references the feed. An exact list, not a prefix."""
    importers = sorted(
        str(path.relative_to(BACKEND))
        for path in BACKEND.rglob("*.py")
        if ".venv" not in path.parts and "__pycache__" not in path.parts and "tests" not in path.parts
        and PACKAGE not in path.parents and path not in OWN_FILES
        and "services.company_feed" in path.read_text(encoding="utf-8")
    )

    assert importers == ["app/services/brief/feed_source.py", "scripts/snapshot_company_feed.py"]


def test_the_log_file_is_gitignored():
    """`company-feed`: "The file SHALL be gitignored"; asked of git itself, not read from a pattern."""
    shipped = BACKEND / "data" / "company_feed_log.db"

    result = subprocess.run(["git", "check-ignore", "-q", str(shipped)], cwd=BACKEND, capture_output=True, timeout=30)

    assert result.returncode == 0
    assert company_feed_log.COMPANY_FEED_LOG_DB_PATH != shipped  # tests are redirected to a temporary file


# --- the weekly brief's adapter (`add-dividend-and-ex-date-lines`) -------------------------------------


def _brief_sources() -> list[Path]:
    return [path for path in BRIEF.rglob("*.py") if "__pycache__" not in path.parts]


def _imports_from_the_package(path: Path) -> list[str]:
    import ast

    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and "company_feed" in (node.module or ""):
            names += [f"{node.module}.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Import):
            names += [alias.name for alias in node.names if "company_feed" in alias.name]
    return names


def test_the_adapter_imports_the_store_module_of_the_feed_and_nothing_else_of_it():
    assert ADAPTER.exists()

    assert _imports_from_the_package(ADAPTER) == ["app.services.company_feed.store"]


def test_no_brief_file_but_the_adapter_names_the_feed_and_none_can_start_a_process():
    """The brief never runs the snapshot: no `subprocess`, no `os.system`, no lowercase word `snapshot`
    (the class name `FeedSnapshot` is not that word) outside the adapter's command text."""
    import re

    forbidden = re.compile(r"subprocess|os\.system|\bsnapshot\b")
    named = [p.name for p in _brief_sources() if p != ADAPTER and "company_feed" in p.read_text(encoding="utf-8")]
    starters = [p.name for p in _brief_sources() if forbidden.search(p.read_text(encoding="utf-8"))]
    script = (BACKEND / "scripts" / "weekly_brief.py").read_text(encoding="utf-8")

    assert named == []
    assert starters == [] or starters == ["feed_source.py"]
    assert "company_feed" not in script and forbidden.search(script) is None


_PROBE = """
import json, sys
sys.path.insert(0, {backend!r})
import {module}
watched = ["app.services.company_feed.fetch", "app.services.company_feed.snapshot", "vnstock"]
print(json.dumps(sorted(m for m in sys.modules if any(m == w or m.startswith(w + ".") for w in watched))))
"""


def _loaded_after_importing(module: str) -> list[str]:
    import json
    import sys

    result = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE.format(backend=str(BACKEND), module=module)],
        capture_output=True, text=True, timeout=120, cwd="/",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_importing_the_brief_cannot_load_the_fetch_or_the_snapshot_modules():
    """Scenario: The brief cannot start a snapshot. (`vnstock` is loaded by the brief's own price refresh, N1.)"""
    loaded = _loaded_after_importing("app.services.brief.run")

    assert [m for m in loaded if m.startswith("app.services.company_feed")] == []


def test_importing_the_adapter_alone_loads_neither_the_fetch_nor_the_snapshot_nor_the_vendor_library():
    assert _loaded_after_importing("app.services.brief.feed_source") == []


def test_the_probe_is_live():
    loaded = _loaded_after_importing("app.services.company_feed.snapshot")

    assert any(m.startswith("app.services.company_feed") for m in loaded)


def test_the_adapter_uses_only_the_read_helpers_and_constants_of_the_store_module():
    """No writer (`record_fetch`, `open_log_for_write`) is reachable through the `store` handle by name."""
    import ast

    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    used = {
        node.attr for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "store"
    }

    assert used and used <= {"last_fetch", "latest_items", "StoredItem", "STATUS_RATE_LIMITED", "STATUS_ERROR"}
