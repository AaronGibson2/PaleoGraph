import Link from "next/link";
import { HomeContext } from "../features/explore/HomeContext";
import { HomeOpening } from "../features/home/HomeOpening";
import { BrandMark } from "../features/brand/PaleoGraphBrand";
import { HomeMotion } from "../features/home/HomeMotion";
import { HomeStudy } from "../features/home/HomeStudy";
import "./home-experience.css";
import "./home-opening.css";

export default function HomePage() {
  return <div className="home-atlas home-experience home-moonshot">
    <HomeMotion />
    <div className="home-reading-progress" aria-hidden="true" />
    <HomeOpening />
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
