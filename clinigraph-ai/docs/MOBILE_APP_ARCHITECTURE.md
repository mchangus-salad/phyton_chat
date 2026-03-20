# CliniGraph AI Mobile App Architecture

This document defines the baseline architecture for both iOS and Android apps.

## Architecture Decision

- Cross-platform stack: React Native with Expo.
- State strategy: server state with React Query; local UI state by feature.
- Navigation: Expo Router with authenticated and public route groups.
- Security: SecureStore for tokens, OS biometric gate for sensitive sessions, no PHI persisted in plaintext.
- Networking: a shared API client aligned with the web frontend contract and JWT tenant headers.

## Module Boundaries

- `app/`: route entry points and screen composition.
- `features/auth/`: login, refresh, session bootstrap.
- `features/cases/`: patient upload, de-identification summary, case history.
- `features/evidence/`: citation search, filters, saved evidence.
- `features/billing/`: plans, checkout handoff, subscription status.
- `shared/api/`: HTTP client, auth headers, retry policy, typed contracts.
- `shared/storage/`: secure token storage and offline draft queue.
- `shared/ui/`: design system primitives.

## Mobile-Specific Best Practices

- Keep domain logic outside screen files.
- Treat uploads and sync as resumable background tasks.
- Use a write queue for draft case uploads when network is unstable.
- Encrypt any cached sensitive metadata; never cache raw PHI payloads.
- Gate observability by environment and scrub PII before sending logs or crash reports.

## Backend Contract Requirements

- Use `Authorization: Bearer <token>` for user auth.
- Use `X-Tenant-ID` for tenant-scoped calls.
- Preserve `X-Request-ID` returned by the API for support and diagnostics.
- Use paginated endpoints for audit, evidence, and billing history views.

## Initial Delivery Sequence

1. Auth/session bootstrap.
2. Patient-case upload flow.
3. Evidence viewer with citations.
4. Subscription and billing surfaces.
5. Notifications and background sync.