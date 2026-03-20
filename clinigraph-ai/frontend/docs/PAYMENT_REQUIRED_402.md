# Payment Required (402) Error Handling - Best Practices

## Overview

The 402 Payment Required HTTP status code is critical for SaaS platforms. In CliniGraph AI, this error indicates that a tenant's subscription is not active and users cannot access GenAI/LLM features. This guide provides best practices for handling 402 errors on the frontend.

## When 402 is Returned

The backend returns HTTP 402 when:

1. **Subscription Status**:
   - Status is `CANCELED` (subscription ended/cancelled)
   - Status is `INCOMPLETE` (payment incomplete)
   - Status is `PAST_DUE` and grace period has expired
   - No subscription exists for the tenant

2. **Request Context**:
   - User attempts any LLM/GenAI endpoint (agent_query, medical_query, etc.)
   - User is authenticated (JWT token is valid)
   - User has valid membership in the tenant (role is clinician, admin, or owner)
   - But tenant's subscription is not valid

## Frontend Handling

### Localization Context

- 402 messages are localized through the frontend i18n catalog (EN/ES).
- Static error UI updates instantly on language change.
- If runtime translation toggle is enabled, dynamic LLM response text and citations are translated asynchronously.
- Runtime translation is protected with debounce and per-minute request limits to avoid excessive translation calls.
- When runtime translation limit is reached, the UI shows a soft warning and keeps original (non-translated) text to avoid blocking the clinical workflow.

### Error Detection

```javascript
// In hooks/useAgentQuery.js (or similar)
if (errorCode === 402) {
  errorMessage = 'Your subscription is not active. Please update...';
}
```

### Visual Distinction

```css
.alert.alert-payment-required {
  background: linear-gradient(135deg, rgba(241, 192, 45, 0.15), rgba(255, 152, 0, 0.1));
  border-left-color: #f9a825;
  color: #7a4419;
}
```

**Why this styling?**
- Yellow/orange = warning/billing status (not generic error)
- User immediately recognizes it's subscription-related
- Distinct from 403 (permission) or 401 (authentication)
- Aligns with industry standards for payment errors

### Action Links

Always provide clear next steps:

```jsx
{isSubscriptionError && (
  <div className="alert-actions">
    <a href="/billing" className="action-link">
      Manage Subscription
    </a>
  </div>
)}
```

**Link destination should**:
- Show current subscription status
- Display payment method
- Offer plan upgrade options
- Allow subscription renewal if canceled
- Show grace period status if applicable

### Form Input Handling

**Do NOT disable all inputs on 402 error** - but DO provide clear guidance:

Option 1: Keep form visible but show prominent warning
```jsx
{isSubscriptionError && (
  <div className="alert alert-payment-required">
    <strong>Subscription Required</strong>
    <p>Your subscription is currently inactive...</p>
    <a href="/billing">Update Your Subscription</a>
  </div>
)}

{/* Form remains visible for viewing/copying data */}
<form onSubmit={handleSubmit}>
  <textarea value={question} disabled={status === 'loading'} />
  <button disabled={isSubscriptionError || status === 'loading'}>
    {isSubscriptionError ? 'Subscription Required' : 'Submit'}
  </button>
</form>
```

Option 2: Disable inputs explicitly after 402
```jsx
<textarea 
  value={question} 
  disabled={status === 'loading' || isSubscriptionError}
/>
```

**Recommendation**: Option 1 is better UX because:
- User can review and copy their work
- Button text clearly indicates issue
- User doesn't feel "locked out"
- No need to re-enter data after subscription update

## Implementation Checklist

- [ ] Hook detects 402 status code
- [ ] Error message explains subscription is inactive
- [ ] Alert has payment-required styling (yellow/orange)
- [ ] "Manage Subscription" or "Upgrade Subscription" link present
- [ ] Link URL is correct (`/billing` or similar)
- [ ] Button shows loading state during request
- [ ] Form inputs remain visible even on error
- [ ] If inputs are disabled, reason is clear from button/alert text

## Testing Checklist

### Setup
```bash
# 1. Create test user in canceled tenant
User: testuser@example.com
Tenant: test-tenant (with CANCELED subscription)

# 2. Get JWT token
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass"}'

# 3. Copy token and tenant ID
```

### Test Cases

**TC-402-001: Display Payment Required Error**
1. Open AgentQueryPanel
2. Paste JWT token from canceled tenant
3. Enter tenant ID
4. Enter a test question
5. Click "Submit Query"
6. **Expected**: 
   - Alert displays: "Your subscription is not active..."
   - Background color is yellow/orange
   - "Manage Subscription" button is visible
   - HTTP 402 is shown

**TC-402-002: Form Remains Accessible**
1. Complete TC-402-001
2. Observe form inputs
3. **Expected**:
   - Question textarea is still visible (not removed)
   - Can copy question text for later use
   - Button shows clear message about subscription requirement
   - Can update token field if switching users

**TC-402-003: Recover After Subscription Update**
1. Open two browser tabs
2. Tab A: AgentQueryPanel showing 402 error
3. Tab B: Billing page - activate subscription for tenant
4. Go back to Tab A
5. Click "Manage Subscription" link
6. After subscription activated, navigate back
7. Retry query with same token
8. **Expected**:
   - Query succeeds (200 OK)
   - Success alert appears
   - Response is displayed

**TC-402-004: Different Tenant Shows Different Status**
1. User has access to 2 tenants
2. Tenant A: Active subscription ✅
3. Tenant B: Canceled subscription ❌
4. Query with Tenant A ID
5. **Expected**: Success
6. Query with Tenant B ID
7. **Expected**: 402 Payment Required error

## Grace Period Handling

**Important**: PAST_DUE subscriptions within grace period should NOT return 402.

Grace period flow:
- Subscription.status = `PAST_DUE`
- `grace_period_ends_at` is set to future date
- User attempts LLM query
- **Expected**: 200 OK (succeeds with optional warning)
- Grace period gives user time to resolve payment

If grace period expires without payment:
- `grace_period_ends_at` passes
- Next LLM query returns **402 Payment Required**
- User must update subscription immediately

## Database Verification

To verify subscription state:

```sql
-- Check subscription status
SELECT id, status, grace_period_ends_at, updated_at 
FROM billings_subscription 
WHERE tenant_id = '<tenant_id>'
ORDER BY updated_at DESC;

-- Expected output
id | status    | grace_period_ends_at | reason
---+-----------+----------------------+--------
1  | CANCELED  | NULL                 | Grace period not applicable for CANCELED
2  | PAST_DUE  | 2026-04-20 00:00:00  | Grace period active - should NOT return 402 yet
3  | INCOMPLETE| NULL                 | Immediately blocking - returns 402
```

## Error Message Localization

For multi-language support, errors should be translated:

```javascript
// English
'Your subscription is not active. Please update your subscription to use this feature.'

// Spanish
'Tu suscripción no está activa. Por favor actualiza tu suscripción para usar esta función.'

// French
'Votre abonnement n\'est pas actif. Veuillez mettre à jour votre abonnement...'
```

Store in translation files, not inline.

## Monitoring and Alerts

Track 402 errors in analytics:

```javascript
// Example: Sentry/error tracking
if (errorCode === 402) {
  captureException(new Error('Rate Limited - LLM Access'), {
    tags: {
      'payment.status': 'inactive',
      'endpoint': '/agent/query/',
      'user.tenant': tenantId,
    },
    level: 'warning', // Not critical - expected behavior
  });
}
```

## Related Endpoints

LLM endpoints that return 402:
- `POST /api/v1/agent/query/` - General agent query
- `POST /api/v1/agent/medical/query/` - Medical query
- `POST /api/v1/agent/medical/train/` - Medical training
- `POST /api/v1/agent/oncology/query/` - Oncology query
- `POST /api/v1/agent/oncology/train/` - Oncology training
- `POST /api/v1/agent/patient/analyze/` - Patient case analysis

## Links to Related Docs

- [GenAI Components Guide](./GENAI_COMPONENTS.md) - Full component documentation
- [Backend Error Handling](../docs/API_ERRORS.md) - Server-side error codes
- [Billing API Guide](../docs/BILLING_GUIDE.md) - Subscription management
- [Entitlement Service](../docs/ENTITLEMENT_SERVICE.md) - Subscription logic

---

**Last Updated**: March 2026  
**Version**: 1.0.0  
**Critical Component**: Yes - Payment handling is critical for SaaS
