# Metaxy | Proxy Health Pool

A pool of HTTP proxies is only useful while the members in it still work. One dead address, left in front of the others, stalls every client that keeps using it. Checking by hand does not scale, and swapping to whichever proxy answered last makes traffic flap between members that are only briefly faster.

Metaxy keeps a list of proxies you operate, checks them on a schedule, and sends new connections to a member that has stayed healthy. When that member fails, the next healthy one takes the connection. The list itself stays on your machine. This repository does not ship a working inventory.

## What it fixes

- **A single bad proxy blocks everyone behind it.** The local feeder tries the preferred member first, then other healthy members, up to a failover limit.
- **One lucky check looks like a good proxy.** A member becomes healthy only after a streak of successes, and unhealthy only after a streak of failures.
- **The ranking chatters.** A slightly better score does not steal traffic. A lead has to hold for the configured number of sweeps.
- **Old failures are forgotten, or they dominate.** The score mixes the last hour, the last day, and the last week, plus current health and latency.
- **A path outside the pool is mixed into the ranking.** An optional egress probe is stored on its own series and never changes who is preferred.

## Core functionality

You point Metaxy at a check URL and a YAML list of `host`, `port`, and `label`. On each sweep it requests that URL through every member and records success, status, and latency.

From those records it keeps three windows: 1 hour, 24 hours, and 7 days. The score is a weighted sum of those success rates, a healthy flag, and a latency ratio. Recent success weighs more than the week. Slower than the latency budget adds nothing.

The preferred member is the one new feeder connections try first. The feeder listens on loopback, accepts normal HTTP requests and `CONNECT`, and walks the healthy list if the first choice does not answer. A tunnel already open stays where it is when a later sweep picks someone else.

The dashboard shows the preferred member, the pool health rate, the feeder, the optional egress probe, and the table of members. The same picture is available as JSON.

| | |
|---|---|
| Dashboard | [http://127.0.0.1:8080](http://127.0.0.1:8080) |
| Feeder | `http://127.0.0.1:18080` |
| Status | `GET /v1/status` |
| Members | `GET /v1/proxies` and `GET /v1/proxies/{id}` |
| Process | `GET /health`, `GET /ready`, `GET /metrics` |

## Architecture

The rules live in one core. Everything that touches the network, the clock, or the database sits outside it and is wired in a single place. Replacing SQLite with Postgres means a new store behind the same port. The sweep, the score, and the feeder do not change.

```
inventory  →  sweep  →  store  →  score and selection  →  feeder
                              ↘
                                dashboard and JSON
```

| Piece | Role |
|---|---|
| Domain | Members, checks, the score, and the rule for who is preferred. No I/O. |
| Use cases | One sweep, one egress probe, one status read. |
| HTTP client | Probes the check URL through a member. Response bodies are capped so a large page cannot fill memory. |
| Store | Check history, the three windows, and daily and hourly rollups. SQLite by default. An in-memory store implements the same contract for tests. |
| Feeder | The local forwarder. It only dials members the pool currently calls healthy. |
| Pressure guard | A soft memory cap pauses probes and refuses new feeder connections instead of growing until the host kills the process. |
| API | The dashboard and the JSON envelope. Errors carry a code, not an exception traceback. |

A few techniques carry the behavior:

- **Streaks, not single samples.** Health flips only after consecutive results.
- **Hold before switch.** The preferred member moves when a lead lasts, not when a score ticks up once.
- **Separate series.** Pool checks and the egress probe never share a success rate.
- **Derived identity.** A member is `host:port`. The same address always updates the same history.
- **Time is injected.** Sweeps and tests share a clock port, so windows can be asserted without waiting an hour.

Configuration, field meanings, and the domain vocabulary are in [docs/configuration.md](docs/configuration.md) and [docs/domain.md](docs/domain.md).

## Run

Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
cp proxies.example.yaml proxies.yaml
uv sync
./run.sh
```

Edit `proxies.yaml` so it lists proxies you operate. The example file uses documentation addresses and is not a working pool. Leave `proxies.yaml` and `.env` uncommitted.

`./run.sh` starts the dashboard, the feeder, and the sweep. `METAXY_` environment variables override `config.yaml` (`METAXY_FEEDER__PORT=18081`). Keep the feeder on `127.0.0.1` unless other machines are supposed to use it.

```bash
curl -x http://127.0.0.1:18080 http://www.gstatic.com/generate_204
uv run pytest -q
```
