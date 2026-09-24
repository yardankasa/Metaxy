from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

from api.mappers import daily_row, history_row, hourly_row, member_row, status_data
from api.payloads import (
    ErrorBody,
    ErrorEnvelope,
    Meta,
    ProxyDetailData,
    ProxyDetailEnvelope,
    ProxyListData,
    ProxyListEnvelope,
    ReadyData,
    ReadyEnvelope,
    StatusEnvelope,
)

POOL_HEALTHY = Gauge("metaxy_pool_healthy", "Members currently marked healthy")
POOL_TOTAL = Gauge("metaxy_pool_members", "Members in the inventory")
EGRESS_UP = Gauge("metaxy_egress_up", "1 when the optional egress probe succeeded")

DASHBOARD = Path(__file__).resolve().parent / "dashboard.html"
router = APIRouter()


def _meta(request: Request) -> Meta:
    return Meta(request_id=getattr(request.state, "request_id", uuid.uuid4().hex))


def _container(request: Request):
    return request.app.state.container


@router.get("/health")
async def health(request: Request) -> ReadyEnvelope:
    return ReadyEnvelope(meta=_meta(request), data=ReadyData(status="ok"))


@router.get("/ready")
async def ready(request: Request) -> ReadyEnvelope:
    container = _container(request)
    checks = {
        "inventory": "ok" if container.pool.total else "empty",
        "store": "ok" if container.store_ready else "closed",
        "egress": "enabled" if container.egress.enabled else "disabled",
    }
    status = "ready" if checks["store"] == "ok" else "degraded"
    if checks["inventory"] == "empty":
        status = "degraded"
    return ReadyEnvelope(meta=_meta(request), data=ReadyData(status=status, checks=checks))


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    container = _container(request)
    POOL_HEALTHY.set(container.pool.healthy_count)
    POOL_TOTAL.set(container.pool.total)
    egress_up = 1 if container.egress.enabled and container.egress.ok else 0
    EGRESS_UP.set(egress_up)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD.read_text(encoding="utf-8"))


@router.get("/v1/status", response_model=StatusEnvelope)
async def status(request: Request) -> StatusEnvelope:
    container = _container(request)
    data = status_data(
        container.pool,
        container.egress,
        feeder_host=container.settings.feeder.host,
        feeder_port=container.settings.feeder.port,
    )
    return StatusEnvelope(meta=_meta(request), data=data)


@router.get("/v1/proxies", response_model=ProxyListEnvelope)
async def proxies(request: Request) -> ProxyListEnvelope:
    container = _container(request)
    preferred = container.pool.preferred_id
    rows = [member_row(member, preferred=member.proxy.id == preferred) for member in container.pool.members()]
    rows.sort(key=lambda row: (not row.preferred, not row.healthy, -row.score, row.id))
    return ProxyListEnvelope(meta=_meta(request), data=ProxyListData(count=len(rows), proxies=rows))


@router.get("/v1/proxies/{proxy_id:path}", response_model=ProxyDetailEnvelope)
async def proxy_detail(proxy_id: str, request: Request) -> ProxyDetailEnvelope | JSONResponse:
    container = _container(request)
    detail = await container.status.detail(proxy_id)
    if detail is None:
        body = ErrorEnvelope(
            meta=_meta(request),
            error=ErrorBody(code="unknown_proxy", message="That member is not in the inventory."),
        )
        return JSONResponse(status_code=404, content=body.model_dump())
    return ProxyDetailEnvelope(
        meta=_meta(request),
        data=ProxyDetailData(
            proxy=member_row(detail.member, preferred=detail.preferred),
            history=[history_row(row) for row in detail.history],
            daily=[daily_row(row) for row in detail.daily],
            hourly=[hourly_row(row) for row in detail.hourly],
        ),
    )
