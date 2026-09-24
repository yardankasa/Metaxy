from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Proxy:
    id: str
    host: str
    port: int
    label: str

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def proxy_from_endpoint(host: str, port: int, label: str = "default") -> Proxy:
    cleaned = host.strip()
    if not cleaned or "://" in cleaned or "@" in cleaned:
        raise ValueError(f"host must be a bare hostname, got {host!r}")
    if port < 1 or port > 65535:
        raise ValueError(f"port out of range: {port}")
    return Proxy(id=f"{cleaned}:{port}", host=cleaned, port=port, label=label.strip() or "default")
