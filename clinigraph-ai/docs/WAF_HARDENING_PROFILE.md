# CliniGraph AI — WAF and Reverse Proxy Hardening Profile

## 1. Overview

This document defines the recommended reverse proxy and Web Application Firewall (WAF)
configuration for production deployments of CliniGraph AI. The reference proxy is
**nginx 1.26+**, but the principles apply to Caddy, HAProxy, AWS ALB + WAF, or
Cloudflare WAF equivalents.

---

## 2. Reference nginx Configuration

Save as `/etc/nginx/sites-available/clinigraph-ai.conf` and symlink to `sites-enabled/`.

```nginx
# ─── Rate limiting zones ──────────────────────────────────────────────────────
limit_req_zone $binary_remote_addr zone=api_anon:10m   rate=30r/m;
limit_req_zone $binary_remote_addr zone=api_auth:10m   rate=120r/m;
limit_req_zone $binary_remote_addr zone=api_heavy:10m  rate=10r/m;

# ─── Connection limiting ──────────────────────────────────────────────────────
limit_conn_zone $binary_remote_addr zone=conn_per_ip:10m;

upstream clinigraph_backend {
    server 127.0.0.1:8000;
    keepalive 64;
}

server {
    listen 80;
    server_name api.clinigraph.ai;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.clinigraph.ai;

    # ── TLS ──────────────────────────────────────────────────────────────────
    ssl_certificate     /etc/letsencrypt/live/api.clinigraph.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.clinigraph.ai/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling        on;
    ssl_stapling_verify on;

    # ── Security headers ─────────────────────────────────────────────────────
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options    "nosniff" always;
    add_header X-Frame-Options           "DENY" always;
    add_header X-XSS-Protection          "1; mode=block" always;
    add_header Referrer-Policy           "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy        "camera=(), microphone=(), geolocation=()" always;
    add_header Content-Security-Policy   "default-src 'none'; script-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline';" always;

    # Remove server fingerprint headers
    server_tokens off;
    more_clear_headers Server;
    more_clear_headers X-Powered-By;

    # ── Request limits ───────────────────────────────────────────────────────
    client_max_body_size  20M;    # allow corpus file uploads
    client_body_timeout   30s;
    client_header_timeout 10s;
    send_timeout          30s;
    keepalive_timeout     65;

    # ── Connection limit ─────────────────────────────────────────────────────
    limit_conn conn_per_ip 20;

    # ── Buffer size hardening (prevent buffer overflow exploits) ────────────
    client_body_buffer_size    16k;
    client_header_buffer_size  1k;
    large_client_header_buffers 4 8k;

    # ── Deny access to hidden files and sensitive paths ──────────────────────
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    location ~ /(manage\.py|\.env|\.git|__pycache__|requirements) {
        deny all;
        access_log off;
        return 404;
    }

    # ── Health check — no rate limit, no auth ────────────────────────────────
    location = /api/v1/health/ {
        proxy_pass         http://clinigraph_backend;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        access_log off;
    }

    # ── Heavy training/upload endpoints — strict rate limit ─────────────────
    location ~ ^/api/v1/agent/(oncology|medical)/(train|upload)/ {
        limit_req zone=api_heavy burst=3 nodelay;
        limit_req_status 429;

        proxy_pass         http://clinigraph_backend;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # ── Streaming endpoints — long timeout, no buffering ─────────────────────
    location ~ ^/api/v1/agent/.*/stream/ {
        limit_req zone=api_auth burst=15 nodelay;
        limit_req_status 429;

        proxy_pass             http://clinigraph_backend;
        proxy_set_header       Host $host;
        proxy_set_header       X-Real-IP $remote_addr;
        proxy_set_header       X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header       X-Forwarded-Proto $scheme;
        proxy_buffering        off;
        proxy_cache            off;
        proxy_read_timeout     120s;
        proxy_http_version     1.1;
        proxy_set_header       Connection "";
        chunked_transfer_encoding on;
    }

    # ── Auth endpoints — moderate rate limit ─────────────────────────────────
    location ~ ^/api/v1/auth/ {
        limit_req zone=api_anon burst=10 nodelay;
        limit_req_status 429;

        proxy_pass         http://clinigraph_backend;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # ── All other API endpoints ───────────────────────────────────────────────
    location /api/ {
        limit_req zone=api_auth burst=30 nodelay;
        limit_req_status 429;

        proxy_pass         http://clinigraph_backend;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}
```

---

## 3. ModSecurity / OWASP CRS (Optional WAF Layer)

For environments requiring WAF rule sets (e.g., PCI, HIPAA audit requirements), deploy
**ModSecurity v3** with the **OWASP Core Rule Set (CRS) v4**:

```bash
# Install on Ubuntu/Debian
apt install libmodsecurity3 libmodsecurity-dev
# Clone CRS
git clone https://github.com/coreruleset/coreruleset /etc/nginx/modsecurity/crs

# Minimal nginx snippet to enable CRS
# In nginx.conf:
#   modsecurity on;
#   modsecurity_rules_file /etc/nginx/modsecurity/main.conf;
```

**CRS tuning for CliniGraph AI:**
- Disable rule 920170 (no `Content-Type` on GET — DRF sends `application/json` on GET responses, not requests ✓)
- Disable rule 942100 (SQL injection false positives on medical terminology — `union` appears in clinical text)
- Paranoia level: **2** recommended for SaaS medical API

---

## 4. Cloudflare WAF Equivalents (Managed Rules)

If using Cloudflare in front of the platform:

| Rule | Action | Notes |
|---|---|---|
| OWASP Core Ruleset | Block | Paranoia level Medium |
| Cloudflare Managed Rules | Block | Enable all |
| Rate limiting — API endpoints | 30 req/min anonymous | Match `/api/v1/*` |
| Rate limiting — Auth endpoints | 10 req/min per IP | Match `/api/v1/auth/*` |
| Geo blocking | Configurable | See `GEO_IP_BLOCKLIST_CIDRS` env var |
| Bot protection | JS Challenge | For browser-facing endpoints only |
| Account Takeover Protection | Block credential stuffing | On `/api/v1/auth/token/` |

---

## 5. IP Reputation Controls (Django Layer)

The `GeoIPReputationMiddleware` in `api/middleware.py` provides application-layer
IP reputation enforcement, complementing the reverse proxy:

| Setting | Env Var | Default | Effect |
|---|---|---|---|
| Blocklist CIDRs | `GEO_IP_BLOCKLIST_CIDRS` | (empty) | 403 + SecurityEvent |
| Flaglist CIDRs | `GEO_IP_FLAGLIST_CIDRS` | (empty) | Pass-through + SecurityEvent |
| Allowlist CIDRs | `GEO_IP_ALLOWLIST_CIDRS` | `127.0.0.1/32,::1/128` | Skip all checks |

**Example `.env` for known high-risk CIDR ranges:**
```bash
GEO_IP_BLOCKLIST_CIDRS=185.220.0.0/16,192.42.116.0/24
GEO_IP_FLAGLIST_CIDRS=45.142.212.0/24,23.129.64.0/18
# Always allowlist internal health check sources:
GEO_IP_ALLOWLIST_CIDRS=127.0.0.1/32,::1/128,10.0.0.0/8
```

Blocked requests appear in the security event log with `event_type=geo_ip_blocked`.
Use the SIEM export to refresh blocklists automatically.

---

## 6. TLS Certificate Management

Use **certbot** with Let's Encrypt for automatic certificate renewal:

```bash
certbot --nginx -d api.clinigraph.ai
# Auto-renewal via systemd timer (certbot package sets this up automatically)
systemctl status certbot.timer
```

For production with higher assurance: use an OV or EV certificate from a commercial CA.

---

## 7. Security Header Verification

After deploying nginx, verify headers with:

```bash
curl -I https://api.clinigraph.ai/api/v1/health/
# Expected headers:
# Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
# X-Content-Type-Options: nosniff
# X-Frame-Options: DENY
# Content-Security-Policy: default-src 'none'; ...
```

Use [securityheaders.com](https://securityheaders.com) to validate the full response header set.

---

## 8. Maintenance

| Reviewed By | Date | Changes |
|---|---|---|
| Engineering | April 2026 | Initial version — nginx config + CRS + Cloudflare + IP reputation docs |
