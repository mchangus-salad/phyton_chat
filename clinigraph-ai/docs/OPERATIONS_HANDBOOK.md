# CliniGraph AI — Operations Handbook

## 1. Stack Overview

| Service | Role | Port (local) |
|---|---|---|
| Django (Gunicorn) | Backend API | 8000 |
| React (Vite) | SaaS frontend | 5173 |
| Redis | Cache + JWT blacklist | 6379 |
| Kafka (Confluent) | Event streaming | 9092 |
| Weaviate | Vector DB (local) | 8080 |
| Ollama | Local LLM server | 11434 |
| Prometheus | Metrics scrape | 9090 |
| Grafana | Dashboards | 3000 |

---

## 2. Development Environment

### Start full local stack
```powershell
.\scripts\dev-up.ps1
```
This starts Redis, Kafka, Weaviate, Ollama, Prometheus, Grafana, Django backend, and React frontend via Docker Compose (`docker-compose.local.yml`).

### Seed medical corpus
```powershell
.\scripts\dev-seed.ps1
```
Seeds all specialties from `data/seed_*.json` via management commands.

### Run backend only
```powershell
& .venv\Scripts\Activate.ps1
python manage.py runserver
```

### Run tests
```powershell
python manage.py test api --verbosity=1
```
Expected: **128+ tests, 0 failures**.

### Database migrations
```powershell
python manage.py makemigrations
python manage.py migrate
```

### Stop stack
```powershell
.\scripts\dev-down.ps1
```

---

## 3. Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Prod only | dev-insecure | Django secret key |
| `DEBUG` | No | `True` | Set `False` in production |
| `ALLOWED_HOSTS` | Prod only | `*` | Comma-separated host list |
| `DATABASE_URL` | Prod only | SQLite | PostgreSQL DSN |
| `OPENAI_API_KEY` | Yes (GPT) | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | Yes (Claude) | — | Anthropic API key |
| `AGENT_AI_LLM_PROVIDER` | No | `mock` | `gpt\|claude\|ollama\|mock` |
| `AGENT_AI_VECTOR_DB_PROVIDER` | No | `weaviate` | `pinecone\|weaviate` |
| `PINECONE_API_KEY` | If Pinecone | — | Pinecone API key |
| `PINECONE_INDEX` | If Pinecone | — | Index name |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection |
| `KAFKA_BOOTSTRAP_SERVERS` | No | `localhost:9092` | Kafka broker |
| `STRIPE_SECRET_KEY` | Billing | — | Stripe secret key |
| `BILLING_WEBHOOK_SECRET` | Billing | — | Stripe webhook secret |
| `CORS_ALLOWED_ORIGINS` | Prod | `http://localhost:5173` | Frontend origins |

---

## 4. Key API Endpoints

### Health
```
GET /api/v1/health/
```
Returns `{"status": "ok"}`. Use for load balancer health checks.

### Operational Metrics
```
GET /api/v1/ops/metrics/           → JSON snapshot
GET /api/v1/ops/metrics/prometheus/ → Prometheus text format
```

### Security Audit
```
GET /api/v1/security/events/recent/?limit=100     → Recent events (staff)
GET /api/v1/security/events/export/?format=json   → NDJSON export (staff)
GET /api/v1/security/events/export/?format=cef    → CEF export (staff)
GET /api/v1/audit/patient-cases/?days=30&limit=50 → Patient-case audit (staff)
```

---

## 5. Grafana Dashboards

URL: `http://localhost:3000` (admin / admin in dev)

### CliniGraph AI – Operations (`clinigraph-ops`)
Panels organized in four rows:

| Row | Panels |
|---|---|
| Security | Auth failures/min, Abuse blocks/min, Security events (table) |
| Availability | HTTP 2xx/4xx/5xx rates, Latency (avg ms) |
| Billing | Subscriptions active, Billing events over time |
| SLO Targets | Availability SLO gauge (≥99.5%), Latency stat (<3000ms), Error budget burn rate, Availability timeseries |

### Alert Rules (Grafana-managed)
| Alert | Condition | Severity |
|---|---|---|
| High auth failure rate | auth_failures > 10/min for 5m | warning |
| Abuse spike | abuse_blocks > 5/min for 2m | critical |
| 5xx spike | http_5xx rate > 1% for 5m | warning |

---

## 6. Incident Response Quick Reference

### Auth/credential compromise
1. Rotate `SECRET_KEY` → all sessions invalidated
2. Rotate affected API keys: `DELETE /api/v1/auth/logout/` per affected user
3. Review `SecurityEvent` log: `GET /api/v1/security/events/recent/?limit=500`
4. Export for SIEM: `GET /api/v1/security/events/export/?format=cef&limit=1000`

### PHI breach investigation
1. Query `PatientCaseSession` audit: `GET /api/v1/audit/patient-cases/?days=90`
2. Verify: no original text stored (`text_hash` fields only)
3. Review redaction categories and counts
4. Check application logs for any PHI in error messages (should not exist — `phi_deidentifier.py` runs before logging)
5. Notify DPO within 72h per HIPAA breach notification rule

### Service degradation
1. Check `GET /api/v1/health/` from external probe
2. Check Prometheus metrics for 5xx spike
3. Review Grafana SLO panel — availability gauge go red < 99.5%
4. Roll back recent deployment: `docker compose up --no-deps web --build` previous image
5. If Weaviate: `docker compose restart weaviate`
6. If Redis: `docker compose restart redis` (JWT blacklist resets — monitor for replay attacks)

---

## 7. Deployment Checklist (Production)

- [ ] Set `DEBUG=False`
- [ ] Set `SECRET_KEY` to secure random value
- [ ] Set `ALLOWED_HOSTS` to production domain
- [ ] Set `DATABASE_URL` to PostgreSQL
- [ ] Run `python manage.py migrate`
- [ ] Run `python manage.py seed_plans` to initialize billing plans
- [ ] Set Stripe keys and webhook endpoint
- [ ] Set `CORS_ALLOWED_ORIGINS` to production frontend URL
- [ ] Set `SECURE_SSL_REDIRECT=True`
- [ ] Configure reverse proxy (Nginx / Caddy) with TLS
- [ ] Verify `GET /api/v1/health/` returns 200
- [ ] Verify Grafana dashboards load and receive metrics
- [ ] Create first staff user: `python manage.py createsuperuser`

---

## 8. Log Management

All application logs are structured JSON (via `RequestIDMiddleware` + Python `logging`).

Log fields: `timestamp`, `level`, `logger`, `message`, `request_id`, `tenant_id` (when available).

**Rules**:
- PHI and PII must never appear in logs — `phi_deidentifier.py` runs before any logging in patient-case flows
- Security events are stored in `SecurityEvent` model, not just log files
- Log shipping: configure Filebeat → Elasticsearch or Filebeat → SIEM of choice
- Retention: recommended 90 days hot, 1 year cold

---

## 9. Backup and Recovery

| Resource | Backup strategy | RTO | RPO |
|---|---|---|---|
| PostgreSQL (prod) | Daily pg_dump + WAL archiving | 4h | 1h |
| Weaviate vectors | Daily snapshot to object storage | 8h | 24h |
| Redis (JWT blacklist) | Ephemeral — acceptable to lose | Instant restart | Full reset |
| Kafka topics | 7-day retention | — | 7 days replay |
| Application code | Git (GitHub) | Minutes | Commit |
| Grafana dashboards | Provisioned from `monitoring/` in repo | Minutes | Commit |
