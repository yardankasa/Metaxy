from __future__ import annotations

from pathlib import Path

import yaml

from core.domain.proxy import Proxy, proxy_from_endpoint


def load_inventory(path: Path) -> list[Proxy]:
    if not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("inventory file must be a mapping")
    entries = raw.get("proxies", [])
    if not isinstance(entries, list):
        raise ValueError("proxies must be a list")
    proxies: list[Proxy] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each proxy must be a mapping of host, port, and label")
        proxy = proxy_from_endpoint(
            str(entry.get("host", "")),
            int(entry.get("port", 0)),
            str(entry.get("label", "default")),
        )
        if proxy.id in seen:
            raise ValueError(f"duplicate proxy id {proxy.id}")
        seen.add(proxy.id)
        proxies.append(proxy)
    return proxies
