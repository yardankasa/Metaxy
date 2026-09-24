from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from core.domain.check import CheckRecord, DailyRollup, HourlyRollup, SuccessRates


class CheckStore(ABC):
    @abstractmethod
    async def open(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def record(self, records: Sequence[CheckRecord]) -> None: ...

    @abstractmethod
    async def success_rates(
        self,
        proxy_ids: Sequence[str],
        *,
        now: float,
        series: str,
    ) -> dict[str, SuccessRates]: ...

    @abstractmethod
    async def rebuild_rollups(self, *, now: float, days: int, hours: int, series: str) -> None: ...

    @abstractmethod
    async def daily_since(self, *, days: int, now: float) -> dict[str, list[DailyRollup]]: ...

    @abstractmethod
    async def hourly_since(self, *, hours: int, now: float) -> dict[str, list[HourlyRollup]]: ...

    @abstractmethod
    async def history(self, proxy_id: str, *, series: str, limit: int) -> list[CheckRecord]: ...

    @abstractmethod
    async def prune(self, *, now: float, retain_days: int) -> int: ...
