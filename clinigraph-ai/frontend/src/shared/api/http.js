import { appConfig } from '../../app/config';

async function parseResponse(response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
  return response.text();
}

export async function apiGet(path, init = {}) {
  const { headers: initHeaders = {}, ...restInit } = init;
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    ...restInit,
    method: 'GET',
    headers: {
      Accept: 'application/json',
      ...initHeaders,
    },
  });

  const payload = await parseResponse(response);
  if (!response.ok) {
    const error = new Error(`API request failed with status ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export async function apiPost(path, body, init = {}) {
  const { headers: initHeaders = {}, ...restInit } = init;
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    ...restInit,
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...initHeaders,
    },
    body: JSON.stringify(body ?? {}),
  });

  const payload = await parseResponse(response);
  if (!response.ok) {
    const error = new Error(`API request failed with status ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export async function apiPatch(path, body, init = {}) {
  const { headers: initHeaders = {}, ...restInit } = init;
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    ...restInit,
    method: 'PATCH',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...initHeaders,
    },
    body: JSON.stringify(body ?? {}),
  });

  const payload = await parseResponse(response);
  if (!response.ok) {
    const error = new Error(`API request failed with status ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export async function apiPostFormData(path, formData, init = {}) {
  const { headers: initHeaders = {}, ...restInit } = init;
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    ...restInit,
    method: 'POST',
    headers: {
      Accept: 'application/json',
      ...initHeaders,
    },
    body: formData,
  });

  const payload = await parseResponse(response);
  if (!response.ok) {
    const error = new Error(`API request failed with status ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export async function apiDelete(path, init = {}) {
  const { headers: initHeaders = {}, ...restInit } = init;
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    ...restInit,
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
      ...initHeaders,
    },
  });

  const payload = await parseResponse(response);
  if (!response.ok) {
    const error = new Error(`API request failed with status ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export async function apiPostNdjson(path, body, init = {}) {
  const { headers: initHeaders = {}, onEvent, ...restInit } = init;
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    ...restInit,
    method: 'POST',
    headers: {
      Accept: 'application/x-ndjson, application/json',
      'Content-Type': 'application/json',
      ...initHeaders,
    },
    body: JSON.stringify(body ?? {}),
  });

  if (!response.ok) {
    const payload = await parseResponse(response);
    const error = new Error(`API request failed with status ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  if (!response.body) {
    const payload = await parseResponse(response);
    if (onEvent && payload && typeof payload === 'object') {
      onEvent({ event: 'done', ...payload });
    }
    return payload;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let donePayload = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) continue;

      try {
        const event = JSON.parse(line);
        if (onEvent) onEvent(event);

        if (event.event === 'done') {
          donePayload = event;
        }
        if (event.event === 'error') {
          const error = new Error(event.error || 'Streaming request failed');
          error.status = 500;
          error.payload = event;
          throw error;
        }
      } catch (err) {
        if (err?.status) throw err;
      }
    }
  }

  if (buffer.trim()) {
    try {
      const event = JSON.parse(buffer.trim());
      if (onEvent) onEvent(event);
      if (event.event === 'done') {
        donePayload = event;
      }
    } catch {
      // Ignore trailing partial/invalid line.
    }
  }

  return donePayload || { event: 'done', answer: '' };
}