from __future__ import annotations

import time

from core.contracts.clock import Clock


class SystemClock(Clock):
    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()
