from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScoringPolicy:
    """Weights are expected to sum to 1. The score is their weighted sum, rounded to 6 decimals.

    Latency is milliseconds because `latency_ref_ms` is the budget the ratio is taken against.
    A probe slower than that budget contributes nothing; a missing latency contributes nothing.
    """

    success_1h: float = 0.35
    success_24h: float = 0.20
    success_7d: float = 0.15
    healthy: float = 0.10
    latency: float = 0.20
    latency_ref_ms: float = 2000.0


def clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def latency_score(latency_ms: float | None, ref_ms: float) -> float:
    if latency_ms is None or ref_ms <= 0:
        return 0.0
    return clamp_unit(1.0 - (latency_ms / ref_ms))


def compute_score(
    success_1h: float,
    success_24h: float,
    success_7d: float,
    currently_healthy: bool,
    latency_ms: float | None,
    policy: ScoringPolicy | None = None,
) -> float:
    weights = policy or ScoringPolicy()
    healthy = 1.0 if currently_healthy else 0.0
    total = (
        weights.success_1h * clamp_unit(success_1h)
        + weights.success_24h * clamp_unit(success_24h)
        + weights.success_7d * clamp_unit(success_7d)
        + weights.healthy * healthy
        + weights.latency * latency_score(latency_ms, weights.latency_ref_ms)
    )
    return round(total, 6)
