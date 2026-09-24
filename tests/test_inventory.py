from pathlib import Path

import pytest
import yaml

from core.domain.proxy import proxy_from_endpoint
from inventory.yaml_file import load_inventory


def test_example_inventory_uses_documentation_addresses() -> None:
    proxies = load_inventory(Path("proxies.example.yaml"))
    assert [proxy.host for proxy in proxies] == ["203.0.113.10", "198.51.100.20"]
    assert len({proxy.id for proxy in proxies}) == 2


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "proxies.yaml"
    path.write_text(
        yaml.safe_dump({"proxies": [{"host": "203.0.113.10", "port": 8080}, {"host": "203.0.113.10", "port": 8080}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_inventory(path)


def test_credentials_in_the_host_are_rejected() -> None:
    with pytest.raises(ValueError):
        proxy_from_endpoint("user:secret@203.0.113.10", 8080)
