import Link from "next/link";

export default function HomePage() {
  return (
    <section className="page-section">
      <p className="eyebrow">A paleobiology atlas</p>
      <h1>The fossil record,<br />in context.</h1>
      <p>PaleoGraph is taking shape as a place to explore fossils through time, geography, and the collections that preserve them.</p>
      <Link className="text-link" href="/explore">Explore PaleoGraph <span aria-hidden="true">→</span></Link>
    </section>
  );
}
