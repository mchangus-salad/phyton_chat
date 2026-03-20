import { apiPost } from '../api/http';
import { appConfig } from '../../app/config';

const runtimeCache = new Map();
const inFlight = new Map();
const translationRequestTimestamps = [];

const MAX_TRANSLATIONS_PER_MINUTE = Math.max(1, appConfig.llmTranslation.maxPerMinute || 20);
const ONE_MINUTE_MS = 60_000;
const RATE_LIMIT_ERROR_CODE = 'LLM_TRANSLATION_RATE_LIMITED';

function keyFor(sourceLocale, targetLocale, text) {
  return `${sourceLocale}:${targetLocale}:${text}`;
}

function normalizeTranslatedText(payload, fallback) {
  if (!payload) {
    return fallback;
  }
  if (typeof payload === 'string') {
    return payload;
  }
  if (typeof payload.answer === 'string' && payload.answer.trim()) {
    return payload.answer.trim();
  }
  if (typeof payload.message === 'string' && payload.message.trim()) {
    return payload.message.trim();
  }
  return fallback;
}

function consumeTranslationBudget() {
  const now = Date.now();

  while (translationRequestTimestamps.length > 0 && now - translationRequestTimestamps[0] > ONE_MINUTE_MS) {
    translationRequestTimestamps.shift();
  }

  if (translationRequestTimestamps.length >= MAX_TRANSLATIONS_PER_MINUTE) {
    const oldest = translationRequestTimestamps[0] || now;
    return {
      allowed: false,
      retryAfterMs: Math.max(250, ONE_MINUTE_MS - (now - oldest)),
    };
  }

  translationRequestTimestamps.push(now);
  return { allowed: true, retryAfterMs: 0 };
}

function createRateLimitError(retryAfterMs) {
  const error = new Error('Runtime translation rate limit reached.');
  error.code = RATE_LIMIT_ERROR_CODE;
  error.retryAfterMs = retryAfterMs;
  return error;
}

export function isRuntimeTranslationRateLimited(error) {
  return Boolean(error && error.code === RATE_LIMIT_ERROR_CODE);
}

export async function translateWithLlm({
  text,
  sourceLocale,
  targetLocale,
  authToken,
  tenantId,
}) {
  if (!text || sourceLocale === targetLocale) {
    return text;
  }

  const cacheKey = keyFor(sourceLocale, targetLocale, text);
  if (runtimeCache.has(cacheKey)) {
    return runtimeCache.get(cacheKey);
  }

  if (inFlight.has(cacheKey)) {
    return inFlight.get(cacheKey);
  }

  const budget = consumeTranslationBudget();
  if (!budget.allowed) {
    throw createRateLimitError(budget.retryAfterMs);
  }

  const prompt = [
    `Translate the following UI text from ${sourceLocale} to ${targetLocale}.`,
    'Return only translated text, no explanation.',
    `Text: ${text}`,
  ].join(' ');

  const requestPromise = apiPost(
    '/agent/query/',
    { question: prompt },
    {
      headers: {
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
      },
    },
  )
    .then((payload) => {
      const translated = normalizeTranslatedText(payload, text);
      runtimeCache.set(cacheKey, translated);
      return translated;
    })
    .catch(() => text)
    .finally(() => {
      inFlight.delete(cacheKey);
    });

  inFlight.set(cacheKey, requestPromise);
  return requestPromise;
}
