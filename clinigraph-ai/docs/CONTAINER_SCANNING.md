# CliniGraph AI — Container Scanning Guide

## 1. Overview

All Docker images used in CliniGraph AI are scanned for known CVEs using
**[Trivy](https://github.com/aquasecurity/trivy)** (AquaSecurity), an open-source
container and file system vulnerability scanner trusted in production pipelines.

The primary image scanned is `clinigraph-ai-web:latest`, which contains both the Django
backend runtime and the Celery worker runtime.

**Policy:**
- **CRITICAL** and **HIGH** CVEs block production deploys.
- **MEDIUM** and **LOW** findings are tracked but do not block releases by default.
- Scans run on every local CI run and must run before any production push.

---

## 2. Running a Scan

### Quick scan (local developer check)
```powershell
.\scripts\scan-containers.ps1
```
Scans `clinigraph-ai-web:latest` and prints a table of CRITICAL/HIGH findings to stdout.

### CI gate (block on findings)
```powershell
.\scripts\scan-containers.ps1 -ExitOnFinding
```
Exits with code 1 if any CRITICAL or HIGH CVE is found. Use this in `ci-local.ps1` or a GitHub Actions workflow:

```yaml
- name: Build Docker image
  run: docker build -t clinigraph-ai-web:latest -f clinigraph-ai/Dockerfile clinigraph-ai/

- name: Container security scan
  run: |
    docker run --rm \
      -v /var/run/docker.sock:/var/run/docker.sock \
      aquasec/trivy:latest image \
      --severity CRITICAL,HIGH \
      --exit-code 1 \
      --no-progress \
      clinigraph-ai-web:latest
```

### Scan a specific tagged image
```powershell
.\scripts\scan-containers.ps1 -Image clinigraph-ai-web:v1.3.0
```

### Export JSON report (for SIEM / audit)
```powershell
.\scripts\scan-containers.ps1 -JsonOutput -OutputFile trivy-report.json
```

### Scan only CRITICAL
```powershell
.\scripts\scan-containers.ps1 -Severity CRITICAL -ExitOnFinding
```

---

## 3. What Trivy Scans

| Scan Type | What It Checks |
|---|---|
| OS packages | Alpine/Debian/Ubuntu packages with known CVEs |
| Python packages | All packages in `site-packages/` against the Python advisory DB |
| Pip-installed packages | Packages from `requirements*.txt` |
| Dockerfile misconfigurations | Root user, exposed secrets, `COPY --chown` inconsistencies |

---

## 4. Fixing Findings

### Python dependency CVE

1. Identify the vulnerable package from the Trivy report.
2. Check the CVE details: `https://nvd.nist.gov/vuln/detail/<CVE-ID>`
3. Update the version pin in `api/requirements-agentai.txt`:
   ```
   somepackage>=X.Y.Z  # CVE-2026-XXXXX fix
   ```
4. Rebuild the image: `docker build -t clinigraph-ai-web:latest .`
5. Re-scan: `.\scripts\scan-containers.ps1`
6. Redeploy: `docker compose -f docker-compose.saas.yml up -d --no-deps web celery-worker`

### OS package CVE (Alpine/Debian base image)

1. Bump the Python base image version in `Dockerfile`:
   ```dockerfile
   FROM python:3.12-slim-bookworm   # pin to latest patch
   ```
2. Rebuild and re-scan.

### Dockerfile misconfiguration

Review the Trivy `config` section output and correct the flagged `Dockerfile` instruction.
Common fixes:
- Do not run as `root` in the final stage — use `USER appuser`.
- Do not `COPY` `.env` or secret files into the image.
- Use `COPY --chown=appuser:appuser` for app files.

---

## 5. Suppressing False Positives

To suppress a known false positive or an accepted risk, create a `.trivyignore` file at
the repo root:

```
# .trivyignore
# Format: <CVE-ID>  # reason
CVE-2025-XXXXX  # Not exploitable — affected code path is not reachable in our runtime
```

Document all suppressions in this file with the reason and a review date.

---

## 6. Scan Schedule

| When | Trigger | Gate |
|---|---|---|
| Local development | `.\scripts\scan-containers.ps1` | Warning only |
| Before every production push | `.\scripts\scan-containers.ps1 -ExitOnFinding` | P0: blocks push |
| Weekly automated scan | GitHub Actions cron schedule | Alert to Slack / SIEM |

### GitHub Actions weekly cron example

```yaml
name: Weekly container scan
on:
  schedule:
    - cron: '0 6 * * 1'   # Every Monday at 06:00 UTC

jobs:
  trivy-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: docker build -t clinigraph-ai-web:latest -f clinigraph-ai/Dockerfile clinigraph-ai/
      - name: Run Trivy scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: clinigraph-ai-web:latest
          format: sarif
          output: trivy-results.sarif
          severity: CRITICAL,HIGH
          exit-code: '1'
      - name: Upload SARIF to GitHub Security tab
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: trivy-results.sarif
```

---

## 7. Maintenance

| Reviewed By | Date | Changes |
|---|---|---|
| Engineering | April 2026 | Initial version — Trivy integration, scan script, CI/CD guide |
