# Documentation Update Template

Use this template whenever a new feature is added or an existing feature changes.

## 1) Change Metadata

- Date:
- Version (docs):
- Feature name:
- Owner:
- Type of change: New feature | Enhancement | Breaking change | Deprecation | Security update

## 2) Functional Summary

- Problem solved:
- What changed:
- User/business impact:

## 3) API Impact

- New endpoints:
- Updated endpoints:
- Deprecated endpoints:
- Payload changes:
- Response changes:
- Auth/permissions changes:

## 4) Security and Compliance Impact

- PHI/HIPAA impact:
- Data retention impact:
- Audit/logging impact:
- Required client-side controls:

## 5) Operational Impact

- New env vars:
- New scripts/commands:
- Docker/deployment changes:
- Migration required: Yes/No
- Rollback notes:

## 6) Diagram Updates (Mermaid)

Update or add diagrams in:

- [MERMAID_DIAGRAMS.md](MERMAID_DIAGRAMS.md)

Checklist:

- Diagram updated/added
- Mermaid syntax validated
- Diagram preview verified

## 7) Documentation Files To Update

Required:

1. [README.md](../README.md)
2. [AGENT_AI_README.md](AGENT_AI_README.md)
3. [MERMAID_DIAGRAMS.md](MERMAID_DIAGRAMS.md)
4. [CLIENT_MANUAL.md](CLIENT_MANUAL.md)
5. [CLIENT_MANUAL_EN.md](CLIENT_MANUAL_EN.md)

## 8) Client Communication Snippet

- Summary for release notes:
- Action required by client:
- Deadline (if any):

## 9) Manual Version History Row

Add one row to both manual files using this structure:

| Version | Date | Change Summary | Affected Endpoints | Client Action Required |
|---------|------|----------------|--------------------|------------------------|
| x.y.z   | YYYY-MM-DD | ... | ... | Yes/No |
