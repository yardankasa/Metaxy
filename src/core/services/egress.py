from __future__ import annotations

from dataclasses import dataclass

from core.domain.check import ProbeOutcome


@dataclass
class EgressStatus:
    enabled: bool = False
    ok: bool | None = None
    latency_ms: float | None = None
    status_code: int | None = None
    error: str | None = None
    checked_at: float | None = None
    via: str | None = None

    def observe(self, outcome: ProbeOutcome) -> None:
        self.ok = outcome.success
        self.latency_ms = outcome.latency_ms
        self.status_code = outcome.status_code
        self.error = outcome.error
        self.checked_at = outcome.checked_at
