import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { translateWithLlm } from './runtimeTranslator';
import { DEFAULT_LOCALE, SUPPORTED_LOCALES, translations } from './translations';

const STORAGE_KEY = 'clinigraph.locale';
const LLM_TRANSLATION_STORAGE_KEY = 'clinigraph.llmTranslationEnabled';

const I18nContext = createContext(null);

function getByPath(obj, path) {
  return path.split('.').reduce((acc, segment) => (acc && acc[segment] !== undefined ? acc[segment] : undefined), obj);
}

function formatTemplate(template, vars) {
  if (!vars) {
    return template;
  }
  return template.replace(/\{\{\s*(\w+)\s*\}\}/g, (_match, key) => {
    const value = vars[key];
    return value === undefined || value === null ? '' : String(value);
  });
}

function safeLocale(candidate) {
  if (SUPPORTED_LOCALES.includes(candidate)) {
    return candidate;
  }
  return DEFAULT_LOCALE;
}

export function I18nProvider({ children }) {
  const [locale, setLocale] = useState(DEFAULT_LOCALE);
  const [llmTranslationEnabled, setLlmTranslationEnabled] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved) {
      setLocale(safeLocale(saved));
      return;
    }

    const browserLanguage = (navigator.language || '').slice(0, 2).toLowerCase();
    setLocale(safeLocale(browserLanguage));
  }, []);

  useEffect(() => {
    const saved = window.localStorage.getItem(LLM_TRANSLATION_STORAGE_KEY);
    if (!saved) {
      return;
    }
    setLlmTranslationEnabled(saved === 'true');
  }, []);

  const changeLocale = useCallback((nextLocale) => {
    const resolved = safeLocale(nextLocale);
    setLocale(resolved);
    window.localStorage.setItem(STORAGE_KEY, resolved);
  }, []);

  const changeLlmTranslationEnabled = useCallback((enabled) => {
    const normalized = Boolean(enabled);
    setLlmTranslationEnabled(normalized);
    window.localStorage.setItem(LLM_TRANSLATION_STORAGE_KEY, String(normalized));
  }, []);

  const t = useCallback(
    (key, vars) => {
      const catalog = translations[locale] || translations[DEFAULT_LOCALE];
      const fallbackCatalog = translations[DEFAULT_LOCALE];
      const localized = getByPath(catalog, key);
      const fallback = getByPath(fallbackCatalog, key);
      const template = localized ?? fallback;

      if (template === undefined) {
        return key;
      }
      if (typeof template !== 'string') {
        return template;
      }
      return formatTemplate(template, vars);
    },
    [locale],
  );

  const translateDynamicText = useCallback(
    async ({ text, authToken, tenantId, sourceLocale }) => {
      return translateWithLlm({
        text,
        sourceLocale: sourceLocale || DEFAULT_LOCALE,
        targetLocale: locale,
        authToken,
        tenantId,
      });
    },
    [locale],
  );

  const value = useMemo(
    () => ({
      locale,
      supportedLocales: SUPPORTED_LOCALES,
      setLocale: changeLocale,
      llmTranslationEnabled,
      setLlmTranslationEnabled: changeLlmTranslationEnabled,
      t,
      translateDynamicText,
    }),
    [changeLocale, changeLlmTranslationEnabled, llmTranslationEnabled, locale, t, translateDynamicText],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within I18nProvider');
  }
  return context;
}
