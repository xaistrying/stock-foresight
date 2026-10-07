"""Write one scoreable row per debate run (`debate-outcome-log`).

Stores stances, the band, guards, provenance and the agents' own evidence, so a
verdict and the displayed band can be scored once five sessions have passed. It
stores no reasoning text, no headline text and no credentials (design Decisions
3-4), and makes no network call: evidence is what the agents handed over.

`log_debate_run` raises on any problem; the caller decides it must not fail the
response and must not be silent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.db import debate_log
from app.db.connection import get_connection
from app.ml.volatility import MODEL_PATH
from app.services.debate.engine import AGENT_ORDER, AgentPosition, DebateResult
from app.services.debate.llm_client import LLMClient

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
GIT_TIMEOUT_SECONDS = 2

_STANCE_COLUMNS = tuple(f"r{n}_{agent}" for n in (1, 2) for agent in AGENT_ORDER)
_COLUMNS = (
    "ticker", "as_of", "run_at", "close_at_asof", "data_age_sessions", "eligible",
    "eligibility_reasons", "agents_degraded", "sigma_daily_pct", "range_5s_pct",
    "range_k", "range_coverage", *_STANCE_COLUMNS, "verdict", "agreement_level",
    "model_sha256", "llm_provider", "llm_model", "llm_effort", "code_rev", "evidence",
)
INSERT_DEBATE_LOG = (
    f"INSERT INTO debate_log ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join(':' + c for c in _COLUMNS)})"
)


@lru_cache(maxsize=1)
def _resolve_code_rev() -> str:
    """Short git revision, `+dirty` with uncommitted changes. Raises if git does not answer."""
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=GIT_TIMEOUT_SECONDS, check=True,
        ).stdout.strip()

    return git("rev-parse", "--short", "HEAD") + ("+dirty" if git("status", "--porcelain") else "")


def _code_rev() -> str | None:
    """Prompts and gates are changing, so rows from different code are not comparable without
    this. Resolved once per process on success; a failure is NOT cached (NULL, warned each time)
    so one slow git call does not blank the provenance of every later row."""
    try:
        return _resolve_code_rev()
    except (OSError, subprocess.SubprocessError):
        logger.warning("code_rev unavailable: git did not answer", exc_info=True)
        return None


def _model_sha256() -> str | None:
    try:
        return hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _close_at(ticker: str, as_of: str) -> float | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT close FROM ohlcv WHERE ticker = ? AND date = ?", (ticker, as_of)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _stance(position: AgentPosition | None) -> str | None:
    """A degraded agent's stance is a placeholder that never voted: not logged."""
    if position is None or position.degraded_reason is not None:
        return None
    return position.stance


def _evidence(result: DebateResult) -> dict:
    return {a: (result.round1[a].evidence if a in result.round1 else None) or {} for a in AGENT_ORDER}


def build_row(result: DebateResult) -> dict:
    # `as_of` is the features-row date. The engine's own `as_of` can fall back to
    # today when the technical agent did not finish, so it is never used here.
    if not result.data_as_of:
        raise ValueError(f"data_as_of missing for {result.ticker}: refusing to log a run without a data date")
    evidence = _evidence(result)
    llm = LLMClient()
    row = {
        "ticker": result.ticker,
        "as_of": result.data_as_of,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "close_at_asof": _close_at(result.ticker, result.data_as_of),
        "data_age_sessions": result.data_age_sessions,
        "eligible": int(bool(result.eligibility.get("eligible"))),
        "eligibility_reasons": json.dumps(list(result.eligibility.get("reasons", []))),
        "agents_degraded": json.dumps(list(result.agents_degraded)),
        "sigma_daily_pct": result.sigma_daily_pct,
        "range_5s_pct": result.range_5s_pct,
        "range_k": evidence["technical"].get("range_k"),
        "range_coverage": result.range_coverage,
        "verdict": result.verdict,
        "agreement_level": result.agreement_level,
        "model_sha256": _model_sha256(),
        "llm_provider": llm.provider,
        "llm_model": llm.model,
        "llm_effort": llm.effort if llm.provider == "claude_cli" else None,
        "code_rev": _code_rev(),
        "evidence": json.dumps(evidence),
    }
    for n, positions in ((1, result.round1), (2, result.round2)):
        for agent in AGENT_ORDER:
            row[f"r{n}_{agent}"] = _stance(positions.get(agent))
    return row


def log_debate_run(result: DebateResult) -> int:
    """Insert one row for this run and return its id. Raises on any problem."""
    row = build_row(result)  # everything that can fail before the file is touched
    conn = debate_log.get_debate_log_connection()
    try:
        debate_log.init_debate_log_db(conn)
        with conn:
            return conn.execute(INSERT_DEBATE_LOG, row).lastrowid
    finally:
        conn.close()
