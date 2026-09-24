from __future__ import annotations

from core.contracts.clock import Clock


class FixedClock(Clock):
    def __init__(self, instant: float = 0.0) -> None:
        self.instant = instant
        self._monotonic = 0.0

    def now(self) -> float:
        return self.instant

    def monotonic(self) -> float:
        self._monotonic += 0.001
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self.instant += seconds
