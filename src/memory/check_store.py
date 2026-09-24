from __future__ import annotations

from collections.abc import Sequence

from core.contracts.check_store import CheckStore
from core.domain.check import CheckRecord, DailyRollup, HourlyRollup, SuccessRates
from core.domain.windows import (
    DAY_SECONDS,
    daily_rollups_from_checks,
    hourly_rollups_from_checks,
    rates_from_checks,
    utc_day,
    utc_hour,
)


class InMemoryCheckStore(CheckStore):
    def __init__(self) -> None:
        self._records: list[CheckRecord] = []
        self._daily: dict[str, list[DailyRollup]] = {}
        self._hourly: dict[str, list[HourlyRollup]] = {}
        self.opened = False

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.opened = False

    async def record(self, records: Sequence[CheckRecord]) -> None:
        self._records.extend(records)

    async def success_rates(
        self,
        proxy_ids: Sequence[str],
        *,
        now: float,
        series: str,
    ) -> dict[str, SuccessRates]:
        return rates_from_checks(self._records, list(proxy_ids), now=now, series=series)

    async def rebuild_rollups(self, *, now: float, days: int, hours: int, series: str) -> None:
        self._daily = daily_rollups_from_checks(self._records, now=now, days=days, series=series)
        self._hourly = hourly_rollups_from_checks(self._records, now=now, hours=hours, series=series)

    async def daily_since(self, *, days: int, now: float) -> dict[str, list[DailyRollup]]:
        start = utc_day(now - (days - 1) * DAY_SECONDS)
        return {
            proxy_id: [row for row in rows if row.day >= start]
            for proxy_id, rows in self._daily.items()
        }

    async def hourly_since(self, *, hours: int, now: float) -> dict[str, list[HourlyRollup]]:
        start = utc_hour(now - (hours - 1) * 3600)
        return {
            proxy_id: [row for row in rows if row.hour >= start]
            for proxy_id, rows in self._hourly.items()
        }

    async def history(self, proxy_id: str, *, series: str, limit: int) -> list[CheckRecord]:
        matched = [row for row in self._records if row.proxy_id == proxy_id and row.series == series]
        matched.sort(key=lambda row: row.checked_at, reverse=True)
        return matched[:limit]

    async def prune(self, *, now: float, retain_days: int) -> int:
        cutoff = now - max(1, retain_days) * DAY_SECONDS
        before = len(self._records)
        self._records = [row for row in self._records if row.checked_at >= cutoff]
        day_cutoff = utc_day(cutoff)
        hour_cutoff = utc_hour(cutoff)
        self._daily = {
            proxy_id: [row for row in rows if row.day >= day_cutoff]
            for proxy_id, rows in self._daily.items()
        }
        self._hourly = {
            proxy_id: [row for row in rows if row.hour >= hour_cutoff]
            for proxy_id, rows in self._hourly.items()
        }
        return before - len(self._records)
