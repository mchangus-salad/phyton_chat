import { useEffect, useState } from 'react';

import { useI18n } from './I18nProvider';
import { appConfig } from '../../app/config';
import { isRuntimeTranslationRateLimited } from './runtimeTranslator';

const TRANSLATION_DEBOUNCE_MS = Math.max(50, appConfig.llmTranslation.debounceMs || 350);

export function useRuntimeTranslation({
  text,
  authToken,
  tenantId,
  sourceLocale = 'en',
}) {
  const { locale, llmTranslationEnabled, translateDynamicText } = useI18n();
  const [translatedText, setTranslatedText] = useState(text || '');
  const [translating, setTranslating] = useState(false);
  const [rateLimited, setRateLimited] = useState(false);
  const [retryAfterSeconds, setRetryAfterSeconds] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timeoutId;

    async function run() {
      if (!text) {
        setTranslatedText('');
        setRateLimited(false);
        setRetryAfterSeconds(0);
        return;
      }

      if (!llmTranslationEnabled || locale === sourceLocale) {
        setTranslatedText(text);
        setRateLimited(false);
        setRetryAfterSeconds(0);
        return;
      }

      setTranslating(true);
      try {
        const result = await translateDynamicText({
          text,
          authToken,
          tenantId,
          sourceLocale,
        });
        if (!cancelled) {
          setTranslatedText(result || text);
          setRateLimited(false);
          setRetryAfterSeconds(0);
        }
      } catch (error) {
        if (!cancelled) {
          setTranslatedText(text);
          if (isRuntimeTranslationRateLimited(error)) {
            setRateLimited(true);
            setRetryAfterSeconds(Math.max(1, Math.ceil((error.retryAfterMs || 1000) / 1000)));
          }
        }
      } finally {
        if (!cancelled) {
          setTranslating(false);
        }
      }
    }

    timeoutId = setTimeout(run, TRANSLATION_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [authToken, locale, llmTranslationEnabled, sourceLocale, tenantId, text, translateDynamicText]);

  return { translatedText, translating, rateLimited, retryAfterSeconds };
}

export function useRuntimeTranslationList({
  texts,
  authToken,
  tenantId,
  sourceLocale = 'en',
}) {
  const { locale, llmTranslationEnabled, translateDynamicText } = useI18n();
  const [translatedTexts, setTranslatedTexts] = useState(texts || []);
  const [translating, setTranslating] = useState(false);
  const [rateLimited, setRateLimited] = useState(false);
  const [retryAfterSeconds, setRetryAfterSeconds] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timeoutId;

    async function run() {
      if (!Array.isArray(texts) || texts.length === 0) {
        setTranslatedTexts([]);
        setRateLimited(false);
        setRetryAfterSeconds(0);
        return;
      }

      if (!llmTranslationEnabled || locale === sourceLocale) {
        setTranslatedTexts(texts);
        setRateLimited(false);
        setRetryAfterSeconds(0);
        return;
      }

      setTranslating(true);
      try {
        let listWasRateLimited = false;
        let maxRetryAfterMs = 0;

        const results = await Promise.all(
          texts.map(async (text) => {
            if (!text) {
              return text;
            }

            try {
              return await translateDynamicText({
                text,
                authToken,
                tenantId,
                sourceLocale,
              });
            } catch (error) {
              if (isRuntimeTranslationRateLimited(error)) {
                listWasRateLimited = true;
                maxRetryAfterMs = Math.max(maxRetryAfterMs, error.retryAfterMs || 1000);
              }
              return text;
            }
          }),
        );

        if (!cancelled) {
          setTranslatedTexts(results);
          setRateLimited(listWasRateLimited);
          setRetryAfterSeconds(listWasRateLimited ? Math.max(1, Math.ceil(maxRetryAfterMs / 1000)) : 0);
        }
      } finally {
        if (!cancelled) {
          setTranslating(false);
        }
      }
    }

    timeoutId = setTimeout(run, TRANSLATION_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [authToken, locale, llmTranslationEnabled, sourceLocale, tenantId, texts, translateDynamicText]);

  return { translatedTexts, translating, rateLimited, retryAfterSeconds };
}
