import { useI18n } from '../../../shared/i18n/I18nProvider';

function buildProductAreas(t) {
  return [
    {
      title: t('platform.area1Title'),
      description: t('platform.area1Description'),
    },
    {
      title: t('platform.area2Title'),
      description: t('platform.area2Description'),
    },
    {
      title: t('platform.area3Title'),
      description: t('platform.area3Description'),
    },
  ];
}

export function PlatformAreasGrid() {
  const { t } = useI18n();
  const productAreas = buildProductAreas(t);

  return (
    <section className="content-grid">
      {productAreas.map((area) => (
        <article className="feature-card" key={area.title}>
          <h2>{area.title}</h2>
          <p>{area.description}</p>
        </article>
      ))}
    </section>
  );
}