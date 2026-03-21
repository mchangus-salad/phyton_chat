import { appConfig } from '../../app/config';

async function parseResponse(response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
  return response.text();
}

export async function apiGet(path, init = {}) {
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      ...(init.headers || {}),
    },
    ...init,
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
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
    body: JSON.stringify(body ?? {}),
    ...init,
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
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    method: 'PATCH',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
    body: JSON.stringify(body ?? {}),
    ...init,
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
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      ...(init.headers || {}),
    },
    body: formData,
    ...init,
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
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
      ...(init.headers || {}),
    },
    ...init,
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