from __future__ import annotations

import asyncio

from core.domain.proxy import proxy_from_endpoint
from core.domain.score import ScoringPolicy
from core.domain.selection import SelectionPolicy


def run(coro):
    return asyncio.run(coro)


def sample_proxy(host: str = "203.0.113.10", port: int = 8080, label: str = "docs"):
    return proxy_from_endpoint(host, port, label)


def scoring() -> ScoringPolicy:
    return ScoringPolicy(
        success_1h=0.30,
        success_24h=0.30,
        success_7d=0.15,
        healthy=0.15,
        latency=0.10,
        latency_ref_ms=2000,
    )


def selection(**overrides) -> SelectionPolicy:
    values = dict(fail_threshold=2, success_threshold=1, score_switch_margin=0.15, switch_hold_sweeps=2)
    values.update(overrides)
    return SelectionPolicy(**values)
