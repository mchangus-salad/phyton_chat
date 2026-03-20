import { useI18n } from '../../../shared/i18n/I18nProvider';

function buildMilestones(t) {
  return [
    t('platform.milestone1'),
    t('platform.milestone2'),
    t('platform.milestone3'),
    t('platform.milestone4'),
  ];
}

export function OperationsPanel({ health }) {
  const { t } = useI18n();
  const milestones = buildMilestones(t);

  return (
    <section className="status-panel">
      <div>
        <p className="eyebrow">{t('platform.currentDelivery')}</p>
        <h2>{t('platform.foundation')}</h2>
        <p className="status-copy">{t('platform.foundationCopy')}</p>
        {health.requestId ? (
          <p className="status-meta">
            {t('platform.lastRequestId')}: {health.requestId}
          </p>
        ) : null}
      </div>
      <ul>
        {milestones.map((milestone) => (
          <li key={milestone}>{milestone}</li>
        ))}
      </ul>
    </section>
  );
}