import { useI18n } from '../i18n/I18nProvider';

export function LanguageSwitcher() {
  const { locale, setLocale, t, llmTranslationEnabled, setLlmTranslationEnabled } = useI18n();

  return (
    <div className="language-switcher" aria-label={t('ui.changeLanguage')}>
      <label className="language-switcher__locale-row">
        <span className="language-switcher__label">{t('ui.language')}</span>
        <select value={locale} onChange={(event) => setLocale(event.target.value)}>
          <option value="en">{t('ui.english')}</option>
          <option value="es">{t('ui.spanish')}</option>
        </select>
      </label>

      <label className="language-switcher__llm-row">
        <input
          type="checkbox"
          checked={llmTranslationEnabled}
          onChange={(event) => setLlmTranslationEnabled(event.target.checked)}
        />
        <span>{t('ui.llmTranslateLabel')}</span>
      </label>
      <p className="language-switcher__hint">{t('ui.llmTranslateHint')}</p>
    </div>
  );
}
