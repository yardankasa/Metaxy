from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Series(StrEnum):
    POOL = "pool"
    EGRESS = "egress"


EGRESS_ID = "egress"


@dataclass(frozen=True, slots=True)
class CheckRecord:
    proxy_id: str
    series: str
    checked_at: float
    success: bool
    latency_ms: float | None
    status_code: int | None
    error: str | None


@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    success: bool
    latency_ms: float | None
    status_code: int | None
    error: str | None
    checked_at: float


@dataclass(frozen=True, slots=True)
class CheckApply:
    proxy_id: str
    success: bool
    latency_ms: float | None
    status_code: int | None
    error: str | None
    checked_at: float


@dataclass(frozen=True, slots=True)
class SuccessRates:
    window_24h_ok: int = 0
    window_24h_total: int = 0
    window_7d_ok: int = 0
    window_7d_total: int = 0
    window_1h_ok: int = 0
    window_1h_total: int = 0

    @property
    def success_1h(self) -> float:
        if self.window_1h_total <= 0:
            return 0.0
        return self.window_1h_ok / self.window_1h_total

    @property
    def success_24h(self) -> float:
        if self.window_24h_total <= 0:
            return 0.0
        return self.window_24h_ok / self.window_24h_total

    @property
    def success_7d(self) -> float:
        if self.window_7d_total <= 0:
            return 0.0
        return self.window_7d_ok / self.window_7d_total


@dataclass(frozen=True, slots=True)
class DailyRollup:
    proxy_id: str
    day: str
    success_count: int
    fail_count: int
    avg_latency_ms: float | None


@dataclass(frozen=True, slots=True)
class HourlyRollup:
    proxy_id: str
    hour: str
    success_count: int
    fail_count: int
    avg_latency_ms: float | None

    @property
    def success_rate(self) -> float | None:
        total = self.success_count + self.fail_count
        if total <= 0:
            return None
        return self.success_count / total
