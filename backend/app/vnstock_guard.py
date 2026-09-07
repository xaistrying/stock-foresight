"""Durable neutralisation of vnstock/vnai's automatic AI-config file writing.

`vnstock/__init__.py` calls `setup_agent(async_mode=True)` unconditionally at
module level, so every `import vnstock` — including transitive imports from
this app's own code and tests — reaches
`vnai.beam.agents.setup_agent_environment`, which writes prompt-injection-style
content into this repo's `AGENTS.md` and into six global AI-tool config files
in the user's home directory. Full account: `docs/KNOWN_ISSUES.md`.

The previous mitigation edited the installed package inside `backend/.venv`,
which is gitignored and silently lost on any venv rebuild or `vnstock`
upgrade. This module is the durable replacement: it lives in tracked source
and neutralises the writer functions in memory, so nothing outside the process
is ever touched and no install-time step has to be remembered.

`install()` must run *before* `vnstock` is first imported — the write happens
during vnstock's own module body. Every module in this repo that imports
`vnstock` therefore calls `install()` above that import; the ordering is
enforced by `backend/tests/test_vnstock_guard.py`.
"""

import logging
import sys

logger = logging.getLogger(__name__)

# (module path, attribute) pairs replaced with no-ops. `vnai.beam.agents` holds
# the real implementations; `vnai` re-exports them, and
# `vnstock.core.utils.agents.init_agent_environment` resolves them by
# `from vnai import ...` at call time — so both surfaces need patching.
_WRITER_TARGETS = (
    ("vnai.beam.agents", "setup_agent_environment"),
    ("vnai.beam.agents", "async_setup_agent_environment"),
    ("vnai", "setup_agent_environment"),
    ("vnai", "async_setup_agent_environment"),
)

_installed = False


def _noop_setup_agent_environment(project_root: str = ".") -> bool:
    """Stand-in for vnai's config-file writers. Reports failure to write,
    which is what actually happened, and is a return value vnstock already
    handles (its own wrapper swallows a False)."""
    logger.debug("Suppressed vnai agent-environment write for %r", project_root)
    return False


def install() -> bool:
    """Replace vnai's AI-config writers with no-ops.

    Returns True if the writers are neutralised (or vnai is absent and there
    is nothing to neutralise), False if vnai is installed but could not be
    patched — in which case the caller's `import vnstock` may still write.
    Idempotent.
    """
    global _installed
    if _installed:
        return True

    if "vnstock" in sys.modules:
        logger.warning(
            "vnstock was imported before vnstock_guard.install(); any "
            "AI-config files it wrote on import were not prevented"
        )

    try:
        import vnai  # noqa: F401  (imported for its side-effect-free module object)
        import vnai.beam.agents  # noqa: F401
    except ImportError:
        # vnai absent means vnstock cannot reach the writers at all.
        _installed = True
        return True
    except Exception:
        logger.exception("Could not import vnai to neutralise its config writers")
        return False

    patched_any = False
    for module_path, attribute in _WRITER_TARGETS:
        module = sys.modules.get(module_path)
        if module is None or not hasattr(module, attribute):
            # Upstream renamed or dropped it; nothing to suppress here, but say
            # so rather than reporting a clean install we did not achieve.
            logger.warning(
                "Expected vnai writer %s.%s not found — vnstock's import-time "
                "AI-config writing may no longer be suppressed",
                module_path, attribute,
            )
            continue
        setattr(module, attribute, _noop_setup_agent_environment)
        patched_any = True

    if not patched_any:
        # Every target was missing — report the failure rather than the
        # unconditional True this used to return, which claimed a clean
        # install when nothing was actually patched. Not marking
        # `_installed` lets a later call retry, matching the ImportError
        # branch above.
        logger.error(
            "vnai is installed but none of its known writer targets were "
            "found — vnstock's import-time AI-config writing is NOT "
            "suppressed"
        )
        return False

    _installed = True
    return True
