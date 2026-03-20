import { StatusBadge } from '../../../shared/ui/StatusBadge';

function mapHealthTone(status) {
  if (status === 'ok') {
    return 'success';
  }
  if (status === 'loading' || status === 'idle') {
    return 'neutral';
  }
  return 'danger';
}

function renderHealthLabel(status, framework) {
  if (status === 'ok') {
    return `API healthy${framework ? ` · ${framework}` : ''}`;
  }
  if (status === 'loading') {
    return 'Checking platform health';
  }
  return 'API unavailable';
}

export function HeroSection({ health }) {
  return (
    <section className="hero-panel">
      <div className="hero-heading-row">
        <p className="eyebrow">CliniGraph AI</p>
        <StatusBadge tone={mapHealthTone(health.status)}>
          {renderHealthLabel(health.status, health.framework)}
        </StatusBadge>
      </div>
      <h1>Medical intelligence built for clinical rigor and SaaS scale.</h1>
      <p className="hero-copy">
        This workspace foundation follows a feature-oriented frontend architecture: shared API access,
        isolated UI primitives, and product modules ready for auth, evidence search, billing, and patient-case flows.
      </p>
      <div className="hero-actions">
        <a className="primary-action" href="/api/v1/health/">
          API health
        </a>
        <a className="secondary-action" href="/api/schema/swagger-ui/">
          Swagger UI
        </a>
      </div>
    </section>
  );
}