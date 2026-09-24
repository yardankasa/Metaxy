from __future__ import annotations

from dataclasses import dataclass

from core.contracts.resources import Resources


@dataclass(frozen=True, slots=True)
class PressurePolicy:
    max_rss_mb: int = 384
    max_connections: int = 64

    @property
    def max_rss_bytes(self) -> int:
        return max(0, self.max_rss_mb) * 1024 * 1024


class PressureGuard:
    """Soft RSS and connection caps. Crossing the RSS cap refuses new work
    instead of waiting for the host to kill the process.
    """

    def __init__(self, policy: PressurePolicy, resources: Resources) -> None:
        self._policy = policy
        self._resources = resources
        self._active = 0

    @property
    def active_connections(self) -> int:
        return self._active

    def over_limit(self) -> bool:
        cap = self._policy.max_rss_bytes
        if cap <= 0:
            return False
        return self._resources.rss_bytes() >= cap

    def try_acquire(self) -> bool:
        if self._policy.max_connections <= 0:
            return False
        if self._active >= self._policy.max_connections:
            return False
        if self.over_limit():
            return False
        self._active += 1
        return True

    def release(self) -> None:
        if self._active > 0:
            self._active -= 1
