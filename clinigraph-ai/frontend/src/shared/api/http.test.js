import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiGet, apiPost } from './http';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a minimal Response-like object that fetch() would return. */
function mockResponse({ status = 200, body = {}, contentType = 'application/json' } = {}) {
  const responseBody =
    typeof body === 'string' ? body : JSON.stringify(body);

  return new Response(responseBody, {
    status,
    headers: { 'Content-Type': contentType },
  });
}

// ---------------------------------------------------------------------------
// Setup: stub fetch globally and reset between tests
// ---------------------------------------------------------------------------

const originalFetch = globalThis.fetch;

beforeEach(() => {
  globalThis.fetch = vi.fn();
  // Stub appConfig so the module resolves without the React app context.
  vi.doMock('../../app/config', () => ({ appConfig: { apiBaseUrl: 'http://localhost:8000' } }));
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// apiGet
// ---------------------------------------------------------------------------

describe('apiGet', () => {
  it('sends a GET request to the full path', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ body: { status: 'ok' } }));
    await apiGet('/api/v1/health/');
    expect(globalThis.fetch).toHaveBeenCalledOnce();
    const [url, init] = globalThis.fetch.mock.calls[0];
    expect(url).toContain('/api/v1/health/');
    expect(init.method).toBe('GET');
  });

  it('returns parsed JSON on success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ body: { answer: 'hello' } }));
    const result = await apiGet('/api/v1/agent/query/');
    expect(result.answer).toBe('hello');
  });

  it('throws an error with status and payload on 4xx', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockResponse({ status: 401, body: { detail: 'Unauthorized' } }));
    await expect(apiGet('/api/v1/agent/query/')).rejects.toMatchObject({
      status: 401,
      payload: { detail: 'Unauthorized' },
    });
  });

  it('returns plain text when response is not JSON', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockResponse({ body: 'plain text', contentType: 'text/plain' }));
    const result = await apiGet('/api/v1/health/');
    expect(result).toBe('plain text');
  });
});

// ---------------------------------------------------------------------------
// apiPost
// ---------------------------------------------------------------------------

describe('apiPost', () => {
  it('sends a POST request with JSON body', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ body: { answer: 'clinical' } }));
    await apiPost('/api/v1/agent/query/', { question: 'What is HFrEF?' });

    const [, init] = globalThis.fetch.mock.calls[0];
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ question: 'What is HFrEF?' });
    expect(init.headers['Content-Type']).toBe('application/json');
  });

  it('returns parsed JSON on success', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockResponse({ body: { subscription_id: 42 } }));
    const result = await apiPost('/api/v1/billing/subscriptions/cancel/', { immediately: false });
    expect(result.subscription_id).toBe(42);
  });

  it('throws with status on 5xx', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockResponse({ status: 500, body: { detail: 'Server error' } }));
    await expect(apiPost('/api/v1/agent/query/', { question: 'test' })).rejects.toMatchObject({
      status: 500,
    });
  });

  it('serialises an empty body when body is null', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({}));
    await apiPost('/api/v1/billing/usage/ingest/', null);
    const [, init] = globalThis.fetch.mock.calls[0];
    expect(init.body).toBe('{}');
  });
});
