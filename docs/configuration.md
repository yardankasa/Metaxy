# Configuration

`config.yaml` holds knobs. `proxies.yaml` holds members. Only the first is committed.

Copy `proxies.example.yaml` to `proxies.yaml` and replace the documentation addresses with proxies you operate. Each entry is `host`, `port`, and an optional `label`. Duplicate `host:port` pairs are rejected. A missing file starts an empty pool, and `/ready` reports `inventory: empty`.

## Fields

| Block | Field | What breaks at the extremes |
|---|---|---|
| | `check_url` | Every probe requests this URL. It must be `http` or `https`. |
| | `expected_status` | Any other status is a failed check, even when the TCP connection worked. |
| `pool` | `sweep_interval_seconds` | Too small and the pool spends its time probing. Too large and failover data goes stale. |
| `pool` | `concurrency` | How many probes run at once. |
| `pool` | `timeout_seconds` | A hung member occupies a probe slot until this elapses. |
| `egress` | `proxy_url` | Empty disables the probe. A value is dialed on the egress series only. |
| `feeder` | `host` / `port` | Default bind is loopback `18080`. A public bind makes this process an open forwarder. |
| `feeder` | `max_failover` | How many healthy members one client request may try. |
| `api` | `host` / `port` | Dashboard and JSON. Default `127.0.0.1:8080`. |
| `scoring` | weights and `latency_ref_ms` | Changing them changes who becomes preferred. They do not rewrite history. |
| `selection` | thresholds, margin, hold | See docs/domain.md §3. `switch_hold_sweeps` below 1 is treated as 1. |
| `store` | `path` | SQLite file. An empty path selects the in-memory store, which forgets history on exit. |
| `memory` | `max_rss_mb` | Soft cap. `0` disables it. |
| `memory` | `hard_limit_mb` | `RLIMIT_AS`. `0` disables it. |
| `memory` | `max_connections` | Feeder clients. Must stay at least 1. |
| `memory` | `max_probe_body_bytes` | Probe responses are discarded after this many bytes. |
| `memory` | `checks_retain_days` | Raw checks older than this are deleted after each sweep. |

Environment variables override the file. Prefix `METAXY_`, nest with `__`: `METAXY_POOL__CONCURRENCY=4`.

The feeder and the API refuse nothing about particular port numbers. Pick ports that are free on the host.
