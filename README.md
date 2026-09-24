# Metaxy | Proxy Health Pool

Metaxy watches a list of HTTP proxies that you operate, scores them from recent checks, and exposes a local feeder that fails over to the next healthy member.

The inventory never ships with the repository. You keep it in `proxies.yaml`, which is gitignored. The committed example uses documentation addresses from RFC 5737 and is not a working pool.

## What it does

1. On a timer, it requests a check URL through every member and records success, status, and latency.
2. A member becomes healthy only after consecutive successes, and unhealthy only after consecutive failures.
3. The preferred member is the one the feeder tries first. A small score lead does not move it; a lead that lasts for the configured number of sweeps does.
4. The feeder listens on loopback and forwards HTTP and `CONNECT` to healthy members, in preferred order, up to a failover limit.
5. An optional egress URL can be probed on its own series so those samples never enter the pool score.

## Run

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.14.

```bash
cp proxies.example.yaml proxies.yaml
# edit proxies.yaml so it lists proxies you operate
uv sync
./run.sh
```

The dashboard is at [http://127.0.0.1:8080](http://127.0.0.1:8080). The feeder is at `http://127.0.0.1:18080`.

```bash
curl -x http://127.0.0.1:18080 http://www.gstatic.com/generate_204
uv run python src/main.py inventory
uv run pytest -q
uv run ruff check src tests
```

`./run.sh` is `uv run python src/main.py serve`. Pass `--config` to point at another YAML file. Environment variables use the prefix `METAXY_` and `__` for nested fields, for example `METAXY_FEEDER__PORT=18081`.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Operator dashboard |
| `GET` | `/health` | Process is up |
| `GET` | `/ready` | Inventory and store. `degraded` when the inventory is empty or the store is closed |
| `GET` | `/metrics` | Prometheus gauges for pool size and egress |
| `GET` | `/v1/status` | Pool, feeder, and egress snapshot |
| `GET` | `/v1/proxies` | Every member and its score |
| `GET` | `/v1/proxies/{id}` | One member, recent checks, and rollups |

JSON responses use one envelope: `{"meta": {"request_id": "..."}, "data": ...}` on success and `{"meta": ..., "error": {"code", "message"}}` on failure. Error bodies do not include exception text.

## Layout

`src/` is a flat set of adapters around one core. `core` does not import an adapter.

```
src/core/contracts     ports
src/core/domain        values and pure rules
src/core/services      pool, pressure, egress state
src/core/usecases      sweep, egress probe, status read
src/api                dashboard and JSON
src/cli                commands
src/tasks              the clock
src/feeder             local forwarder
src/clients            HTTP probes
src/persistence        SQLite
src/memory             in-memory stand-ins
src/inventory          YAML inventory file
src/composition        the only place that wires them
```

Read [docs/domain.md](docs/domain.md) for the vocabulary and the rules the tests lock in. Read [docs/configuration.md](docs/configuration.md) before changing a number.

## Status

| Capability | State |
|---|---|
| Scoring and hysteresis | built |
| SQLite history, windows, and rollups | built |
| In-memory store with the same window math | built |
| Loopback feeder with failover and `CONNECT` | built |
| Optional egress probe, stored on its own series | built |
| Dashboard, JSON API, readiness, metrics | built |
| Operator inventory file, gitignored | built |

## Safety

- Bind the feeder to `127.0.0.1` unless you intend other hosts to use it.
- Do not commit `proxies.yaml` or `.env`.
- The process only dials the members you listed and the check URL. It does not discover proxies.
