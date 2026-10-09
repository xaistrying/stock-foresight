"""The vote — maps the agents' stances to a verdict and an agreement level.

Deterministic: a pure function of the live agents' stances. It makes no language-model
call (not even to abstain) and returns no prose; the key-tension and summary calls and
the prompts that carried the vote to a model no longer exist.

Verdict mapping (design.md Decision 2):
    3/3 bull  → STRONG_BUY_SIGNAL  / unanimous
    2/3 bull  → BUY_SIGNAL         / majority
    3/3 neutral → OBSERVE          / unanimous
    2 neutral + 1 directional → OBSERVE / majority
    1 bull + 1 neutral + 1 bear → SPLIT / split
    2/3 bear  → CAUTION_SIGNAL     / majority
    3/3 bear  → STRONG_CAUTION_SIGNAL / unanimous

A degraded agent (degraded_reason set) never votes. Two live agents agree →
BUY_SIGNAL / CAUTION_SIGNAL / OBSERVE with `majority` (never STRONG_*, never
`unanimous`); two live disagree → SPLIT; fewer than two → INSUFFICIENT_DATA / none
(debate-data-guards, design Decision 4).

Rule 6: the enum values are the API contract; display labels are non-transactional and
live in export.py and the panel.
"""

from __future__ import annotations

from app.services.debate.engine import AGENT_ORDER, AgentPosition, AgreementLevel, Verdict


def _map_verdict(stances: list[str]) -> tuple[Verdict, AgreementLevel]:
    """Deterministic mapping from three stance strings to verdict + agreement."""
    bulls = stances.count("bull")
    bears = stances.count("bear")
    neutrals = stances.count("neutral")

    if bulls == 3:
        return "STRONG_BUY_SIGNAL", "unanimous"
    if bears == 3:
        return "STRONG_CAUTION_SIGNAL", "unanimous"
    if neutrals == 3:
        return "OBSERVE", "unanimous"

    if bulls == 2:
        return "BUY_SIGNAL", "majority"
    if bears == 2:
        return "CAUTION_SIGNAL", "majority"

    # Remaining cases involve no 2-of-a-kind directional stance
    if neutrals == 2:
        # 2 neutral + 1 directional → OBSERVE (directional insufficient)
        return "OBSERVE", "majority"

    # 1 bull + 1 bear + 1 neutral  OR  any other 1-1-1 split
    return "SPLIT", "split"


_TWO_LIVE_AGREE: dict[str, Verdict] = {
    "bull": "BUY_SIGNAL", "bear": "CAUTION_SIGNAL", "neutral": "OBSERVE",
}


def _vote(stances: list[str]) -> tuple[Verdict, AgreementLevel]:
    """Verdict over the LIVE agents' stances (a degraded agent never votes).

    Three live: the existing mapping. Two live: agreement is `majority` at most
    (a strong or unanimous verdict needs three agreeing agents); disagreement is
    a SPLIT. Fewer than two: abstain.
    """
    if len(stances) == 3:
        return _map_verdict(stances)
    if len(stances) == 2:
        first, second = stances
        return (_TWO_LIVE_AGREE[first], "majority") if first == second else ("SPLIT", "split")
    return "INSUFFICIENT_DATA", "none"


def vote(positions: dict[str, AgentPosition]) -> tuple[Verdict, AgreementLevel]:
    """The verdict and agreement level over `positions` (the agents' only round), in AGENT_ORDER.

    An agent with a `degraded_reason` is excluded, never counted as neutral.
    """
    live = [positions[agent].stance for agent in AGENT_ORDER if positions[agent].degraded_reason is None]
    return _vote(live)
