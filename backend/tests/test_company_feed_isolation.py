"""The company feed is started only by hand and read by nothing else (`company-feed`: "The snapshot runs
only by hand"; "No route exposes the log"; "News agent unchanged").
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
        if "company_feed" in path.read_text(encoding="utf-8")
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


def test_only_the_script_and_the_tests_import_the_package_outside_it():
    importers = sorted(
        str(path.relative_to(BACKEND))
        for path in BACKEND.rglob("*.py")
        if ".venv" not in path.parts and "__pycache__" not in path.parts and "tests" not in path.parts
        and PACKAGE not in path.parents and path not in OWN_FILES
        and "services.company_feed" in path.read_text(encoding="utf-8")
    )

    assert importers == ["scripts/snapshot_company_feed.py"]


def test_the_log_file_is_gitignored():
    """`company-feed`: "The file SHALL be gitignored"; asked of git itself, not read from a pattern."""
    shipped = BACKEND / "data" / "company_feed_log.db"

    result = subprocess.run(["git", "check-ignore", "-q", str(shipped)], cwd=BACKEND, capture_output=True, timeout=30)

    assert result.returncode == 0
    assert company_feed_log.COMPANY_FEED_LOG_DB_PATH != shipped  # tests are redirected to a temporary file
