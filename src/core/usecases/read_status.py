from __future__ import annotations

from dataclasses import dataclass

from core.contracts.check_store import CheckStore
from core.contracts.clock import Clock
from core.domain.check import CheckRecord, DailyRollup, HourlyRollup, Series
from core.services.egress import EgressStatus
from core.services.pool import MemberState, Pool


@dataclass(frozen=True, slots=True)
class ProxyDetail:
    member: MemberState
    preferred: bool
    history: list[CheckRecord]
    daily: list[DailyRollup]
    hourly: list[HourlyRollup]


class ReadStatusService:
    def __init__(self, *, pool: Pool, egress: EgressStatus, store: CheckStore, clock: Clock) -> None:
        self._pool = pool
        self._egress = egress
        self._store = store
        self._clock = clock

    @property
    def pool(self) -> Pool:
        return self._pool

    @property
    def egress(self) -> EgressStatus:
        return self._egress

    async def detail(self, proxy_id: str) -> ProxyDetail | None:
        member = self._pool.get(proxy_id)
        if member is None:
            return None
        now = self._clock.now()
        history = await self._store.history(proxy_id, series=Series.POOL, limit=100)
        daily = (await self._store.daily_since(days=7, now=now)).get(proxy_id, [])
        hourly = (await self._store.hourly_since(hours=24, now=now)).get(proxy_id, [])
        return ProxyDetail(
            member=member,
            preferred=proxy_id == self._pool.preferred_id,
            history=history,
            daily=daily,
            hourly=hourly,
        )
