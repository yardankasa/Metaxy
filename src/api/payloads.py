from __future__ import annotations

from pydantic import BaseModel, Field


class Meta(BaseModel):
    request_id: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    meta: Meta
    error: ErrorBody


class PreferredView(BaseModel):
    id: str
    url: str
    label: str
    latency_ms: float | None
    score: float


class PoolView(BaseModel):
    healthy: int
    unhealthy: int
    total: int
    health_rate: float
    preferred: PreferredView | None
    last_sweep_at: float | None
    last_sweep_seconds: float | None
    sweep_in_progress: bool


class FeederView(BaseModel):
    host: str
    port: int


class EgressView(BaseModel):
    enabled: bool
    ok: bool | None
    via: str | None
    latency_ms: float | None
    status_code: int | None
    checked_at: float | None
    error: str | None


class StatusData(BaseModel):
    pool: PoolView
    feeder: FeederView
    egress: EgressView


class StatusEnvelope(BaseModel):
    meta: Meta
    data: StatusData


class ProxyRow(BaseModel):
    id: str
    host: str
    port: int
    label: str
    url: str
    healthy: bool
    preferred: bool
    score: float
    latency_ms: float | None
    last_status: int | None
    last_error: str | None
    last_checked_at: float | None
    success_1h: float
    success_24h: float
    success_7d: float
    consecutive_success: int
    consecutive_fail: int


class ProxyListData(BaseModel):
    count: int
    proxies: list[ProxyRow]


class ProxyListEnvelope(BaseModel):
    meta: Meta
    data: ProxyListData


class RollupRow(BaseModel):
    bucket: str
    success_count: int
    fail_count: int
    avg_latency_ms: float | None
    success_rate: float | None


class HistoryRow(BaseModel):
    checked_at: float
    success: bool
    latency_ms: float | None
    status_code: int | None
    error: str | None


class ProxyDetailData(BaseModel):
    proxy: ProxyRow
    history: list[HistoryRow]
    daily: list[RollupRow]
    hourly: list[RollupRow]


class ProxyDetailEnvelope(BaseModel):
    meta: Meta
    data: ProxyDetailData


class ReadyData(BaseModel):
    status: str
    checks: dict[str, str] = Field(default_factory=dict)


class ReadyEnvelope(BaseModel):
    meta: Meta
    data: ReadyData
