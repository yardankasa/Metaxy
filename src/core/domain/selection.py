from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    """A member becomes healthy only after `success_threshold` successes in a row,
    and unhealthy only after `fail_threshold` failures in a row.

    The preferred member changes when a healthier candidate leads by at least
    `score_switch_margin` for `switch_hold_sweeps` consecutive sweeps. A margin
    of 0 follows the current leader on every sweep.
    """

    fail_threshold: int = 2
    success_threshold: int = 1
    score_switch_margin: float = 0.05
    switch_hold_sweeps: int = 1


@dataclass(frozen=True, slots=True)
class RankedMember:
    proxy_id: str
    healthy: bool
    score: float
    latency_ms: float | None


@dataclass(frozen=True, slots=True)
class SelectionState:
    preferred_id: str | None = None
    pending_id: str | None = None
    pending_sweeps: int = 0


def apply_streak(
    *,
    healthy: bool,
    consecutive_success: int,
    consecutive_fail: int,
    success: bool,
    policy: SelectionPolicy,
) -> tuple[bool, int, int]:
    if success:
        consecutive_success += 1
        consecutive_fail = 0
        if consecutive_success >= policy.success_threshold:
            healthy = True
        return healthy, consecutive_success, consecutive_fail
    consecutive_fail += 1
    consecutive_success = 0
    if consecutive_fail >= policy.fail_threshold:
        healthy = False
    return healthy, consecutive_success, consecutive_fail


def choose_preferred(
    members: list[RankedMember],
    state: SelectionState,
    policy: SelectionPolicy,
) -> SelectionState:
    healthy = [member for member in members if member.healthy]
    healthy.sort(
        key=lambda member: (
            -member.score,
            member.latency_ms if member.latency_ms is not None else 1e18,
            member.proxy_id,
        )
    )
    if not healthy:
        preferred = state.preferred_id
        still = next((member for member in members if member.proxy_id == preferred and member.healthy), None)
        if still is None:
            preferred = None
        return SelectionState(preferred_id=preferred)

    best = healthy[0]
    current = next((member for member in healthy if member.proxy_id == state.preferred_id), None)
    margin = policy.score_switch_margin
    hold = max(1, policy.switch_hold_sweeps)
    if margin <= 0 or current is None:
        return SelectionState(preferred_id=best.proxy_id)
    lead = best.score - current.score
    if best.proxy_id != current.proxy_id and lead >= margin:
        pending = state.pending_sweeps + 1 if state.pending_id == best.proxy_id else 1
        if pending >= hold:
            return SelectionState(preferred_id=best.proxy_id)
        return SelectionState(preferred_id=current.proxy_id, pending_id=best.proxy_id, pending_sweeps=pending)
    return SelectionState(preferred_id=current.proxy_id)


def healthy_order(members: list[RankedMember], preferred_id: str | None) -> list[str]:
    healthy = [member for member in members if member.healthy]
    healthy.sort(
        key=lambda member: (
            0 if member.proxy_id == preferred_id else 1,
            -member.score,
            member.proxy_id,
        )
    )
    return [member.proxy_id for member in healthy]
