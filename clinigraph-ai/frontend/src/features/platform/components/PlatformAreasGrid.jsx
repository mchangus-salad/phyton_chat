import { productAreas } from '../data';

export function PlatformAreasGrid() {
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