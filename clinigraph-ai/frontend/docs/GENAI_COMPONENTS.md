# GenAI/LLM Frontend Components - Error Handling Guide

## Overview

The GenAI/LLM frontend components have been hardened with comprehensive error handling to inform users about subscription status, permissions, and other issues. All endpoints now properly handle and display HTTP error codes including **402 Payment Required** when tenant subscriptions are not active.

The frontend now also includes:
- UI localization with **English (default)** and **Spanish**.
- A global language switcher for instant UI language changes.
- An optional **AI translation toggle** for dynamic GenAI response text and citations.
- Runtime translation safeguards: debounce and per-minute request limiting.

## Components

### 1. AgentQueryPanel
- **File**: `frontend/src/features/platform/components/AgentQueryPanel.jsx`
- **Hook**: `useAgentQuery.js`
- **Endpoint**: `POST /api/v1/agent/query/`
- **Purpose**: General-purpose medical intelligence queries

### 2. OncologyQueryPanel
- **File**: `frontend/src/features/platform/components/OncologyQueryPanel.jsx`
- **Hook**: `useOncologyQuery.js`
- **Endpoint**: `POST /api/v1/agent/oncology/query/`
- **Purpose**: Oncology-focused research queries

### 3. MedicalQueryPanel
- **File**: `frontend/src/features/platform/components/MedicalQueryPanel.jsx`
- **Hook**: `useMedicalQuery.js`
- **Endpoint**: `POST /api/v1/agent/medical/query/`
- **Purpose**: Domain-scoped medical knowledge queries (cardiology, neurology, etc.)

### 4. PatientCaseAnalyzePanel
- **File**: `frontend/src/features/platform/components/PatientCaseAnalyzePanel.jsx`
- **Hook**: `usePatientCaseAnalyze.js`
- **Endpoint**: `POST /api/v1/agent/patient/analyze/`
- **Purpose**: Patient case analysis with PHI redaction

## Error Handling Strategy

Each component uses a custom hook that implements consistent error handling with the following HTTP status codes:

### HTTP 401 - Unauthorized
- **Cause**: User is not authenticated or token is invalid
- **User Message**: "Authentication failed. Please log in again."
- **Action**: Link to login page

### HTTP 402 - Payment Required ⚠️ **CRITICAL**
- **Cause**: Tenant subscription is not active (CANCELED, INCOMPLETE, PAST_DUE beyond grace period)
- **User Message**: "Your subscription is not active. Please update your subscription to use this feature."
- **Special Styling**: Yellow/orange alert with payment emphasis
- **Action**: Link to billing/subscription management page
- **Fields Disabled**: All form inputs are disabled until subscription is active

### HTTP 403 - Forbidden
- **Cause**: User lacks required role or permissions for the tenant
- **User Message**: "You do not have permission to access this feature."
- **Action**: Contact tenant administrator
- **Note**: Non-billing roles (clinician, owner, admin) are required for LLM endpoints

### HTTP 429 - Rate Limited
- **Cause**: User has made too many requests
- **User Message**: "Too many requests. Please wait a moment and try again."
- **Action**: Automatic retry suggested

### HTTP 400 - Bad Request
- **Cause**: Invalid input (missing domain, malformed question, invalid file)
- **User Message**: Displays specific validation error from backend
- **Action**: User corrects input

### HTTP 500+ - Server Error
- **Cause**: Backend service failure
- **User Message**: "Server error. Please try again later."
- **Action**: Retry or contact support

## State Management

Each hook implements a state machine with the following statuses:

```javascript
{
  status: 'idle' | 'loading' | 'success' | 'error',
  data: null | ResponseObject,
  error: null | ErrorMessage,
  errorCode: null | HttpStatusCode
}
```

## Component Features

### Localization and Runtime Translation
- Static UI text uses local dictionaries (`translations.js`) for instant language switching.
- Dynamic LLM response text can be translated via optional runtime translation.
- Dynamic citations can also be translated when runtime translation is enabled.
- Runtime translation is disabled by default and can be enabled from the language switcher.

### Runtime Translation Safeguards
- **Debounce**: translation requests are delayed by ~350ms to reduce burst traffic.
- **Rate limit**: runtime translation helper allows up to 20 translation requests per minute.
- **Caching**: repeated source/target text pairs are returned from cache.
- **In-flight dedupe**: concurrent translation calls for the same text are deduplicated.
- **User notice**: when translation rate limit is hit, UI shows a non-blocking notice and falls back to original text.

Configuration via environment variables:
- `VITE_LLM_TRANSLATION_MAX_PER_MINUTE` (default `20`)
- `VITE_LLM_TRANSLATION_DEBOUNCE_MS` (default `350`)
- Use `.env.example` as the baseline template for local/staging setup.

These controls reduce latency spikes and cost in edge cases where users frequently switch languages.

### Authentication
All components require:
- **JWT Bearer Token**: Paste authentication token in token field
- **Tenant ID** (optional): Specify tenant if user has access to multiple tenants
- Headers are automatically set: `Authorization: Bearer <token>`, `X-Tenant-ID: <id>`

### Loading State
While requests are loading:
- All form inputs are disabled
- Button text changes to indicate processing ("Searching...", "Analyzing...", etc.)
- User cannot submit duplicate requests

### Success Display
On success (HTTP 200):
- Response is displayed in a green success alert
- Citations/evidence sources are shown (if available)
- For patient case analysis, PHI redaction summary is included
- Form is automatically cleared for next query

### Error Display
On error:
- Alert appears with HTTP status code
- Error message clearly explains the issue
- Action link is provided (login, upgrade, manage subscription, etc.)
- For 402 errors specifically:
  - Alert has special yellow/orange styling
  - "Manage Subscription" or "Upgrade Subscription" button is prominent
  - Form inputs remain visible but disabled

## CSS Classes

### Alert Styling
- `.alert` - Base alert styles
- `.alert-error` - Error alert (red)
- `.alert-success` - Success alert (green)
- `.alert-payment-required` - Special styling for HTTP 402 (orange/yellow)

### Form Elements
- `.form-section` - Container for related form fields
- `.form-group` - Individual field with label
- `.toggle-group` - Toggle button group (text vs file input)
- `.toggle-btn` / `.toggle-btn.active` - Toggle button state

### Response Display
- `.response-content` - Container for API response
- `.citations` - Evidence sources list
- `.phi-notice` - PHI redaction notice (patient case)

## Usage Example

```jsx
import { AgentQueryPanel } from './features/platform/components/AgentQueryPanel';

export function MyApp() {
  return (
    <div className="page-shell">
      <AgentQueryPanel />
    </div>
  );
}
```

## Testing Error Scenarios

### Test 402 Payment Required
1. Create a test user in a tenant with CANCELED subscription
2. Paste JWT token and Tenant ID
3. Submit a query
4. Expected: Orange alert with message "Your subscription is not active..."
5. Expected: "Manage Subscription" link appears

### Test 401 Unauthorized
1. Paste an invalid or expired JWT token
2. Submit a query
3. Expected: Red alert with message "Authentication failed..."
4. Expected: "Log In" link appears

### Test 403 Forbidden
1. Create a test user with only billing role
2. Submit a query to agent endpoint
3. Expected: Red alert with permission denial message
4. Expected: Contact administrator notice appears

### Test Successful Query
1. Create test user with active subscription
2. Paste valid JWT and Tenant ID
3. Submit a query
4. Expected: Green success alert with response
5. Expected: Citations appear if available

## Backend Entitlement Integration

The frontend components automatically respect the backend's entitlement checks:

- **HasLlmAccessOrApiKey permission** (on all 4 endpoints)
  - Chains `IsTenantClinicianOrAbove` + `HasActiveEntitlement`
  - Validates tenant membership exists
  - Validates subscription status (ACTIVE, TRIALING, or PAST_DUE within grace period)
  - Returns 402 if subscription is invalid

- **X-Tenant-ID Header**
  - Required for JWT authentication on LLM endpoints
  - Optional if user belongs to default tenant
  - Automatically included by all components

## Form Validation

### Client-Side Validation
- Checks for missing authentication token before submit
- Checks for empty/whitespace-only questions
- Validates file selection for file uploads
- Prevents duplicate submissions while loading

### Server-Side Validation
- Backend validates all input fields
- Returns 400 with specific error details
- Frontend displays detailed validation errors

## Performance Considerations

- Components use React hooks for state management (useState, useEffect)
- No unnecessary re-renders with proper dependency arrays
- Form inputs are only disabled during loading (proper UX feedback)
- Errors are retained until user submits new request
- No polling - all requests are explicit user actions
- Runtime translation adds network latency only when enabled
- Debounce, cache, and request limiting are applied to runtime translation calls

## Accessibility

- All form fields have associated labels
- Error messages are semantic and descriptive
- Loading states are clearly indicated
- Alert styling uses color + icons/text (not color alone)
- Form inputs are disabled during loading (prevents accidental double-clicks)
- Links have proper contrast and hover states

## Integration with Billing

When a 402 Payment Required error occurs:
1. "Manage Subscription" or "Upgrade Subscription" link is provided
2. Link should redirect to billing page (e.g., `/billing`)
3. Billing page should show subscription status and upgrade options
4. After subscription is updated, user can retry the query

## Common Patterns

### Using useAgentQuery Hook

```jsx
import { useAgentQuery } from '../hooks/useAgentQuery';

function MyComponent() {
  const { status, data, error, errorCode, query } = useAgentQuery();
  
  const handleSubmit = async (question) => {
    try {
      const result = await query(question, authToken, tenantId);
      // Handle success
    } catch {
      // Error is already in state - render accordingly
    }
  };
  
  return (
    <>
      {status === 'loading' && <p>Loading...</p>}
      {status === 'error' && <ErrorAlert error={error} code={errorCode} />}
      {status === 'success' && <SuccessDisplay data={data} />}
    </>
  );
}
```

## Troubleshooting

### Components Not Showing Error Messages
- Check that JWT token is provided
- Check browser console for network errors
- Verify API endpoint is correct (check `appConfig.apiBaseUrl`)

### 402 Not Appearing for Canceled Subscription
- Verify subscription status in database is CANCELED or INCOMPLETE
- Check that X-Tenant-ID header is being sent
- Verify user has valid membership in that tenant

### Forms Remain Disabled After Error
- This is expected - user must address the error and retry
- 402 errors specifically disable inputs to prevent work loss
- User must update subscription to re-enable inputs

### Files Not Uploading for Patient Case
- Check file size (should be reasonable - backend may have limits)
- Check file type is .pdf, .txt, .doc, .docx
- Verify formData is being constructed correctly in hook

---

**Last Updated**: March 2026  
**Version**: 1.0.0  
**Author**: Development Team
