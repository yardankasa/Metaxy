from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

from core.contracts.check_store import CheckStore
from core.domain.check import CheckRecord, DailyRollup, HourlyRollup, SuccessRates
from core.domain.windows import DAY_SECONDS, utc_day, utc_hour
from persistence.models import Base


class SqliteCheckStore(CheckStore):
    def __init__(self, path: Path, *, cache_kb: int = 8192) -> None:
        self._path = path
        self._cache_kb = max(1, cache_kb)
        self._engine = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(f"sqlite+aiosqlite:///{self._path}")

        @event.listens_for(engine.sync_engine, "connect")
        def _pragmas(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA temp_store=FILE")
            cursor.execute("PRAGMA mmap_size=0")
            cursor.execute(f"PRAGMA cache_size={-self._cache_kb}")
            cursor.close()

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._engine = engine

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None

    def _require(self):
        if self._engine is None:
            raise RuntimeError("check store is not open")
        return self._engine

    async def record(self, records: Sequence[CheckRecord]) -> None:
        if not records:
            return
        payload = [
            {
                "proxy_id": row.proxy_id,
                "series": row.series,
                "checked_at": row.checked_at,
                "success": 1 if row.success else 0,
                "latency_ms": row.latency_ms,
                "status_code": row.status_code,
                "error": row.error,
            }
            for row in records
        ]
        statement = text(
            """
            INSERT INTO checks (proxy_id, series, checked_at, success, latency_ms, status_code, error)
            VALUES (:proxy_id, :series, :checked_at, :success, :latency_ms, :status_code, :error)
            """
        )
        async with self._lock:
            async with self._require().begin() as conn:
                await conn.execute(statement, payload)

    async def success_rates(
        self,
        proxy_ids: Sequence[str],
        *,
        now: float,
        series: str,
    ) -> dict[str, SuccessRates]:
        ids = list(proxy_ids)
        empty = {proxy_id: SuccessRates() for proxy_id in ids}
        if not ids:
            return empty
        binds = {f"id{index}": proxy_id for index, proxy_id in enumerate(ids)}
        placeholders = ", ".join(f":id{index}" for index in range(len(ids)))
        statement = text(
            f"""
            SELECT proxy_id,
                   SUM(CASE WHEN checked_at >= :since_1h THEN 1 ELSE 0 END) AS n1h,
                   SUM(CASE WHEN checked_at >= :since_1h AND success = 1 THEN 1 ELSE 0 END) AS ok1h,
                   SUM(CASE WHEN checked_at >= :since_24h THEN 1 ELSE 0 END) AS n24,
                   SUM(CASE WHEN checked_at >= :since_24h AND success = 1 THEN 1 ELSE 0 END) AS ok24,
                   COUNT(*) AS n7,
                   SUM(success) AS ok7
            FROM checks
            WHERE series = :series AND checked_at >= :since_7d AND proxy_id IN ({placeholders})
            GROUP BY proxy_id
            """
        )
        params = {
            "since_1h": now - 3600,
            "since_24h": now - DAY_SECONDS,
            "since_7d": now - 7 * DAY_SECONDS,
            "series": series,
            **binds,
        }
        async with self._lock:
            async with self._require().connect() as conn:
                rows = (await conn.execute(statement, params)).mappings().all()
        found = dict(empty)
        for row in rows:
            found[row["proxy_id"]] = SuccessRates(
                window_24h_ok=int(row["ok24"] or 0),
                window_24h_total=int(row["n24"] or 0),
                window_7d_ok=int(row["ok7"] or 0),
                window_7d_total=int(row["n7"] or 0),
                window_1h_ok=int(row["ok1h"] or 0),
                window_1h_total=int(row["n1h"] or 0),
            )
        return found

    async def rebuild_rollups(self, *, now: float, days: int, hours: int, series: str) -> None:
        daily = text(
            """
            INSERT INTO daily_rollups (proxy_id, day, success_count, fail_count, avg_latency_ms)
            SELECT proxy_id,
                   date(CAST(checked_at AS INTEGER), 'unixepoch') AS day,
                   SUM(success),
                   SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END),
                   AVG(CASE WHEN success = 1 THEN latency_ms END)
            FROM checks
            WHERE series = :series AND checked_at >= :since
            GROUP BY proxy_id, day
            ON CONFLICT(proxy_id, day) DO UPDATE SET
                success_count = excluded.success_count,
                fail_count = excluded.fail_count,
                avg_latency_ms = excluded.avg_latency_ms
            """
        )
        hourly = text(
            """
            INSERT INTO hourly_rollups (proxy_id, hour, success_count, fail_count, avg_latency_ms)
            SELECT proxy_id,
                   strftime('%Y-%m-%dT%H', CAST(checked_at AS INTEGER), 'unixepoch') AS hour,
                   SUM(success),
                   SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END),
                   AVG(CASE WHEN success = 1 THEN latency_ms END)
            FROM checks
            WHERE series = :series AND checked_at >= :since
            GROUP BY proxy_id, hour
            ON CONFLICT(proxy_id, hour) DO UPDATE SET
                success_count = excluded.success_count,
                fail_count = excluded.fail_count,
                avg_latency_ms = excluded.avg_latency_ms
            """
        )
        async with self._lock:
            async with self._require().begin() as conn:
                await conn.execute(daily, {"series": series, "since": now - days * DAY_SECONDS})
                await conn.execute(hourly, {"series": series, "since": now - hours * 3600})

    async def daily_since(self, *, days: int, now: float) -> dict[str, list[DailyRollup]]:
        start = utc_day(now - (days - 1) * DAY_SECONDS)
        statement = text(
            """
            SELECT proxy_id, day, success_count, fail_count, avg_latency_ms
            FROM daily_rollups
            WHERE day >= :start
            ORDER BY day ASC
            """
        )
        async with self._lock:
            async with self._require().connect() as conn:
                rows = (await conn.execute(statement, {"start": start})).mappings().all()
        grouped: dict[str, list[DailyRollup]] = defaultdict(list)
        for row in rows:
            grouped[row["proxy_id"]].append(
                DailyRollup(
                    proxy_id=row["proxy_id"],
                    day=row["day"],
                    success_count=int(row["success_count"]),
                    fail_count=int(row["fail_count"]),
                    avg_latency_ms=row["avg_latency_ms"],
                )
            )
        return dict(grouped)

    async def hourly_since(self, *, hours: int, now: float) -> dict[str, list[HourlyRollup]]:
        start = utc_hour(now - (hours - 1) * 3600)
        statement = text(
            """
            SELECT proxy_id, hour, success_count, fail_count, avg_latency_ms
            FROM hourly_rollups
            WHERE hour >= :start
            ORDER BY hour ASC
            """
        )
        async with self._lock:
            async with self._require().connect() as conn:
                rows = (await conn.execute(statement, {"start": start})).mappings().all()
        grouped: dict[str, list[HourlyRollup]] = defaultdict(list)
        for row in rows:
            grouped[row["proxy_id"]].append(
                HourlyRollup(
                    proxy_id=row["proxy_id"],
                    hour=row["hour"],
                    success_count=int(row["success_count"]),
                    fail_count=int(row["fail_count"]),
                    avg_latency_ms=row["avg_latency_ms"],
                )
            )
        return dict(grouped)

    async def history(self, proxy_id: str, *, series: str, limit: int) -> list[CheckRecord]:
        statement = text(
            """
            SELECT proxy_id, series, checked_at, success, latency_ms, status_code, error
            FROM checks
            WHERE proxy_id = :proxy_id AND series = :series
            ORDER BY checked_at DESC
            LIMIT :limit
            """
        )
        async with self._lock:
            async with self._require().connect() as conn:
                result = await conn.execute(
                    statement,
                    {"proxy_id": proxy_id, "series": series, "limit": limit},
                )
                rows = result.mappings().all()
        return [
            CheckRecord(
                proxy_id=row["proxy_id"],
                series=row["series"],
                checked_at=float(row["checked_at"]),
                success=bool(row["success"]),
                latency_ms=row["latency_ms"],
                status_code=row["status_code"],
                error=row["error"],
            )
            for row in rows
        ]

    async def prune(self, *, now: float, retain_days: int) -> int:
        cutoff = now - max(1, retain_days) * DAY_SECONDS
        async with self._lock:
            async with self._require().begin() as conn:
                result = await conn.execute(text("DELETE FROM checks WHERE checked_at < :cutoff"), {"cutoff": cutoff})
                await conn.execute(text("DELETE FROM daily_rollups WHERE day < :day"), {"day": utc_day(cutoff)})
                await conn.execute(text("DELETE FROM hourly_rollups WHERE hour < :hour"), {"hour": utc_hour(cutoff)})
                return int(result.rowcount or 0)
