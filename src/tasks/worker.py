from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger(__name__)


async def run_worker(container, stop: asyncio.Event) -> None:
    await asyncio.gather(
        _loop(stop, container.settings.pool.sweep_interval_seconds, container.sweep.execute, "sweep"),
        _loop(stop, container.settings.egress.interval_seconds, container.egress_probe.execute, "egress"),
        _memory(container, stop),
    )


async def _loop(stop: asyncio.Event, interval: float, call, name: str) -> None:
    while not stop.is_set():
        try:
            result = await call()
            logger.info(
                "cycle",
                task=name,
                probed=getattr(result, "probed", None),
                skipped=getattr(result, "skipped_reason", None),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("cycle_failed", task=name)
        try:
            await asyncio.wait_for(stop.wait(), timeout=max(0.1, interval))
        except TimeoutError:
            continue


async def _memory(container, stop: asyncio.Event) -> None:
    over = False
    interval = container.settings.memory.check_interval_seconds
    while not stop.is_set():
        pressured = container.guard.over_limit()
        if pressured and not over:
            logger.warning("memory_pressure")
        elif over and not pressured:
            logger.info("memory_recovered")
        over = pressured
        try:
            await asyncio.wait_for(stop.wait(), timeout=max(1.0, interval))
        except TimeoutError:
            continue
