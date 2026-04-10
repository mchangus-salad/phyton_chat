# CliniGraph AI — Scalability Architecture

## Overview

This document describes the scalability strategy for CliniGraph AI across four key
dimensions: database read scaling, CDN/API gateway, regional deployment, and
global rate-limiting.  The implementation is incremental — each layer can be
activated independently via environment variables or Docker Compose profiles.

---

## 1. Database Read Replica

### Goal
Offload read-heavy query patterns (audit logs, evidence searches, session lookups)
from the primary PostgreSQL instance to one or more read replicas, reducing
primary DB load and improving read latency.

### Implementation

#### Django DB router — `api/db_router.py`
`ReadReplicaRouter` is a standard Django database router that:
- Routes all `SELECT` queries to the `replica` alias (if configured).
- Routes all `INSERT` / `UPDATE` / `DELETE` to `default`.
- Blocks `migrate` from running against the replica.
- Falls back silently to `default` when no replica is configured (local dev).

Activated in `webapi/settings.py`:
```python
DATABASE_ROUTERS = ['api.db_router.ReadReplicaRouter']
```

#### Replica env vars
| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_REPLICA_DB_HOST` | *(empty — disables replica)* | Hostname of the read replica |
| `DJANGO_REPLICA_DB_PORT` | `5432` | Port |
| `DJANGO_REPLICA_DB_NAME` | Same as primary | Database name |
| `DJANGO_REPLICA_DB_USER` | Same as primary | DB user |
| `DJANGO_REPLICA_DB_PASSWORD` | Same as primary | DB password |
| `DJANGO_REPLICA_DB_CONN_MAX_AGE` | `60` | Connection pool keep-alive (seconds) |

#### PostgreSQL streaming replication (ops)
1. On the primary, enable `wal_level = replica` and `max_wal_senders = 3`.
2. Create a replication user: `CREATE ROLE replicator REPLICATION LOGIN PASSWORD '…';`
3. Bootstrap the replica with `pg_basebackup -h primary -U replicator -D /var/lib/postgresql/data -P -R`.
4. The replica starts as a hot-standby (`hot_standby = on` in `postgresql.conf`).
5. Configure `primary_conninfo` in `recovery.conf` / `postgresql.auto.conf`.

#### Testing
In Django tests the replica is configured with `TEST: {MIRROR: default}` so all
test transactions run against a single DB, keeping the test suite self-contained.

---

## 2. CDN / API Gateway

### Goal
Reduce origin load for cacheable responses (static assets, public evidence API,
documentation artifacts) and enforce TLS termination at the edge.

### Strategy

#### Public CDN (Cloudflare / AWS CloudFront)
- **Cache policy**: `Cache-Control: public, max-age=300` for evidence search
  responses where the query + domain hash is stable.
- **Cache bypass**: JWT-authenticated requests carry an `Authorization` header —
  CDN pass-through must be configured to bypass cache for any request with
  `Authorization` or `X-API-Key` headers.
- **Purge**: Use cache-tag purging (`cf-cache-status`, CloudFront invalidations)
  after corpus re-training to flush stale evidence results.

#### API Gateway (AWS API Gateway / Kong)
For enterprise self-hosted deployments:
- Route `/api/v1/mobile/*` through the `mobile-gateway` nginx profile
  (see `docker-compose.saas.yml`).
- Apply JWT validation at the gateway layer to reduce hits on the Django worker.
- Per-tenant throttle quotas enforced by the gateway before request hits Django
  (complements Django's `AgentUserRateThrottle`).

#### nginx mobile gateway (`infra/nginx/mobile-gateway.conf`)
A lightweight nginx reverse proxy that provides:
- Per-IP rate limiting: 10 req/s (burst 20).
- Global rate limiting: 60 req/s aggregate.
- Client body size capped at 20 MB for patient case uploads.
- Security headers (X-Frame-Options, nosniff, XSS-Protection).
- Activate with `docker compose --profile mobile up`.

---

## 3. Regional / Multi-Zone Deployment

### Architecture

```
                         ┌──────────────────────────────┐
                         │     Global Load Balancer      │
                         │  (AWS ALB / Cloudflare LB)    │
                         └──────────┬───────────┬────────┘
                                    │           │
                    ┌───────────────▼──┐   ┌────▼────────────────┐
                    │   Region: US-E   │   │   Region: EU-W       │
                    │ ┌──────────────┐ │   │  ┌──────────────┐   │
                    │ │ web (Django) │ │   │  │ web (Django) │   │
                    │ │ × N replicas │ │   │  │ × N replicas │   │
                    │ └──────┬───────┘ │   │  └──────┬───────┘   │
                    │ ┌──────▼───────┐ │   │  ┌──────▼───────┐   │
                    │ │  postgres    │ │   │  │  postgres    │   │
                    │ │  primary     │◄────┤  │  replica     │   │
                    │ └──────────────┘ │   │  └──────────────┘   │
                    │ ┌──────────────┐ │   │  ┌──────────────┐   │
                    │ │ redis        │ │   │  │ redis read   │   │
                    │ │ primary      │◄────┤  │ replica      │   │
                    │ └──────────────┘ │   │  └──────────────┘   │
                    └──────────────────┘   └───────────────────────┘
```

### Data sovereignty considerations (HIPAA)
- PHI never crosses region boundaries — each region's DB is independent.
- Audit logs (`SecurityEvent`) are replicated only within the same data-residency
  zone; cross-region replication is disabled for PHI-adjacent tables.
- CDN caching is disabled for any response that may embed patient session data
  (cache bypass header: `Cache-Control: private, no-store`).

### Deployment sequence
1. Provision primary region (US-E) with full stack.
2. Provision secondary region (EU-W) with a read replica pointed at US-E primary.
3. Promote EU-W replica to primary via `pg_promote()` if primary is unreachable
   (RTO < 30 s with automated failover via Patroni / AWS RDS Multi-AZ).
4. Set `DJANGO_REPLICA_DB_HOST` per region and redeploy.

---

## 4. Global Rate-Limiting Strategy

### Layered defence

| Layer | Mechanism | Threshold |
|---|---|---|
| nginx mobile gateway | `limit_req_zone` per-IP | 10 req/s, burst 20 |
| nginx mobile gateway | `limit_req_zone` global | 60 req/s, burst 100 |
| Django `AnonRateThrottle` | DRF throttle | 30 req/min anonymous |
| Django `AgentUserRateThrottle` | DRF throttle | 120 req/min per user |
| Django `TenantPlanQuotaThrottle` | DRF throttle | Per-plan quota |

### Redis-backed distributed throttling
`AgentUserRateThrottle` and `TenantPlanQuotaThrottle` store counters in Redis.
In a multi-region setup, a single Redis cluster (or Redis Enterprise Active-Active)
is shared across all Django pods in the same region.  Cross-region throttle
coordination is handled by the upstream load balancer (sticky sessions per tenant).

### Token-bucket algorithm
DRF uses a sliding-window counter in Redis (key TTL = window size). For high-
traffic tenants the bucket refills at the plan's `api_request_limit` per month;
remaining budget is exposed via the `X-RateLimit-Remaining` response header
(calculated in `TenantPlanQuotaThrottle.wait()`).

### Burst protection for AI endpoints
The LangGraph pipeline is CPU/GPU-bound. Upstream nginx absorbs bursts while
Django async workers (ASGI + Daphne) process requests concurrently. At 500 RPS
sustained load provision ≥ 4 Django workers (`WEB_CONCURRENCY=4`) and scale
horizontally via Kubernetes HPA targeting CPU > 60%.

---

## Checklist

- [x] Django read replica router (`api/db_router.py`)
- [x] `DATABASE_ROUTERS` configured in `settings.py`
- [x] Conditional `DATABASES['replica']` from env vars
- [x] Mobile API gateway nginx profile (`docker-compose.saas.yml`)
- [x] `infra/nginx/mobile-gateway.conf` — rate limits, security headers
- [x] Per-IP + global `limit_req_zone` in nginx
- [ ] Patroni / RDS Multi-AZ automated failover (ops — cloud infra)
- [ ] Cloudflare / CloudFront CDN rules for evidence API caching (ops — cloud infra)
- [ ] Redis Enterprise Active-Active for cross-region throttle counters (ops — cloud infra)
- [ ] Kubernetes HPA manifests for Django web pods (ops — k8s cluster)
