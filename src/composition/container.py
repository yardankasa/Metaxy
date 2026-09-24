from __future__ import annotations

from pathlib import Path

from clients.http_prober import HttpProber
from clock.system_clock import SystemClock
from config.settings import Settings
from core.contracts.clock import Clock
from core.contracts.prober import Prober
from core.contracts.resources import Resources
from core.domain.score import ScoringPolicy
from core.domain.selection import SelectionPolicy
from core.services.egress import EgressStatus
from core.services.pool import Pool
from core.services.pressure import PressureGuard, PressurePolicy
from core.usecases.probe_egress import ProbeEgressService
from core.usecases.read_status import ReadStatusService
from core.usecases.sweep_pool import SweepPoolService
from inventory.yaml_file import load_inventory
from memory.check_store import InMemoryCheckStore
from persistence.check_store import SqliteCheckStore
from runtime.process import ProcessResources


class Container:
    """One composition root. Tests substitute the clock, the prober, or the resource probe."""

    def __init__(
        self,
        settings: Settings,
        *,
        root: Path | None = None,
        clock: Clock | None = None,
        prober: Prober | None = None,
        resources: Resources | None = None,
    ) -> None:
        self.settings = settings
        self.root = root or Path.cwd()
        self.clock = clock or SystemClock()
        self.resources = resources or ProcessResources()
        self.store_ready = False
        self._owns_prober = prober is None
        scoring = ScoringPolicy(
            success_1h=settings.scoring.weight_success_1h,
            success_24h=settings.scoring.weight_success_24h,
            success_7d=settings.scoring.weight_success_7d,
            healthy=settings.scoring.weight_healthy,
            latency=settings.scoring.weight_latency,
            latency_ref_ms=settings.scoring.latency_ref_ms,
        )
        selection = SelectionPolicy(
            fail_threshold=settings.selection.fail_threshold,
            success_threshold=settings.selection.success_threshold,
            score_switch_margin=settings.selection.score_switch_margin,
            switch_hold_sweeps=settings.selection.switch_hold_sweeps,
        )
        proxies = load_inventory(settings.inventory_file(self.root))
        self.pool = Pool(proxies, scoring=scoring, selection=selection)
        store_path = settings.store.path.strip()
        if store_path:
            self.store = SqliteCheckStore(settings.store_file(self.root), cache_kb=settings.store.cache_kb)
        else:
            self.store = InMemoryCheckStore()
        self.guard = PressureGuard(
            PressurePolicy(
                max_rss_mb=settings.memory.max_rss_mb,
                max_connections=settings.memory.max_connections,
            ),
            self.resources,
        )
        via = settings.egress.proxy_url.strip()
        self.egress = EgressStatus(enabled=bool(via), via=via or None)
        self._prober = prober or HttpProber(
            clock=self.clock,
            check_url=settings.check_url,
            expected_status=settings.expected_status,
            max_body_bytes=settings.memory.max_probe_body_bytes,
            concurrency=settings.pool.concurrency,
        )
        self.sweep = SweepPoolService(
            pool=self.pool,
            store=self.store,
            prober=self._prober,
            clock=self.clock,
            guard=self.guard,
            concurrency=settings.pool.concurrency,
            timeout_seconds=settings.pool.timeout_seconds,
            retain_days=settings.memory.checks_retain_days,
        )
        self.egress_probe = ProbeEgressService(
            status=self.egress,
            store=self.store,
            prober=self._prober,
            guard=self.guard,
            timeout_seconds=settings.egress.timeout_seconds,
        )
        self.status = ReadStatusService(pool=self.pool, egress=self.egress, store=self.store, clock=self.clock)

    async def startup(self) -> None:
        limit = max(0, self.settings.memory.hard_limit_mb) * 1024 * 1024
        self.resources.apply_address_space_limit(limit)
        await self.store.open()
        self.store_ready = True

    async def shutdown(self) -> None:
        self.store_ready = False
        await self.store.close()
        if self._owns_prober:
            await self._prober.aclose()
