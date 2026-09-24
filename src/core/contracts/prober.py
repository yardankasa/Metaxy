from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.check import ProbeOutcome


class Prober(ABC):
    @abstractmethod
    async def probe(self, proxy_url: str, *, timeout_seconds: float) -> ProbeOutcome: ...

    async def aclose(self) -> None:
        return None
