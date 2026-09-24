# Domain

The words below are used in code, logs, and the API. Where two words differ, they are not synonyms.

## 1. Vocabulary

| Word | Meaning |
|---|---|
| Member | One HTTP proxy, identified by `host:port`. The id is derived, never assigned. |
| Inventory | The list of members loaded from a local file. Missing file means an empty pool. |
| Check | One probe through a member: success, latency in milliseconds, status, and the instant `checked_at` (epoch seconds). |
| Series | `pool` or `egress`. Rates and rollups never mix the two. |
| Healthy | The member has reached the success streak and has not since reached the failure streak. |
| Preferred | The healthy member the feeder tries first. |
| Score | A weighted sum of the 1 hour, 24 hour, and 7 day success rates, the healthy flag, and a latency ratio. |
| Feeder | The local forwarder. It is not a member of the pool. |
| Egress | An optional extra URL probed on its own series. It does not enter the pool ranking. |
| Sweep | One pass over every member. |

Durations of loops, timeouts, and sweeps are seconds. Probe latency stays in milliseconds because the score compares it with `latency_ref_ms`.

## 2. Score

`latency_score` is `1 - latency_ms / latency_ref_ms`, clamped to `[0, 1]`. A missing latency or a non-positive reference scores 0.

The default weights are 0.35 (1h), 0.20 (24h), 0.15 (7d), 0.10 (healthy), 0.20 (latency). They are expected to sum to 1. The published score is rounded to 6 decimal places. An unhealthy member keeps its history terms and loses only the healthy weight.

## 3. Selection

Health is a streak, not a single sample. With the defaults, one success marks a member healthy and two consecutive failures mark it unhealthy.

Among healthy members the order is score descending, then lower latency, then id. The preferred member changes when another healthy member leads by at least `score_switch_margin` for `switch_hold_sweeps` consecutive sweeps. A margin of 0 follows the leader on every sweep. A lead that disappears resets the pending count. If nobody is healthy, there is no preferred member.

`healthy_ranked` returns the preferred member first, then the other healthy members by score. The feeder walks that list and stops after `max_failover` attempts.

## 4. Windows

Success rates count checks with `checked_at` inside the last hour, the last 24 hours, and the last 7 days. A check older than 7 days is outside all three. The in-memory store and SQLite both answer from this definition; the persistence test compares them.

Daily and hourly rollups group pool-series checks in UTC. Rebuild replaces the bucket for that member and period. `prune` deletes raw checks and rollup buckets older than `checks_retain_days`.

## 5. Feeder

The feeder accepts an absolute-form HTTP request or `CONNECT`. It opens a TCP connection to a healthy member and sends that request on. The first member that answers is used for the rest of the connection. If none answer, the client receives `502`. If the connection cap or the soft RSS cap is already hit, the client receives `503` and no upstream is dialed.

An in-flight tunnel is not moved when a later sweep changes the preferred member.

## 6. Pressure

`max_rss_mb` is a soft cap. At or above it, sweeps and egress probes are skipped and new feeder connections are refused. `0` disables the soft cap. `hard_limit_mb` installs `RLIMIT_AS` when the platform allows it; `0` leaves the process unlimited. `max_connections` counts feeder clients, not probe concurrency. Probe concurrency is `pool.concurrency`.

## 7. Invariants

1. Egress checks do not change pool success rates.
2. A member is not unhealthy after a single failure when `fail_threshold` is 2.
3. A score lead smaller than `score_switch_margin` does not change the preferred member.
4. The feeder does not dial a member that is not currently healthy.
5. The API error envelope does not include exception text.
6. Inventory hosts are bare names. Userinfo is rejected at load time.
