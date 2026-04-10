# CliniGraph AI — Incident Response Runbook

## 1. Purpose and Scope

This runbook defines the step-by-step response procedures for security and operational incidents in the CliniGraph AI platform. It applies to all production environments and must be reviewed annually or after every major incident.

**Incident severity levels:**

| Level | Name | Response SLA | Examples |
|---|---|---|---|
| P0 | Critical | 15 min | Data breach, PHI exposure, full service outage |
| P1 | High | 1 hour | Auth service down, mass abuse, billing system failure |
| P2 | Medium | 4 hours | Elevated 5xx error rate, Kafka consumer lag spike |
| P3 | Low | 24 hours | Unusual traffic pattern, failed seed operation |

---

## 2. On-Call Contact Matrix

| Role | Responsibility | Escalation Path |
|---|---|---|
| On-call Engineer | First responder | → Engineering Lead |
| Engineering Lead | Technical escalation decision | → CTO |
| CTO | Business and regulatory escalation | → Legal / DPO |
| DPO (Data Protection Officer) | HIPAA/GDPR notifications | → Regulatory bodies |

---

## 3. Incident Response Phases

### Phase 1 — Detection

**Automated signals (Grafana alerts → PagerDuty / Slack):**
- `alert_5xx_spike` — 5xx error rate > 5 % over 5 minutes
- `alert_auth_failures` — auth failures > 50 / minute
- `alert_security_event_spike` — security_events_total delta > 100 / 5 min
- `alert_cpu_high`, `alert_memory_high` — resource saturation
- Celery worker heartbeat missing > 2 minutes

**Manual detection sources:**
- User-reported issues via support channel
- Staff review of security dashboard (`GET /api/v1/platform/security-events/`)
- Prometheus query: `rate(http_responses_5xx_total[5m]) > 0.05`

### Phase 2 — Classification

1. Determine severity (P0–P3) using the table above.
2. Open an incident ticket (issue tracker / Jira) with label `incident`.
3. Assign an incident commander from the on-call rotation.
4. Notify the team in the `#incidents` Slack channel with:
   - Severity, affected service, start time, symptoms.
   - Direct link to the Grafana dashboard relevant to the incident.

### Phase 3 — Containment

**If PHI exposure is suspected (P0):**
1. Immediately isolate the affected service: scale Django web container to 0 replicas.
   ```bash
   docker service scale agentai-web=0   # Docker Swarm
   kubectl scale deploy clinigraph-web --replicas=0   # Kubernetes
   ```
2. Revoke all active API keys for the affected tenant(s):
   ```bash
   python manage.py shell -c "from api.models import ApiKey; ApiKey.objects.filter(is_active=True).update(is_active=False)"
   ```
3. Invalidate all active JWT tokens:
   ```bash
   python manage.py flushexpiredtokens   # clears blacklist, forces re-login
   ```
4. Engage DPO for HIPAA Breach Assessment within **60 minutes** of detection.

**If abuse / DDoS is suspected (P1):**
1. Identify attacker CIDRs using the security events API:
   ```bash
   curl -H "Authorization: Bearer <STAFF_TOKEN>" \
     /api/v1/platform/security-events/?event_type=geo_ip_flagged&page_size=50
   ```
2. Add offending CIDRs to `GEO_IP_BLOCKLIST_CIDRS` env var and redeploy, OR update the WAF block list.
3. Increase rate limits by tightening `AgentAnonRateThrottle` in `throttles.py` if attack is from anonymous clients.

**If a compromised API key is detected (P1):**
1. Locate the key by prefix in the admin console or:
   ```bash
   python manage.py shell -c "
   from api.models import ApiKey
   # Find by prefix visible to user — actual key is hashed
   ApiKey.objects.filter(name__icontains='<name>').update(is_active=False)
   "
   ```
2. Emit a `SecurityEvent` manually if not already recorded.
3. Notify the affected tenant via email.

### Phase 4 — Eradication

- Patch the root vulnerability or misconfiguration.
- Rotate all relevant secrets (see `SECRETS_ROTATION_RUNBOOK.md`).
- If a dependency CVE: update the package, rebuild Docker image, redeploy.
  ```bash
  docker compose -f docker-compose.saas.yml build --no-cache web
  docker compose -f docker-compose.saas.yml up -d web
  ```

### Phase 5 — Recovery

1. Restore service from last known-good image or config.
2. Validate end-to-end health:
   ```bash
   curl /api/v1/health/                  # should return {"status":"ok"}
   curl -H "X-API-Key: <key>" /api/v1/agent/query/ -d '{"question":"test"}'
   ```
3. Monitor error rate for 30 minutes post-recovery before declaring incident closed.
4. Confirm Celery worker is processing ingestion queue:
   ```bash
   docker logs agentai-celery-worker --tail 20
   ```

### Phase 6 — Post-Incident Review

Schedule a post-mortem within **48 hours** of resolution. Document:
- Timeline of detection → containment → recovery.
- Root cause analysis (5 Whys).
- Impact: affected tenants, data exposure risk (even if PHI exposure was ruled out).
- Action items: owner + deadline.
- Update this runbook if a new scenario was encountered.

---

## 4. HIPAA Breach Notification Requirements

If PHI exposure cannot be **ruled out** within 24 hours:

1. **72-hour rule**: HIPAA Breach Notification Rule (45 CFR §164.400–414) requires notification to HHS and affected individuals within **60 calendar days** of discovery.
2. Notify affected individuals in writing.
3. Notify HHS via the HHS Breach Report Portal.
4. If > 500 individuals affected in a single state: notify prominent media in that state.
5. Document all notification actions and retain records for **6 years**.

> **Note**: CliniGraph AI never stores raw PHI — only SHA-256 hashes, redaction counts, and redaction categories. A breach of the database does not constitute PHI exposure if the de-identification pipeline functioned correctly. However, a breach of the AI inference endpoint or its upstream buffers during a live request window must be treated as a potential PHI exposure.

---

## 5. Key Operational Commands Quick Reference

```bash
# Check service health
curl https://<your-domain>/api/v1/health/

# View recent security events (staff JWT required)
curl -H "Authorization: Bearer <STAFF_TOKEN>" \
  "https://<your-domain>/api/v1/platform/security-events/?page_size=20"

# View active ingestion jobs
curl -H "X-API-Key: <KEY>" "https://<your-domain>/api/v1/jobs/<job_id>/"

# Celery worker status
docker exec agentai-celery-worker celery -A webapi inspect ping

# Force-fail a stuck ingestion job
python manage.py shell -c "
from api.models import IngestionJob
IngestionJob.objects.filter(status='running').update(status='failed', error='manual intervention')
"

# Export SIEM security events (CSV)
curl -H "Authorization: Bearer <STAFF_TOKEN>" \
  "https://<your-domain>/api/v1/platform/security-events/export/?output=csv" \
  -o security_events.csv

# Flush Redis cache (clear stale AI answer cache)
redis-cli -u $REDIS_URL FLUSHDB

# Revoke all tokens for a specific user
python manage.py shell -c "
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
User = get_user_model()
user = User.objects.get(username='<username>')
OutstandingToken.objects.filter(user=user).delete()
"
```

---

## 6. Runbook Maintenance

| Reviewed By | Date | Changes |
|---|---|---|
| Engineering | April 2026 | Initial version |
