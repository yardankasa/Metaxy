from __future__ import annotations

import asyncio
from pathlib import Path

import typer
import uvicorn

import tasks.worker as worker
from api.server import create_app
from composition.container import Container
from config.settings import load_settings
from feeder.server import serve_feeder
from telemetry.logs import configure_logging

app = typer.Typer(help="Metaxy | Proxy Health Pool")


@app.callback()
def _root() -> None:
    """Health-check a proxy pool, score it, and fail over through a local feeder."""


def _build(config: Path | None) -> Container:
    settings = load_settings(config)
    root = Path.cwd() if config is None else config.resolve().parent
    return Container(settings, root=root)


@app.command()
def serve(
    config: Path | None = typer.Option(None, "--config", "-c", help="YAML settings file"),
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Start the dashboard, the feeder, and the health worker."""
    configure_logging()
    container = _build(config)
    if host:
        container.settings.api.host = host
    if port:
        container.settings.api.port = port
    asyncio.run(_serve(container))


@app.command()
def inventory(
    config: Path | None = typer.Option(None, "--config", "-c"),
) -> None:
    """Print how many proxies the inventory file contributes. Endpoints stay on disk."""
    container = _build(config)
    typer.echo(f"members={container.pool.total}")


def execute() -> None:
    app()


async def _serve(container: Container) -> None:
    await container.startup()
    stop = asyncio.Event()
    api = create_app(container)
    config = uvicorn.Config(
        api,
        host=container.settings.api.host,
        port=container.settings.api.port,
        log_config=None,
    )
    server = uvicorn.Server(config)
    tasks = [
        asyncio.create_task(worker.run_worker(container, stop), name="worker"),
        asyncio.create_task(
            serve_feeder(
                container.pool,
                container.guard,
                host=container.settings.feeder.host,
                port=container.settings.feeder.port,
                connect_timeout_seconds=container.settings.feeder.connect_timeout_seconds,
                max_failover=container.settings.feeder.max_failover,
                stop=stop,
            ),
            name="feeder",
        ),
        asyncio.create_task(server.serve(), name="api"),
    ]
    try:
        await tasks[-1]
    finally:
        stop.set()
        server.should_exit = True
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await container.shutdown()
