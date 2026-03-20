import { milestones } from '../data';

export function OperationsPanel({ health }) {
  return (
    <section className="status-panel">
      <div>
        <p className="eyebrow">Current delivery</p>
        <h2>Foundation in place for the full product surface.</h2>
        <p className="status-copy">
          Backend now has a service layer for billing and tenancy workflows, structured logging with request correlation,
          and the frontend is split into app, shared, and feature modules to scale without coupling screens to transport code.
        </p>
        {health.requestId ? <p className="status-meta">Last request id: {health.requestId}</p> : null}
      </div>
      <ul>
        {milestones.map((milestone) => (
          <li key={milestone}>{milestone}</li>
        ))}
      </ul>
    </section>
  );
}