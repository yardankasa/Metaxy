# Working in this repository

## Layout

`src/core` is the only tree that must stay free of libraries, SQL, and HTTP. If a function would still make sense after the store and the transport were replaced, it belongs in `core`. Parsing a file, opening a socket, or writing a row belongs in an adapter.

```
core/domain     stdlib only
core/contracts  ports; may import domain
core/services   domain and contracts
core/usecases   the rest of core
adapters        core, never another adapter
cli, api, tasks core, composition, config, telemetry
composition     wires the graph
```

Imports are absolute from `src/`. One composition root builds the graph. Tests construct that same `Container` and pass a clock, a prober, or a resource probe when the real one would leave the machine.

Entry surfaces stay thin: `api` turns a request into a read, `cli` turns a command into `serve`, `tasks` calls a use case on a timer.

The module name matches the port. `memory/check_store.py` and `persistence/check_store.py` are two stores. `core/contracts/check_store.py` is the port.

## Names

Ports are bare nouns. Use cases are `<Verb><Noun>Service` with `execute`. Policies are frozen dataclasses built in the container. Time in a name is either `*_at` (epoch seconds) or `*_seconds`, except probe latency, which is milliseconds on purpose (see docs/domain.md).

## Checks

```bash
uv run pytest -q
uv run ruff check src tests
```

Async tests call `asyncio.run` through `tests/conftest.py`. One test should lock one rule from docs/domain.md §7.

Do not commit `proxies.yaml`. The example inventory is documentation addresses, not a pool to probe in CI.
