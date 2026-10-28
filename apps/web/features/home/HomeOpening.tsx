"use client";

import Link from "next/link";
import { useRef } from "react";
import { NavigationIcon } from "../explore/NavigationIcon";
import { OpeningScene } from "./OpeningScene";
import { useOpeningMotion } from "./useOpeningMotion";

/** The working entrance is server-rendered; the illustration never gates it. */
export function HomeOpening() {
  const openingRef = useRef<HTMLElement>(null);
  const motion = useOpeningMotion(openingRef);
  return <section ref={openingRef} className="home-opening" data-opening={motion.phase} data-paused={motion.paused} data-uncovered={motion.uncovered} aria-labelledby="home-title">
    <noscript><style>{`.home-opening .opening-art,.home-opening .opening-title-life,.home-opening .opening-title-recorded,.home-opening .eyebrow,.home-opening .opening-field-note,.home-opening .opening-impression,.home-opening .opening-evidence-nodes,.home-opening .opening-brand-bands i,.home-opening .opening-brand-construction>span,.home-opening .opening-brand-construction>small,body:has(.home-opening) .site-header .wordmark{opacity:1!important;transform:none!important;clip-path:none!important;filter:none!important;animation:none!important}.home-opening .opening-traces path{stroke-dashoffset:0!important}`}</style></noscript>
    <div className="home-introduction">
      <p className="eyebrow"><span className="opening-eyebrow-rule" aria-hidden="true" />An open field atlas / Florida</p>
      <h1 id="home-title"><span className="opening-title-life">Life,</span><br /><em className="opening-title-recorded">recorded.</em></h1>
      <p className="home-statement">Beneath a familiar landscape,<br className="opening-desktop-break" /> an extraordinary record of life.</p>
      <p className="opening-invitation">Explore it through place, deep time, and the evidence we keep.</p>
      <form className="home-search" action="/explore" role="search" aria-label="Search the evidence archive">
        <label className="sr-only" htmlFor="home-query">Search taxa, places or catalog identifiers</label>
        <input id="home-query" name="q" type="search" maxLength={160} placeholder="A taxon, a place, a catalog number…" />
        <input type="hidden" name="source" value="all" />
        <button type="submit" aria-label="Search the archive"><span aria-hidden="true">↗</span></button>
      </form>
      <nav className="home-destinations" aria-label="Choose an exploration destination">
        <Link className="home-destination home-destination-atlas" href="/explore"><NavigationIcon kind="atlas" /><span>Atlas</span><span className="opening-link-arrow" aria-hidden="true">↗</span></Link>
        <Link className="home-destination home-destination-catalog" href="/explore?catalog=open"><NavigationIcon kind="catalog" /><span>Catalog</span><span className="opening-link-arrow" aria-hidden="true">↗</span></Link>
        <Link className="home-destination home-destination-lineage" href="/lineage"><NavigationIcon kind="lineage" /><span>Lineage</span><span className="opening-link-arrow" aria-hidden="true">↗</span></Link>
      </nav>
      <p className="home-search-note">Source records stay distinct. Uncertainty stays visible.</p>
    </div>
    <OpeningScene phase={motion.phase} enhanced={motion.enhanced} artFailed={motion.artFailed} onReplay={motion.replay} onFinish={motion.finish} />
    <a className="home-scroll-invitation" href="#the-collection"><span className="opening-scroll-line" aria-hidden="true" />There is more beneath the surface<span aria-hidden="true">↓</span></a>
  </section>;
}
