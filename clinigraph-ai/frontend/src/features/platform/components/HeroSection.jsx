import { StatusBadge } from '../../../shared/ui/StatusBadge';
import { useI18n } from '../../../shared/i18n/I18nProvider';

function mapHealthTone(status) {
  if (status === 'ok') {
    return 'success';
  }
  if (status === 'loading' || status === 'idle') {
    return 'neutral';
  }
  return 'danger';
}

function renderHealthLabel(status, framework, t) {
  if (status === 'ok') {
    return `${t('hero.healthy')}${framework ? ` · ${framework}` : ''}`;
  }
  if (status === 'loading') {
    return t('hero.checking');
  }
  return t('hero.unavailable');
}

export function HeroSection({ health }) {
  const { t } = useI18n();

  return (
    <section className="hero-panel">
      <div className="hero-heading-row">
        <p className="eyebrow">{t('hero.brand')}</p>
        <StatusBadge tone={mapHealthTone(health.status)}>
          {renderHealthLabel(health.status, health.framework, t)}
        </StatusBadge>
      </div>
      <h1>{t('hero.title')}</h1>
      <p className="hero-copy">{t('hero.copy')}</p>
      <div className="hero-actions">
        <a className="primary-action" href="/api/v1/health/">
          {t('hero.apiHealth')}
        </a>
        <a className="secondary-action" href="/api/schema/swagger-ui/">
          {t('hero.swagger')}
        </a>
      </div>
    </section>
  );
}