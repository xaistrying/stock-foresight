"""Which company feed modules may touch the vendor library (`company-feed`: "Vendor access goes
through the guard, from one module"; "The company feed makes no model call").
"""

from __future__ import annotations

import subprocess
import sys

from . import test_vnstock_guard as guard

PACKAGE = guard.BACKEND_ROOT / "app" / "services" / "company_feed"
SCRIPT = guard.BACKEND_ROOT / "scripts" / "snapshot_company_feed.py"


def test_the_repository_guard_test_stays_green_and_scans_the_fetch_module():
    """Scenario: The repository guard test stays green."""
    guard.test_every_vnstock_importer_installs_the_guard_first()

    fetch_source = (PACKAGE / "fetch.py").read_text(encoding="utf-8")
    vnstock_import = guard._IMPORT_RE.search(fetch_source)
    guard_import = guard._GUARD_RE.search(fetch_source)
    assert PACKAGE / "fetch.py" in guard._python_sources()
    assert vnstock_import and guard_import and guard_import.start() < vnstock_import.start()


def test_only_the_fetch_module_imports_the_vendor():
    """Scenario: Only the fetch module imports the vendor."""
    importers = sorted(
        path.name for path in PACKAGE.glob("*.py") if guard._IMPORT_RE.search(path.read_text(encoding="utf-8"))
    )

    assert importers == ["fetch.py"]


def test_the_script_does_not_import_the_vendor_directly():
    if SCRIPT.exists():
        assert not guard._IMPORT_RE.search(SCRIPT.read_text(encoding="utf-8"))


def test_pure_modules_import_with_the_vendor_blocked_and_with_no_model_client():
    """Scenario: Pure modules do not need the vendor; Scenario: No model client is used (import half)."""
    script = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "for name in ('vnstock', 'vnai', 'vnstock_data'):\n"
        "    sys.modules[name] = None\n"
        "import app.services.company_feed.normalise\n"
        "import app.services.company_feed.store\n"
        "import app.db.company_feed_log\n"
        "loaded = sorted(m for m in sys.modules if m.startswith(('openai', 'anthropic')) or m.endswith('llm_client'))\n"
        "assert loaded == [], loaded\n"
    ) % str(guard.BACKEND_ROOT)

    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stderr


def test_a_blocked_vendor_really_fails_an_import_in_that_subprocess(tmp_path):
    """The control for the test above: the block is effective, so its success means something."""
    script = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "sys.modules['vnstock'] = None\n"
        "import app.services.company_feed.fetch\n"
    ) % str(guard.BACKEND_ROOT)

    # HOME and cwd are redirected: importing vnai (the guard does) creates files in the home directory.
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120, cwd=tmp_path,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "USERPROFILE": str(tmp_path)},
    )

    assert result.returncode != 0 and "vnstock" in result.stderr
