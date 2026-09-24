from __future__ import annotations

from dataclasses import dataclass

from core.contracts.check_store import CheckStore
from core.contracts.clock import Clock
from core.contracts.prober import Prober
from core.domain.check import CheckApply, CheckRecord, Series
from core.services.pool import Pool
from core.services.pressure import PressureGuard


@dataclass(frozen=True, slots=True)
class SweepResult:
    probed: int
    skipped_reason: str | None = None


class SweepPoolService:
    def __init__(
        self,
        *,
        pool: Pool,
        store: CheckStore,
        prober: Prober,
        clock: Clock,
        guard: PressureGuard,
        concurrency: int,
        timeout_seconds: float,
        retain_days: int,
    ) -> None:
        self._pool = pool
        self._store = store
        self._prober = prober
        self._clock = clock
        self._guard = guard
        self._concurrency = max(1, concurrency)
        self._timeout_seconds = timeout_seconds
        self._retain_days = retain_days

    async def execute(self) -> SweepResult:
        if self._guard.over_limit():
            return SweepResult(probed=0, skipped_reason="memory_pressure")
        proxies = self._pool.proxies()
        self._pool.sweep_in_progress = True
        started = self._clock.monotonic()
        try:
            outcomes = await self._probe_all(proxies)
            records = [
                CheckRecord(
                    proxy_id=proxy.id,
                    series=Series.POOL,
                    checked_at=outcome.checked_at,
                    success=outcome.success,
                    latency_ms=outcome.latency_ms,
                    status_code=outcome.status_code,
                    error=outcome.error,
                )
                for proxy, outcome in zip(proxies, outcomes, strict=True)
            ]
            await self._store.record(records)
            now = self._clock.now()
            rates = await self._store.success_rates([proxy.id for proxy in proxies], now=now, series=Series.POOL)
            applies = [
                CheckApply(
                    proxy_id=proxy.id,
                    success=outcome.success,
                    latency_ms=outcome.latency_ms,
                    status_code=outcome.status_code,
                    error=outcome.error,
                    checked_at=outcome.checked_at,
                )
                for proxy, outcome in zip(proxies, outcomes, strict=True)
            ]
            self._pool.apply_sweep(
                applies,
                rates,
                sweep_at=now,
                duration_seconds=round(self._clock.monotonic() - started, 3),
            )
            await self._store.rebuild_rollups(now=now, days=7, hours=48, series=Series.POOL)
            await self._store.prune(now=now, retain_days=self._retain_days)
            return SweepResult(probed=len(proxies))
        finally:
            self._pool.sweep_in_progress = False

    async def _probe_all(self, proxies):
        import asyncio

        semaphore = asyncio.Semaphore(self._concurrency)

        async def one(proxy):
            async with semaphore:
                return await self._prober.probe(proxy.url, timeout_seconds=self._timeout_seconds)

        return await asyncio.gather(*(one(proxy) for proxy in proxies))
