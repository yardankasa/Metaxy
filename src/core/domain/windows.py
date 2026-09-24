from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from core.domain.check import CheckRecord, DailyRollup, HourlyRollup, SuccessRates

HOUR_SECONDS = 3600.0
DAY_SECONDS = 24 * HOUR_SECONDS


def utc_day(instant: float) -> str:
    return datetime.fromtimestamp(instant, tz=timezone.utc).strftime("%Y-%m-%d")


def utc_hour(instant: float) -> str:
    return datetime.fromtimestamp(instant, tz=timezone.utc).strftime("%Y-%m-%dT%H")


def days_back(count: int, *, now: float) -> list[str]:
    start = datetime.fromtimestamp(now, tz=timezone.utc).date()
    return [(start - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(count - 1, -1, -1)]


def hours_back(count: int, *, now: float) -> list[str]:
    start = datetime.fromtimestamp(now, tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    return [(start - timedelta(hours=offset)).strftime("%Y-%m-%dT%H") for offset in range(count - 1, -1, -1)]


def rates_from_checks(
    records: list[CheckRecord],
    proxy_ids: list[str],
    *,
    now: float,
    series: str,
) -> dict[str, SuccessRates]:
    since_1h = now - HOUR_SECONDS
    since_24h = now - DAY_SECONDS
    since_7d = now - 7 * DAY_SECONDS
    buckets: dict[str, list[int]] = {proxy_id: [0, 0, 0, 0, 0, 0] for proxy_id in proxy_ids}
    for record in records:
        if record.series != series or record.checked_at < since_7d:
            continue
        slot = buckets.get(record.proxy_id)
        if slot is None:
            continue
        slot[4] += 1
        if record.success:
            slot[5] += 1
        if record.checked_at >= since_24h:
            slot[2] += 1
            if record.success:
                slot[3] += 1
        if record.checked_at >= since_1h:
            slot[0] += 1
            if record.success:
                slot[1] += 1
    return {
        proxy_id: SuccessRates(
            window_1h_total=counts[0],
            window_1h_ok=counts[1],
            window_24h_total=counts[2],
            window_24h_ok=counts[3],
            window_7d_total=counts[4],
            window_7d_ok=counts[5],
        )
        for proxy_id, counts in buckets.items()
    }


def daily_rollups_from_checks(
    records: list[CheckRecord],
    *,
    now: float,
    days: int,
    series: str,
) -> dict[str, list[DailyRollup]]:
    since = now - days * DAY_SECONDS
    grouped: dict[tuple[str, str], list[CheckRecord]] = defaultdict(list)
    for record in records:
        if record.series == series and record.checked_at >= since:
            grouped[(record.proxy_id, utc_day(record.checked_at))].append(record)
    out: dict[str, list[DailyRollup]] = defaultdict(list)
    for (proxy_id, day), rows in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        out[proxy_id].append(_daily(proxy_id, day, rows))
    return dict(out)


def hourly_rollups_from_checks(
    records: list[CheckRecord],
    *,
    now: float,
    hours: int,
    series: str,
) -> dict[str, list[HourlyRollup]]:
    since = now - hours * HOUR_SECONDS
    grouped: dict[tuple[str, str], list[CheckRecord]] = defaultdict(list)
    for record in records:
        if record.series == series and record.checked_at >= since:
            grouped[(record.proxy_id, utc_hour(record.checked_at))].append(record)
    out: dict[str, list[HourlyRollup]] = defaultdict(list)
    for (proxy_id, hour), rows in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        out[proxy_id].append(_hourly(proxy_id, hour, rows))
    return dict(out)


def _daily(proxy_id: str, day: str, rows: list[CheckRecord]) -> DailyRollup:
    successes = [row for row in rows if row.success]
    latencies = [row.latency_ms for row in successes if row.latency_ms is not None]
    average = sum(latencies) / len(latencies) if latencies else None
    return DailyRollup(
        proxy_id=proxy_id,
        day=day,
        success_count=len(successes),
        fail_count=len(rows) - len(successes),
        avg_latency_ms=average,
    )


def _hourly(proxy_id: str, hour: str, rows: list[CheckRecord]) -> HourlyRollup:
    daily = _daily(proxy_id, hour, rows)
    return HourlyRollup(
        proxy_id=proxy_id,
        hour=hour,
        success_count=daily.success_count,
        fail_count=daily.fail_count,
        avg_latency_ms=daily.avg_latency_ms,
    )
