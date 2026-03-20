function asNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export const appConfig = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, ''),
  llmTranslation: {
    maxPerMinute: asNumber(import.meta.env.VITE_LLM_TRANSLATION_MAX_PER_MINUTE, 20),
    debounceMs: asNumber(import.meta.env.VITE_LLM_TRANSLATION_DEBOUNCE_MS, 350),
  },
};