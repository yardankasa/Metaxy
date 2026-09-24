from __future__ import annotations

import asyncio

import aiohttp

from core.contracts.clock import Clock
from core.contracts.prober import Prober
from core.domain.check import ProbeOutcome


def _truncate(error: str | None, limit: int = 240) -> str | None:
    if error is None:
        return None
    text = " ".join(error.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


class HttpProber(Prober):
    def __init__(
        self,
        *,
        clock: Clock,
        check_url: str,
        expected_status: int,
        max_body_bytes: int,
        concurrency: int,
    ) -> None:
        self._clock = clock
        self._check_url = check_url
        self._expected_status = expected_status
        self._max_body_bytes = max_body_bytes
        timeout = aiohttp.ClientTimeout(total=None)
        connector = aiohttp.TCPConnector(limit=max(1, concurrency), force_close=True, ttl_dns_cache=300)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trust_env=False,
            headers={"User-Agent": "metaxy-health/0.1"},
            auto_decompress=False,
        )

    async def aclose(self) -> None:
        await self._session.close()

    async def probe(self, proxy_url: str, *, timeout_seconds: float) -> ProbeOutcome:
        started = self._clock.monotonic()
        checked_at = self._clock.now()
        timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=min(timeout_seconds, 5.0))
        try:
            async with self._session.get(
                self._check_url,
                proxy=proxy_url,
                allow_redirects=False,
                timeout=timeout,
                auto_decompress=False,
            ) as response:
                await _discard(response, self._max_body_bytes)
                latency_ms = round((self._clock.monotonic() - started) * 1000.0, 2)
                success = response.status == self._expected_status
                error = None if success else f"unexpected status {response.status}"
                return ProbeOutcome(success, latency_ms, response.status, error, checked_at)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            latency_ms = round((self._clock.monotonic() - started) * 1000.0, 2)
            return ProbeOutcome(False, latency_ms, None, _truncate(f"{type(exc).__name__}: {exc}"), checked_at)


async def _discard(response: aiohttp.ClientResponse, max_bytes: int) -> None:
    remaining = max(0, max_bytes)
    while remaining > 0:
        chunk = await response.content.read(min(4096, remaining))
        if not chunk:
            return
        remaining -= len(chunk)
    response.close()
