from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from conftest import run

from core.domain.check import CheckApply, SuccessRates
from core.domain.proxy import Proxy
from core.services.pool import Pool
from feeder.server import handle_client, parse_connect_target, parse_request_line, read_http_head


async def _origin(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    await read_http_head(reader)
    writer.write(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
    await writer.drain()
    writer.close()


async def _good(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    head = await read_http_head(reader)
    method, target, version = parse_request_line(head)
    if method == "CONNECT":
        host, port = parse_connect_target(target)
        up_r, up_w = await asyncio.open_connection(host, port)
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        await _pipe(reader, writer, up_r, up_w)
        return
    parts = urlsplit(target)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    up_r, up_w = await asyncio.open_connection(parts.hostname, parts.port or 80)
    newline = b"\r\n" if b"\r\n" in head else b"\n"
    _first, rest = head.split(newline, 1)
    up_w.write(f"{method} {path} {version}".encode("ascii") + newline + rest)
    await up_w.drain()
    await _pipe(reader, writer, up_r, up_w)


async def _pipe(a_r, a_w, b_r, b_w) -> None:
    async def one(src, dst) -> None:
        try:
            while True:
                chunk = await src.read(65536)
                if not chunk:
                    break
                dst.write(chunk)
                await dst.drain()
        finally:
            dst.close()

    await asyncio.gather(one(a_r, b_w), one(b_r, a_w))


async def _dead(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.close()


async def _start(handler):
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    return server, host, port


def _mark(pool: Pool, *proxies: Proxy) -> None:
    now = 1_700_000_100.0
    pool.apply_sweep(
        [CheckApply(proxy.id, True, 20.0, 204, None, now) for proxy in proxies],
        {proxy.id: SuccessRates(5, 5, 5, 5) for proxy in proxies},
        sweep_at=now,
        duration_seconds=0.1,
    )


def test_feeder_fails_over_and_tunnels() -> None:
    run(_failover())


async def _failover() -> None:
    origin, origin_host, origin_port = await _start(_origin)
    dead, dead_host, dead_port = await _start(_dead)
    good, good_host, good_port = await _start(_good)
    try:
        failed = Proxy(id=f"{dead_host}:{dead_port}", host=dead_host, port=dead_port, label="down")
        live = Proxy(id=f"{good_host}:{good_port}", host=good_host, port=good_port, label="up")
        pool = Pool([failed, live])
        _mark(pool, failed, live)
        local, local_host, local_port = await _start(
            lambda reader, writer: handle_client(reader, writer, pool, connect_timeout_seconds=1.0, max_failover=4)
        )
        try:
            reader, writer = await asyncio.open_connection(local_host, local_port)
            target = f"http://{origin_host}:{origin_port}/generate_204"
            writer.write(f"GET {target} HTTP/1.1\r\nHost: {origin_host}\r\nConnection: close\r\n\r\n".encode())
            await writer.drain()
            response = await asyncio.wait_for(reader.read(1024), timeout=3)
            writer.close()
            assert b"204" in response.split(b"\r\n", 1)[0]

            reader, writer = await asyncio.open_connection(local_host, local_port)
            writer.write(f"CONNECT {origin_host}:{origin_port} HTTP/1.1\r\nHost: {origin_host}\r\n\r\n".encode())
            await writer.drain()
            head = await read_http_head(reader)
            assert b"200" in head.split(b"\n", 1)[0]
            writer.write(f"GET /generate_204 HTTP/1.1\r\nHost: {origin_host}\r\nConnection: close\r\n\r\n".encode())
            await writer.drain()
            tunneled = await asyncio.wait_for(reader.read(1024), timeout=3)
            writer.close()
            assert b"204" in tunneled.split(b"\r\n", 1)[0]
        finally:
            local.close()
            await local.wait_closed()
    finally:
        for server in (origin, dead, good):
            server.close()
            await server.wait_closed()


def test_empty_pool_answers_502() -> None:
    run(_empty())


async def _empty() -> None:
    pool = Pool([Proxy(id="127.0.0.1:9", host="127.0.0.1", port=9, label="down")])
    server, host, port = await _start(
        lambda reader, writer: handle_client(reader, writer, pool, connect_timeout_seconds=0.2, max_failover=2)
    )
    try:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"GET http://example.invalid/ HTTP/1.1\r\nHost: example.invalid\r\n\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(1024), timeout=2)
        writer.close()
        assert b"502" in response.split(b"\r\n", 1)[0]
    finally:
        server.close()
        await server.wait_closed()
