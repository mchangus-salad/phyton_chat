# CliniGraph AI — Secrets Rotation Runbook

## 1. Purpose

This runbook defines the procedure and schedule for rotating all cryptographic secrets,
API keys, and credentials used by the CliniGraph AI platform. Routine rotation limits blast
radius if a credential is silently compromised.

---

## 2. Secrets Inventory

| Secret | Storage Location | Rotation Frequency | Owner |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | `.env` / Secret Manager | Every 6 months or on breach | Engineering |
| JWT signing key (HS256/RS256) | `SIGNING_KEY` in `.env` | Every 6 months or on breach | Engineering |
| `OPENAI_API_KEY` | Secret Manager | Every 12 months or on breach | Engineering |
| `ANTHROPIC_API_KEY` | Secret Manager | Every 12 months or on breach | Engineering |
| `STRIPE_SECRET_KEY` | Secret Manager | Per Stripe policy / on breach | Billing |
| `BILLING_WEBHOOK_SECRET` | Secret Manager | Each webhook endpoint re-registration | Billing |
| `PINECONE_API_KEY` | Secret Manager | Every 12 months or on breach | Engineering |
| `REDIS_URL` (password) | Secret Manager | Every 12 months or on infra change | DevOps |
| `KAFKA_BOOTSTRAP_SERVERS` (SASL) | Secret Manager | Every 12 months | DevOps |
| Tenant API keys (`ApiKey` model) | Database (SHA-256 hashed) | On request or suspected breach | Per-tenant |
| Database credentials (`DATABASE_URL`) | Secret Manager | Every 6 months | DevOps |
| Docker registry credentials | CI/CD secrets | Every 12 months | DevOps |

---

## 3. Rotation Procedures

### 3.1 DJANGO_SECRET_KEY

Used for cookie signing, CSRF tokens, and session encryption. Rotation causes all
existing sessions to become invalid (users must re-login). JWT tokens are **not**
affected (they use `SIGNING_KEY`).

```bash
# Generate new key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 1. Update Secret Manager / .env with new value.
# 2. Redeploy all Django workers (rolling restart — sessions invalidate on restart).
# 3. Verify health: curl /api/v1/health/
```

### 3.2 JWT Signing Key (SIGNING_KEY)

Rotation immediately invalidates all outstanding access tokens. Users will receive 401
on the next request and must obtain a new token via refresh or re-login.

```bash
# Generate RS256 key pair (production)
openssl genpkey -algorithm RSA -out private.pem -pkeyopt rsa_keygen_bits:4096
openssl rsa -in private.pem -pubout -out public.pem

# 1. Store private.pem content as SIGNING_KEY in Secret Manager.
# 2. Store public.pem content as VERIFYING_KEY.
# 3. Redeploy Django workers.
# 4. Run token blacklist flush to clean stale records:
python manage.py flushexpiredtokens
```

### 3.3 OpenAI / Anthropic API Keys

```bash
# 1. Generate new key in the provider's dashboard.
# 2. Update Secret Manager.
# 3. Redeploy Django workers and Celery workers:
docker compose -f docker-compose.saas.yml up -d --no-deps web celery-worker
# 4. Run a smoke test:
curl -H "X-API-Key: <internal-key>" /api/v1/agent/oncology/query/ \
  -d '{"question":"test rotation"}' -H "Content-Type: application/json"
# 5. Revoke the old key in the provider's dashboard.
```

### 3.4 Stripe Keys

```bash
# 1. Generate NEW restricted key in Stripe dashboard with required permissions.
# 2. Update STRIPE_SECRET_KEY in Secret Manager.
# 3. Re-register the Stripe webhook and obtain new BILLING_WEBHOOK_SECRET.
# 4. Update BILLING_WEBHOOK_SECRET in Secret Manager.
# 5. Redeploy Django workers.
# 6. Validate a test webhook event via Stripe CLI:
stripe trigger checkout.session.completed
# 7. Revoke the old key in Stripe dashboard.
```

### 3.5 Pinecone API Key

```bash
# 1. Create new API key in Pinecone console.
# 2. Update PINECONE_API_KEY in Secret Manager.
# 3. Redeploy Django workers and Celery workers.
# 4. Validate vector store connectivity:
python manage.py shell -c "
from api.agent_ai.vector_store import get_vector_store
vs = get_vector_store()
print(vs.ping())
"
# 5. Delete old key in Pinecone console.
```

### 3.6 Tenant API Keys (via Admin)

Tenant API keys are stored as SHA-256 hashes — only the prefix is shown after creation.
To revoke and re-issue:

```bash
python manage.py shell -c "
from api.models import ApiKey
# Revoke by name or prefix
ApiKey.objects.filter(name='<api-key-name>').update(is_active=False)
"
# Then re-issue via the admin UI or the key creation endpoint.
```

### 3.7 Database Credentials

```bash
# 1. Create new DB user / password in PostgreSQL.
# 2. Grant same permissions as existing user.
# 3. Update DATABASE_URL in Secret Manager.
# 4. Deploy new Django workers (rolling).
# 5. Once all workers have restarted:
#    - Drop old DB user:
#    psql -c "DROP ROLE old_user;"
```

---

## 4. Emergency Rotation (Breach Response)

If a secret is confirmed or suspected compromised:

1. **Revoke immediately** in the relevant system (Stripe, OpenAI, Pinecone dashboards).
2. **Generate and deploy** replacement within **1 hour** (P0 SLA).
3. **Audit** the security event log for evidence of unauthorized use:
   ```bash
   curl -H "Authorization: Bearer <STAFF_TOKEN>" \
     "/api/v1/platform/security-events/?event_type=api_key_auth_failure&page_size=100"
   ```
4. **Invalidate all active sessions** if the Django secret key was compromised:
   ```bash
   python manage.py shell -c "from django.contrib.sessions.models import Session; Session.objects.all().delete()"
   ```
5. **Escalate** per the Incident Response Runbook (`INCIDENT_RESPONSE_RUNBOOK.md`).

---

## 5. Rotation Log Template

Maintain a rotation log (this file or a linked spreadsheet) for audit purposes:

| Date | Secret | Rotated By | Reason | Verification |
|---|---|---|---|---|
| 2026-04-10 | Initial values set | Engineering | Initial deployment | Health check OK |
| YYYY-MM-DD | (secret name) | (name) | Routine / Breach | (test result) |

---

## 6. Runbook Maintenance

Review this runbook after every rotation and after each incident. Update the inventory
if new secrets are introduced.

| Reviewed By | Date | Changes |
|---|---|---|
| Engineering | April 2026 | Initial version |
