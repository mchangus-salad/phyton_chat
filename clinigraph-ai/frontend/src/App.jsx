const productAreas = [
  {
    title: 'Clinical Workspace',
    description: 'History-aware medical reasoning, patient-case analysis, and citation-backed answers.',
  },
  {
    title: 'Trust and Compliance',
    description: 'HIPAA-safe de-identification, audit visibility, and tenant-aware access control.',
  },
  {
    title: 'Platform Operations',
    description: 'Billing, abuse telemetry, Prometheus metrics, and an enterprise-ready control plane.',
  },
];

const milestones = [
  'JWT authentication and tenant memberships',
  'Patient-case upload pipeline with PHI redaction',
  'Stripe checkout foundation and plan catalog',
  'Prometheus and Grafana observability stack',
];

export default function App() {
  return (
    <main className="page-shell">
      <section className="hero-panel">
        <p className="eyebrow">CliniGraph AI</p>
        <h1>Medical intelligence built for clinical rigor and SaaS scale.</h1>
        <p className="hero-copy">
          This frontend scaffold is the entry point for the multi-tenant workspace: secure login,
          evidence search, patient-case workflows, subscription management, and operations visibility.
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

      <section className="content-grid">
        {productAreas.map((area) => (
          <article className="feature-card" key={area.title}>
            <h2>{area.title}</h2>
            <p>{area.description}</p>
          </article>
        ))}
      </section>

      <section className="status-panel">
        <div>
          <p className="eyebrow">Current delivery</p>
          <h2>Foundation in place for the full product surface.</h2>
        </div>
        <ul>
          {milestones.map((milestone) => (
            <li key={milestone}>{milestone}</li>
          ))}
        </ul>
      </section>
    </main>
  );
}
