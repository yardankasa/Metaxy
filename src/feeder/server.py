from __future__ import annotations

import asyncio

from core.domain.proxy import Proxy
from core.services.pool import Pool
from core.services.pressure import PressureGuard

_HEADER_LIMIT = 65536
_RELAY_CHUNK = 65536
_UNAVAILABLE = (
    b"HTTP/1.1 503 Service Unavailable\r\n"
    b"Content-Length: 0\r\n"
    b"Connection: close\r\n"
    b"\r\n"
)
_BAD_GATEWAY = (
    b"HTTP/1.1 502 Bad Gateway\r\n"
    b"Content-Length: 0\r\n"
    b"Connection: close\r\n"
    b"\r\n"
)
_BAD_REQUEST = (
    b"HTTP/1.1 400 Bad Request\r\n"
    b"Content-Length: 0\r\n"
    b"Connection: close\r\n"
    b"\r\n"
)


def _headers_complete(buf: bytes) -> bool:
    return b"\r\n\r\n" in buf or b"\n\n" in buf


async def read_http_head(reader: asyncio.StreamReader, limit: int = _HEADER_LIMIT) -> bytes:
    buf = bytearray()
    while not _headers_complete(buf):
        chunk = await reader.read(1024)
        if not chunk:
            break
        buf += chunk
        if len(buf) > limit:
            raise ValueError("request head exceeds the limit")
    if not buf or not _headers_complete(buf):
        raise ValueError("incomplete request head")
    return bytes(buf)


def parse_request_line(head: bytes) -> tuple[str, str, str]:
    first = head.split(b"\n", 1)[0].strip(b"\r")
    parts = first.decode("ascii", "replace").split()
    if len(parts) < 3:
        raise ValueError("malformed request line")
    return parts[0].upper(), parts[1], parts[2]


def parse_connect_target(target: str) -> tuple[str, int]:
    host, sep, port_text = target.rpartition(":")
    if not sep or not host:
        raise ValueError("malformed CONNECT target")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host, int(port_text)


def _status_ok(status_line: bytes) -> bool:
    parts = status_line.strip().decode("ascii", "replace").split()
    return len(parts) >= 2 and parts[1].isdigit() and 200 <= int(parts[1]) < 300


async def _relay(
    left_reader: asyncio.StreamReader,
    left_writer: asyncio.StreamWriter,
    right_reader: asyncio.StreamReader,
    right_writer: asyncio.StreamWriter,
) -> None:
    async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
        try:
            while True:
                data = await src.read(_RELAY_CHUNK)
                if not data:
                    break
                dst.write(data)
                await dst.drain()
        except (ConnectionError, asyncio.IncompleteReadError, TimeoutError):
            pass
        finally:
            try:
                dst.close()
            except Exception:
                pass

    await asyncio.gather(pipe(left_reader, right_writer), pipe(right_reader, left_writer))


async def _open(proxy: Proxy, timeout_seconds: float):
    return await asyncio.wait_for(asyncio.open_connection(proxy.host, proxy.port), timeout=timeout_seconds)


async def _close_writer(writer: asyncio.StreamWriter | None) -> None:
    if writer is None:
        return
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        return


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    pool: Pool,
    *,
    connect_timeout_seconds: float,
    max_failover: int,
    guard: PressureGuard | None = None,
) -> None:
    acquired = True
    if guard is not None:
        acquired = guard.try_acquire()
        if not acquired:
            await _finish(writer, _UNAVAILABLE)
            await _close_writer(writer)
            return
    try:
        head = await read_http_head(reader)
        method, target, _version = parse_request_line(head)
        candidates = pool.healthy_ranked()[: max(1, max_failover)]
        if not candidates:
            await _finish(writer, _BAD_GATEWAY)
            return
        if method == "CONNECT":
            served = await _tunnel(reader, writer, candidates, target, connect_timeout_seconds)
        else:
            served = await _forward(reader, writer, candidates, head, connect_timeout_seconds)
        if not served:
            await _finish(writer, _BAD_GATEWAY)
    except asyncio.CancelledError:
        raise
    except Exception:
        await _finish(writer, _BAD_REQUEST)
    finally:
        if guard is not None and acquired:
            guard.release()
        await _close_writer(writer)


async def _tunnel(reader, writer, candidates: list[Proxy], target: str, timeout_seconds: float) -> bool:
    host, port = parse_connect_target(target)
    request = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode("ascii")
    for proxy in candidates:
        up_writer = None
        try:
            up_reader, up_writer = await _open(proxy, timeout_seconds)
            up_writer.write(request)
            await up_writer.drain()
            reply = await asyncio.wait_for(read_http_head(up_reader), timeout=timeout_seconds)
            if not _status_ok(reply.split(b"\n", 1)[0]):
                await _close_writer(up_writer)
                continue
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await _relay(reader, writer, up_reader, up_writer)
            return True
        except Exception:
            await _close_writer(up_writer)
    return False


async def _forward(reader, writer, candidates: list[Proxy], head: bytes, timeout_seconds: float) -> bool:
    for proxy in candidates:
        up_writer = None
        try:
            up_reader, up_writer = await _open(proxy, timeout_seconds)
            up_writer.write(head)
            await up_writer.drain()
            status = await asyncio.wait_for(up_reader.readline(), timeout=timeout_seconds)
            if not status.upper().startswith(b"HTTP/"):
                raise ConnectionError("upstream closed before a status line")
            writer.write(status)
            await writer.drain()
            await _relay(reader, writer, up_reader, up_writer)
            return True
        except Exception:
            await _close_writer(up_writer)
    return False


async def _finish(writer: asyncio.StreamWriter, payload: bytes) -> None:
    try:
        writer.write(payload)
        await writer.drain()
    except Exception:
        return


async def serve_feeder(
    pool: Pool,
    guard: PressureGuard,
    *,
    host: str,
    port: int,
    connect_timeout_seconds: float,
    max_failover: int,
    stop: asyncio.Event,
) -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await handle_client(
            reader,
            writer,
            pool,
            connect_timeout_seconds=connect_timeout_seconds,
            max_failover=max_failover,
            guard=guard,
        )

    server = await asyncio.start_server(handler, host=host, port=port)
    async with server:
        await stop.wait()
        server.close()
        await server.wait_closed()
