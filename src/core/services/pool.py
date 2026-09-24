from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.check import CheckApply, SuccessRates
from core.domain.proxy import Proxy
from core.domain.score import ScoringPolicy, compute_score
from core.domain.selection import (
    RankedMember,
    SelectionPolicy,
    SelectionState,
    apply_streak,
    choose_preferred,
    healthy_order,
)


@dataclass
class MemberState:
    proxy: Proxy
    healthy: bool = False
    consecutive_success: int = 0
    consecutive_fail: int = 0
    last_latency_ms: float | None = None
    last_status: int | None = None
    last_error: str | None = None
    last_checked_at: float | None = None
    score: float = 0.0
    rates: SuccessRates = field(default_factory=SuccessRates)


class Pool:
    def __init__(
        self,
        proxies: list[Proxy],
        *,
        scoring: ScoringPolicy | None = None,
        selection: SelectionPolicy | None = None,
    ) -> None:
        self._members: dict[str, MemberState] = {proxy.id: MemberState(proxy=proxy) for proxy in proxies}
        self._scoring = scoring or ScoringPolicy()
        self._selection = selection or SelectionPolicy()
        self._choice = SelectionState()
        self.last_sweep_at: float | None = None
        self.last_sweep_seconds: float | None = None
        self.sweep_in_progress: bool = False

    def get(self, proxy_id: str) -> MemberState | None:
        return self._members.get(proxy_id)

    def members(self) -> list[MemberState]:
        return list(self._members.values())

    def proxies(self) -> list[Proxy]:
        return [member.proxy for member in self._members.values()]

    @property
    def total(self) -> int:
        return len(self._members)

    @property
    def healthy_count(self) -> int:
        return sum(1 for member in self._members.values() if member.healthy)

    @property
    def preferred_id(self) -> str | None:
        return self._choice.preferred_id

    def preferred(self) -> MemberState | None:
        if self._choice.preferred_id is None:
            return None
        return self._members.get(self._choice.preferred_id)

    def healthy_ranked(self) -> list[Proxy]:
        order = healthy_order(self._ranked(), self._choice.preferred_id)
        return [self._members[proxy_id].proxy for proxy_id in order]

    def apply_sweep(
        self,
        results: list[CheckApply],
        rates: dict[str, SuccessRates],
        *,
        sweep_at: float,
        duration_seconds: float,
    ) -> None:
        for result in results:
            self._apply_one(result)
        for proxy_id, member in self._members.items():
            stats = rates.get(proxy_id, SuccessRates())
            member.rates = stats
            member.score = compute_score(
                stats.success_1h,
                stats.success_24h,
                stats.success_7d,
                member.healthy,
                member.last_latency_ms,
                self._scoring,
            )
        self._choice = choose_preferred(self._ranked(), self._choice, self._selection)
        self.last_sweep_at = sweep_at
        self.last_sweep_seconds = duration_seconds

    def _apply_one(self, result: CheckApply) -> None:
        member = self._members.get(result.proxy_id)
        if member is None:
            return
        member.last_checked_at = result.checked_at
        member.last_latency_ms = result.latency_ms
        member.last_status = result.status_code
        member.last_error = result.error
        member.healthy, member.consecutive_success, member.consecutive_fail = apply_streak(
            healthy=member.healthy,
            consecutive_success=member.consecutive_success,
            consecutive_fail=member.consecutive_fail,
            success=result.success,
            policy=self._selection,
        )

    def _ranked(self) -> list[RankedMember]:
        return [
            RankedMember(
                proxy_id=member.proxy.id,
                healthy=member.healthy,
                score=member.score,
                latency_ms=member.last_latency_ms,
            )
            for member in self._members.values()
        ]
