from pathlib import Path

import yaml
from conftest import run
from fastapi.testclient import TestClient

from api.server import create_app
from composition.container import Container
from config.settings import Settings
from core.domain.check import CheckApply, SuccessRates
from memory.clock import FixedClock


def test_status_and_dashboard(tmp_path: Path) -> None:
    run(_status(tmp_path))


async def _status(tmp_path: Path) -> None:
    inventory = tmp_path / "proxies.yaml"
    inventory.write_text(
        yaml.safe_dump({"proxies": [{"host": "203.0.113.10", "port": 8080, "label": "docs"}]}),
        encoding="utf-8",
    )
    settings = Settings(
        inventory_path=str(inventory),
        store=Settings().store.model_copy(update={"path": ""}),
        egress=Settings().egress.model_copy(update={"proxy_url": ""}),
    )
    container = Container(settings, root=tmp_path, clock=FixedClock(1_700_000_000.0))
    await container.startup()
    member = container.pool.proxies()[0]
    container.pool.apply_sweep(
        [CheckApply(member.id, True, 42.0, 204, None, 1_700_000_000.0)],
        {member.id: SuccessRates()},
        sweep_at=1_700_000_000.0,
        duration_seconds=1.2,
    )
    app = create_app(container)
    try:
        with TestClient(app) as client:
            page = client.get("/")
            assert page.status_code == 200
            assert "Metaxy | Proxy Health Pool" in page.text
            status = client.get("/v1/status")
            assert status.status_code == 200
            body = status.json()
            assert body["data"]["pool"]["healthy"] == 1
            assert body["data"]["pool"]["preferred"]["id"] == member.id
            assert body["data"]["egress"]["enabled"] is False
            listing = client.get("/v1/proxies")
            assert listing.json()["data"]["count"] == 1
            missing = client.get("/v1/proxies/198.51.100.8:9")
            assert missing.status_code == 404
            assert missing.json()["error"]["code"] == "unknown_proxy"
            ready = client.get("/ready")
            assert ready.json()["data"]["checks"]["inventory"] == "ok"
    finally:
        await container.shutdown()
