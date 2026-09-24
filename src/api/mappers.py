from __future__ import annotations

from api.payloads import EgressView, FeederView, HistoryRow, PoolView, PreferredView, ProxyRow, RollupRow, StatusData
from core.domain.check import CheckRecord, DailyRollup, HourlyRollup
from core.services.egress import EgressStatus
from core.services.pool import MemberState, Pool


def member_row(member: MemberState, *, preferred: bool) -> ProxyRow:
    rates = member.rates
    return ProxyRow(
        id=member.proxy.id,
        host=member.proxy.host,
        port=member.proxy.port,
        label=member.proxy.label,
        url=member.proxy.url,
        healthy=member.healthy,
        preferred=preferred,
        score=member.score,
        latency_ms=member.last_latency_ms,
        last_status=member.last_status,
        last_error=member.last_error,
        last_checked_at=member.last_checked_at,
        success_1h=round(rates.success_1h, 4),
        success_24h=round(rates.success_24h, 4),
        success_7d=round(rates.success_7d, 4),
        consecutive_success=member.consecutive_success,
        consecutive_fail=member.consecutive_fail,
    )


def status_data(pool: Pool, egress: EgressStatus, *, feeder_host: str, feeder_port: int) -> StatusData:
    preferred = pool.preferred()
    preferred_view = None
    if preferred is not None:
        preferred_view = PreferredView(
            id=preferred.proxy.id,
            url=preferred.proxy.url,
            label=preferred.proxy.label,
            latency_ms=preferred.last_latency_ms,
            score=preferred.score,
        )
    total = pool.total
    healthy = pool.healthy_count
    return StatusData(
        pool=PoolView(
            healthy=healthy,
            unhealthy=max(0, total - healthy),
            total=total,
            health_rate=round(healthy / total, 4) if total else 0.0,
            preferred=preferred_view,
            last_sweep_at=pool.last_sweep_at,
            last_sweep_seconds=pool.last_sweep_seconds,
            sweep_in_progress=pool.sweep_in_progress,
        ),
        feeder=FeederView(host=feeder_host, port=feeder_port),
        egress=EgressView(
            enabled=egress.enabled,
            ok=egress.ok,
            via=_redact(egress.via) if egress.enabled else None,
            latency_ms=egress.latency_ms,
            status_code=egress.status_code,
            checked_at=egress.checked_at,
            error=egress.error,
        ),
    )


def history_row(record: CheckRecord) -> HistoryRow:
    return HistoryRow(
        checked_at=record.checked_at,
        success=record.success,
        latency_ms=record.latency_ms,
        status_code=record.status_code,
        error=record.error,
    )


def daily_row(rollup: DailyRollup) -> RollupRow:
    total = rollup.success_count + rollup.fail_count
    rate = None if total <= 0 else round(rollup.success_count / total, 4)
    return RollupRow(
        bucket=rollup.day,
        success_count=rollup.success_count,
        fail_count=rollup.fail_count,
        avg_latency_ms=rollup.avg_latency_ms,
        success_rate=rate,
    )


def hourly_row(rollup: HourlyRollup) -> RollupRow:
    rate = None if rollup.success_rate is None else round(rollup.success_rate, 4)
    return RollupRow(
        bucket=rollup.hour,
        success_count=rollup.success_count,
        fail_count=rollup.fail_count,
        avg_latency_ms=rollup.avg_latency_ms,
        success_rate=rate,
    )


def _redact(url: str | None) -> str | None:
    if not url or "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    _userinfo, _, host = rest.rpartition("@")
    return f"{scheme}://{host}"
