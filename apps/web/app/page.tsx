import Link from "next/link";
import { HomeContext } from "../features/explore/HomeContext";
import { NavigationIcon } from "../features/explore/NavigationIcon";
import { BrandMark } from "../features/brand/PaleoGraphBrand";
import { HomeMotion } from "../features/home/HomeMotion";
import { HomeStudy } from "../features/home/HomeStudy";
import "./home-experience.css";

export default function HomePage() {
  return <div className="home-atlas home-experience">
    <HomeMotion />
    <div className="home-reading-progress" aria-hidden="true" />
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
        <a className="home-scroll-invitation" href="#the-collection">There is more beneath the surface <span aria-hidden="true">↓</span></a>
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
    <section className="home-collection" id="the-collection" aria-labelledby="home-collection-title">
      <div className="home-section-heading" data-home-reveal><p className="home-section-index">01 / The living archive</p><div><h2 id="home-collection-title">A past worth<br /><em>looking into.</em></h2><p>Long before the familiar landscape, there were other lives here. Follow their traces through Florida&apos;s museum material and published fossil evidence.</p></div></div>
      <div className="home-cabinet" data-home-reveal>
        {[
          { name: "Proboscideans", query: "Proboscidea", form: "proboscidean", detail: "A different kind of giant" },
          { name: "Crocodilians", query: "Crocodylia", form: "crocodilian", detail: "An enduring presence" },
          { name: "Sharks & rays", query: "Chondrichthyes", form: "shark", detail: "Traces of ancient waters" },
        ].map((item, index) => <Link key={item.form} className="home-cabinet-entry" href={`/explore?source=all&q=${item.query}`} aria-label={`Explore ${item.name.toLowerCase()} in the evidence archive`}><span className="cabinet-accession">FIELD STUDY / 0{index + 1}</span><span className={`home-cabinet-form cabinet-${item.form}`} aria-hidden="true" /><span className="cabinet-description"><small>{item.detail}</small><strong>{item.name}</strong><span className="cabinet-action">Explore the evidence <span aria-hidden="true">↗</span></span></span></Link>)}
      </div>
      <p className="home-artwork-note">Illustrative forms / orientation, not specimen imagery or species reconstructions.</p>
    </section>
    <section className="home-pathways" aria-labelledby="home-pathways-title">
      <div className="home-pathways-intro" data-home-reveal><p className="home-section-index">02 / A way of seeing</p><h2 id="home-pathways-title">The story changes<br />with your <em>perspective.</em></h2><p>A place opens a collection. A record opens a question. A branch opens another way through. Choose where your curiosity begins.</p><span className="home-pathway-rule" aria-hidden="true" /></div>
      <HomeStudy />
    </section>
    <section className="home-principles" aria-labelledby="home-principles-title">
      <div className="home-principles-heading" data-home-reveal><p className="home-section-index">03 / Kept in context</p><h2 id="home-principles-title">Wonder, with<br /><em>the evidence attached.</em></h2></div>
      <div className="home-principle-list" data-home-reveal>
        <div><span aria-hidden="true">01</span><h3>A source stays a source.</h3><p>Museum material and published occurrences sit alongside one another, with their identities and provenance intact.</p></div>
        <div><span aria-hidden="true">02</span><h3>Uncertainty belongs here.</h3><p>Missing ages, qualified identifications, and differing source classifications remain part of the story.</p></div>
        <div><span aria-hidden="true">03</span><h3>Context goes with you.</h3><p>Move between map, catalog, and classification. Follow the evidence back to the record behind it.</p></div>
      </div>
    </section>
    <section className="home-maker" aria-labelledby="home-maker-title">
      <div className="home-maker-top" data-home-reveal><span className="home-section-index">An independent field atlas</span><BrandMark /></div>
      <h2 id="home-maker-title" data-home-reveal>For the curious.<br /><em>For the record.</em></h2>
      <div className="home-maker-bottom" data-home-reveal><div><p className="home-maker-label">Designed &amp; built by</p><a className="home-maker-name" href="https://github.com/AaronGibson2">Aaron Gibson <span aria-hidden="true">↗</span></a><p className="home-maker-note">A personal project at the meeting point of vertebrate paleontology, data, and a curiosity about what came before.</p><a className="home-related-project" href="https://github.com/AaronGibson2/proboscidean-morphometrics-ml">Also exploring / proboscidean morphometrics <span aria-hidden="true">↗</span></a></div><Link className="home-maker-launch" href="/explore"><span>Begin exploring</span><span aria-hidden="true">↗</span></Link></div>
    </section>
    <footer className="home-credit">UFVP museum data &middot; CC BY-NC 4.0. PBDB published occurrences &middot; CC0 1.0. Geological reference &middot; ICS v2026/06 &middot; CC BY 4.0. Source evidence and PaleoGraph interpretations remain distinct.</footer>
  </div>;
}
