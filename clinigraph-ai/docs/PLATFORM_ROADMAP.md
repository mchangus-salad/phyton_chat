# CliniGraph AI Platform Roadmap

This is the execution roadmap for security, observability, scalability, billing, web, and mobile expansion.

Rule:

- Use this file as the active checklist.
- Mark items complete as implementation lands in code, infrastructure, and docs.
- Add owner/date/notes as the program evolves.

## 1. Security Hardening

- [x] Request ID tracing middleware
- [x] Abuse/security telemetry storage
- [x] Suspicious signature blocking
- [x] Oversized payload blocking
- [x] Failed API-key auth security events
- [x] Secure HTTP settings baseline
- [x] JWT refresh rotation enabled by default in production
- [x] Token blacklist / revocation support
- [x] RBAC by tenant role (owner/admin/clinician/auditor)
- [x] Per-tenant API quotas and enforcement
- [x] SIEM export pipeline
- [ ] Geo/IP reputation controls
- [ ] WAF / reverse proxy hardening profile
- [ ] Penetration testing checklist and runbook
- [ ] Secrets rotation runbook

## 2. Observability and SRE

- [x] Basic operational metrics endpoint
- [x] Security events endpoint for staff
- [x] HTTP latency aggregation
- [x] 2xx/4xx/5xx request counters
- [x] Billing event counters
- [x] Prometheus-compatible metrics endpoint
- [x] Structured JSON logs
- [x] OpenTelemetry tracing
- [x] Alert rules for auth failures / abuse spikes / 5xx spikes
- [x] SLO dashboard (latency, availability, failure rate)
- [x] Audit dashboards for patient-case flows

## 3. Scalability and Multi-Tenancy

- [x] Tenant model
- [x] Usage record model
- [x] Cache abstraction ready for Redis
- [x] Database connection reuse
- [x] True tenant isolation strategy for data access
- [x] Async task queue for heavy ingestion and case analysis
- [ ] Read replica strategy
- [ ] Regional deployment topology
- [ ] CDN and API gateway design
- [ ] Global rate-limiting design

## 4. Billing and Payments

- [x] Subscription plan model
- [x] Subscription model
- [x] Billing event model
- [x] Seed command for default plans
- [x] Public plans endpoint
- [x] Internal subscription draft endpoint
- [x] Stripe checkout session endpoint
- [x] Stripe webhook verification and sync foundation
- [x] Stripe customer portal integration
- [x] Invoice and receipt views
- [x] Proration / upgrade / downgrade support
- [x] Subscription cancellation UI/API
- [x] Trial expiration workflows
- [x] Failed payment recovery flows
- [x] Tax/VAT strategy

## 5. Containerization

- [x] Web service containerized
- [x] Redis containerized
- [x] Kafka containerized
- [x] Weaviate containerized
- [x] Ollama containerized in local stack
- [x] Ollama containerized in SaaS stack
- [x] Auto model pull script for Ollama
- [x] React web frontend containerized
- [ ] Mobile backend gateway/container profile
- [ ] Production container scanning pipeline

## 6. Product Surfaces

### React SaaS Web App

- [x] Workspace/app shell design
- [x] Login / signup / billing pages
- [x] Tenant admin console
- [x] Medical query workspace
- [x] Evidence search workspace
- [x] Patient-case analysis UI
- [x] Audit/security dashboards
- [x] Billing cockpit dashboard scaffold

### iOS App

- [x] Mobile architecture decision
- [ ] Auth/session strategy
- [ ] Case upload workflow
- [ ] Evidence viewer
- [ ] Notifications strategy

### Android App

- [x] Mobile architecture decision
- [ ] Auth/session strategy
- [ ] Case upload workflow
- [ ] Evidence viewer
- [ ] Notifications strategy

## 7. Documentation and Governance

- [x] Documentation centralized in docs folder
- [x] Client manual in Spanish
- [x] Client manual in English
- [x] Documentation update template
- [x] Mermaid diagrams
- [x] Security architecture document
- [x] Billing integration guide
- [x] Operations handbook
- [ ] Incident response runbook
- [x] Mobile/API integration guide

## 8. Immediate Next Milestones

- [ ] Apply migrations in target environment
- [ ] Seed plans in target environment
- [ ] Configure Stripe secrets and price IDs
- [ ] Validate Stripe checkout end-to-end
- [ ] Validate Stripe webhook end-to-end
- [x] Start React SaaS workspace scaffold
- [x] Add Prometheus / Grafana stack
