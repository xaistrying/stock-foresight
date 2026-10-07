"""Install the vnstock/vnai guard before any test module is imported.

pytest imports `conftest.py` ahead of the test modules it collects, so this is
the earliest hook available — and it has to be earlier than
`test_ticker_ingestion.py`'s own top-level `from vnstock.core.exceptions
import RateLimitError`, which would otherwise trigger vnai's AI-config writes
during collection. That is exactly how the issue in `docs/KNOWN_ISSUES.md` was
originally found: `AGENTS.md` reappearing after every `pytest backend/tests`.
"""

from app.vnstock_guard import install as _install_vnstock_guard

_install_vnstock_guard()


import pytest  # noqa: E402

from app.db import debate_log as _debate_log  # noqa: E402


@pytest.fixture(autouse=True)
def _valid_debate_configuration(monkeypatch):
    """The debate endpoint checks its configuration before it runs (`harden-debate-runtime`).

    Every test starts from a valid, fake OpenAI setup whatever backend/.env says, so no
    test depends on the developer's own settings; a test that wants an invalid one sets
    it itself. The key is a placeholder: nothing here can reach a provider.
    """
    for name in (
        "DEBATE_LLM_EFFORT", "DEBATE_MAX_TOKENS_PER_CALL", "DEBATE_LLM_CALL_TIMEOUT_SECONDS",
        "DEBATE_RUN_TIMEOUT_SECONDS", "DEBATE_MAX_CONCURRENT_RUNS", "DEBATE_POST_RUN_HOOK_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEBATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder-not-a-real-key")


@pytest.fixture(autouse=True)
def _fresh_run_registry(monkeypatch):
    """The runner's in-flight registry is process-global: a test that fails mid-run must not leave a
    phantom run (a join or a 429) for the next one."""
    from app.services.debate import runner

    monkeypatch.setattr(runner, "_runs", {})


@pytest.fixture(autouse=True)
def _temporary_debate_log(tmp_path_factory, monkeypatch):
    """No test may create or write the real `backend/data/debate_log.db`.

    Every test that reaches the debate endpoint (including the `TestClient(app)`
    lifespan) would otherwise insert fake rows into the owner's irreplaceable log.
    """
    monkeypatch.setattr(_debate_log, "DEBATE_LOG_DB_PATH", tmp_path_factory.mktemp("debate_log") / "debate_log.db")
