"""Regression tests for the durable vnstock/vnai AI-config-write fix.

`docs/KNOWN_ISSUES.md` records that the original mitigation was an edit inside
the gitignored `backend/.venv`, silently lost on any venv rebuild. These tests
guard the tracked replacement: that the writers are actually neutralised, and
that no module in this repo imports `vnstock` without installing the guard
first — the failure mode that would quietly reintroduce the writes.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from app import vnstock_guard

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent

# Files that legitimately reference vnstock only in prose/assertions, not by
# importing it.
_IMPORT_RE = re.compile(r"^\s*(?:from\s+vnstock[\w.]*\s+import|import\s+vnstock)", re.M)
_GUARD_RE = re.compile(r"^\s*from\s+app\.vnstock_guard\s+import", re.M)


def _python_sources() -> list[Path]:
    return [
        path
        for path in BACKEND_ROOT.rglob("*.py")
        if ".venv" not in path.parts and "__pycache__" not in path.parts
    ]


def test_vnai_config_writers_are_neutralised():
    vnai = pytest.importorskip("vnai")
    import vnai.beam.agents

    assert vnstock_guard.install() is True
    for module, attribute in (
        (vnai, "setup_agent_environment"),
        (vnai, "async_setup_agent_environment"),
        (vnai.beam.agents, "setup_agent_environment"),
        (vnai.beam.agents, "async_setup_agent_environment"),
    ):
        assert getattr(module, attribute) is vnstock_guard._noop_setup_agent_environment, (
            f"{module.__name__}.{attribute} is not neutralised"
        )


def test_noop_writer_reports_failure_and_writes_nothing(tmp_path):
    assert vnstock_guard._noop_setup_agent_environment(str(tmp_path)) is False
    assert list(tmp_path.iterdir()) == []


def test_install_is_idempotent():
    assert vnstock_guard.install() is True
    assert vnstock_guard.install() is True


def test_install_reports_failure_when_no_writer_target_exists(monkeypatch):
    """tasks.md 5.6: the loop `continue`s past each missing target and used to
    fall through to an unconditional `return True`, claiming a clean install
    with nothing patched — contradicting the docstring and hiding exactly the
    scenario the guard exists to survive, a vnai upgrade that renames or
    drops the writers.
    """
    pytest.importorskip("vnai")
    import vnai.beam.agents  # noqa: F401  (must be in sys.modules to be found)

    monkeypatch.setattr(vnstock_guard, "_installed", False)
    monkeypatch.setattr(
        vnstock_guard,
        "_WRITER_TARGETS",
        (
            ("vnai.beam.agents", "renamed_by_an_upgrade"),
            ("vnai", "renamed_by_an_upgrade"),
        ),
    )

    assert vnstock_guard.install() is False
    # A failed install must not be memoised as done, so a later call retries.
    assert vnstock_guard._installed is False


def test_install_reports_success_when_only_some_targets_exist(monkeypatch):
    """A partially-renamed vnai still gets its surviving writers patched, and
    that is a real (if incomplete) suppression — the warning names the
    missing ones."""
    pytest.importorskip("vnai")
    import vnai.beam.agents  # noqa: F401

    monkeypatch.setattr(vnstock_guard, "_installed", False)
    monkeypatch.setattr(
        vnstock_guard,
        "_WRITER_TARGETS",
        (
            ("vnai.beam.agents", "setup_agent_environment"),
            ("vnai", "renamed_by_an_upgrade"),
        ),
    )

    assert vnstock_guard.install() is True


def test_every_vnstock_importer_installs_the_guard_first():
    """A new module that imports vnstock without the guard would silently
    reintroduce the AI-config writes. Catch it here rather than by noticing
    AGENTS.md reappearing again."""
    offenders = []
    for path in _python_sources():
        source = path.read_text(encoding="utf-8")
        vnstock_import = _IMPORT_RE.search(source)
        if vnstock_import is None:
            continue
        # conftest.py installs the guard for the whole test session, so a test
        # module's own vnstock import is already covered.
        if path.parent == BACKEND_ROOT / "tests":
            continue
        guard_import = _GUARD_RE.search(source)
        if guard_import is None or guard_import.start() > vnstock_import.start():
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], (
        "these modules import vnstock without installing app.vnstock_guard "
        f"first: {offenders}"
    )


def test_conftest_installs_the_guard_for_the_test_session():
    conftest = (BACKEND_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert _GUARD_RE.search(conftest) is not None


def test_importing_vnstock_writes_no_ai_config_files(tmp_path):
    """End-to-end against the real installed vnstock: a fresh interpreter that
    installs the guard, imports vnstock, and then calls `setup_agent` on its
    synchronous path leaves AGENTS.md and the six home-directory config paths
    untouched.

    `setup_agent(async_mode=False)` is called explicitly because vnstock's
    import-time call is async — a daemon thread that a short-lived process may
    exit before. The synchronous call exercises the same neutralised writer
    with no timing dependency. HOME and cwd are both redirected into tmp_path
    so a genuine regression cannot touch the developer's real config files.
    """
    pytest.importorskip("vnstock")
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    project = tmp_path / "project"
    project.mkdir()

    script = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "from app.vnstock_guard import install\n"
        "assert install() is True\n"
        "import vnstock\n"
        "assert vnstock.setup_agent(async_mode=False) is False\n"
    ) % str(BACKEND_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project,
        env={
            "HOME": str(fake_home),
            "PATH": "/usr/bin:/bin",
            "USERPROFILE": str(fake_home),
        },
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr

    written = {
        str(p.relative_to(tmp_path))
        for p in list(fake_home.rglob("*")) + list(project.rglob("*"))
        if p.is_file()
    }
    forbidden = {
        "project/AGENTS.md",
        "home/.clauderc",
        "home/.cursorrules",
        "home/.windsurfrules",
        "home/.clinerules",
        "home/.github/copilot-instructions.md",
        "home/.gemini/config/AGENTS.md",
    }
    assert written & forbidden == set(), (
        f"vnstock import wrote AI-config files: {sorted(written & forbidden)}"
    )
