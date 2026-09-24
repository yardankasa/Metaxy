from __future__ import annotations

from dataclasses import dataclass

from core.contracts.check_store import CheckStore
from core.contracts.prober import Prober
from core.domain.check import EGRESS_ID, CheckRecord, Series
from core.services.egress import EgressStatus
from core.services.pressure import PressureGuard


@dataclass(frozen=True, slots=True)
class EgressResult:
    probed: bool
    skipped_reason: str | None = None


class ProbeEgressService:
    def __init__(
        self,
        *,
        status: EgressStatus,
        store: CheckStore,
        prober: Prober,
        guard: PressureGuard,
        timeout_seconds: float,
    ) -> None:
        self._status = status
        self._store = store
        self._prober = prober
        self._guard = guard
        self._timeout_seconds = timeout_seconds

    async def execute(self) -> EgressResult:
        if not self._status.enabled or not self._status.via:
            return EgressResult(probed=False, skipped_reason="disabled")
        if self._guard.over_limit():
            return EgressResult(probed=False, skipped_reason="memory_pressure")
        outcome = await self._prober.probe(self._status.via, timeout_seconds=self._timeout_seconds)
        self._status.observe(outcome)
        await self._store.record(
            [
                CheckRecord(
                    proxy_id=EGRESS_ID,
                    series=Series.EGRESS,
                    checked_at=outcome.checked_at,
                    success=outcome.success,
                    latency_ms=outcome.latency_ms,
                    status_code=outcome.status_code,
                    error=outcome.error,
                )
            ]
        )
        return EgressResult(probed=True)
