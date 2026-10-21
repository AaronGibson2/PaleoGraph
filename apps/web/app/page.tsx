import Link from "next/link";
import { HomeContext } from "../features/explore/HomeContext";
import { NavigationIcon } from "../features/explore/NavigationIcon";
import "./home-experience.css";

export default function HomePage() {
  return <div className="home-atlas home-experience">
    <section className="home-field" aria-labelledby="home-title">
      <div className="home-introduction">
        <p className="eyebrow">An open field atlas / Florida</p>
        <h1 id="home-title">Life,<br /><em>recorded.</em></h1>
        <p className="home-statement">Explore the fossil record through place, deep time, and the evidence we keep.</p>
        <form className="home-search" action="/explore" role="search" aria-label="Search the evidence archive">
          <label className="sr-only" htmlFor="home-query">Search taxa, places or catalog identifiers</label>
          <input id="home-query" name="q" type="search" maxLength={160} placeholder="A taxon, a place, a catalog number..." />
          <input type="hidden" name="source" value="all" />
          <button type="submit" aria-label="Search the archive"><span aria-hidden="true">&#8599;</span></button>
        </form>
        <p className="home-search-note">Source records stay distinct. Uncertainty stays visible.</p>
      </div>
      <div className="home-plate" aria-label="Illustrative animal silhouette with abstract geography, classification and time layers; not a specimen image or scientific reconstruction" role="img">
        <div className="home-plate-grid" />
        <svg className="home-plate-lines" viewBox="0 0 560 500" fill="none" aria-hidden="true">
          <g className="home-map-layer" stroke="currentColor" strokeWidth=".7"><path d="M-20 190C90 70 160 115 270 54S460 90 590-10M-20 220C90 100 160 145 270 84S460 120 590 20M-20 250C90 130 160 175 270 114S460 150 590 50M-20 280C90 160 160 205 270 144S460 180 590 80M-20 310C90 190 160 235 270 174S460 210 590 110" /></g>
          <g className="home-classification-layer" stroke="currentColor"><path d="M75 105V375H470M75 170H174M75 300H145M365 375V310M445 375V425" /><circle cx="75" cy="105" r="4"/><circle cx="174" cy="170" r="4"/><circle cx="145" cy="300" r="4"/><circle cx="365" cy="310" r="4"/><circle cx="445" cy="425" r="4"/></g>
          <circle className="home-plate-ring" cx="280" cy="245" r="164" stroke="currentColor" strokeWidth=".7" /><circle className="home-plate-ring home-plate-ring-inner" cx="280" cy="245" r="145" stroke="currentColor" strokeWidth=".4" />
        </svg>
        <span className="home-plate-label">FLORIDA / THE EVIDENCE ATLAS</span><span className="home-specimen-silhouette" aria-hidden="true" />
        <span className="home-plate-axis axis-geography">01 / Place</span><span className="home-plate-axis axis-classification">02 / Classification</span><span className="home-plate-axis axis-time">03 / Deep time</span>
        <div className="home-strata" aria-hidden="true">{Array.from({ length: 7 }, (_, index) => <i key={index} />)}</div>
        <p className="home-plate-caption">An illustrative form. A network of evidence.<br /><small>Silhouette only / not a specimen photograph</small></p>
      </div>
    </section>
    <nav className="home-destinations" aria-label="Choose an exploration destination">
      <Link className="home-destination home-destination-atlas" href="/explore"><span className="destination-number">01 / Geography</span><NavigationIcon kind="atlas" /><strong>Atlas</strong><p>Find evidence in place.</p><span className="destination-arrow" aria-hidden="true">&#8599;</span></Link>
      <Link className="home-destination home-destination-catalog" href="/explore?catalog=open"><span className="destination-number">02 / Material</span><NavigationIcon kind="catalog" /><strong>Catalog</strong><p>Read the source record.</p><span className="destination-arrow" aria-hidden="true">&#8599;</span></Link>
      <Link className="home-destination home-destination-lineage" href="/lineage"><span className="destination-number">03 / Classification</span><NavigationIcon kind="lineage" /><strong>Lineage</strong><p>Follow a taxonomic branch.</p><span className="destination-arrow" aria-hidden="true">&#8599;</span></Link>
    </nav>
    <HomeContext />
    <footer className="home-credit">UFVP museum data &middot; CC BY-NC 4.0. PBDB published occurrences &middot; CC0 1.0. Geological reference &middot; ICS v2026/06 &middot; CC BY 4.0. Source evidence and PaleoGraph interpretations remain distinct.</footer>
  </div>;
}
