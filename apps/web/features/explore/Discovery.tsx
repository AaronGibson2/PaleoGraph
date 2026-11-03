"use client";

import { useEffect, useRef, useState } from "react";
import { taxonomy } from "../../lib/api/taxonomy";
import type { GeologicalInterval } from "../../lib/api/types";
import { TaxonVisual } from "../taxon-visuals/TaxonVisual";
import { resolveTaxonVisual } from "../taxon-visuals/resolve";
import { browseKey } from "./browseCache";
import { taxonomyContext } from "./taxonomyTree";
import { ageLabel } from "./state";
import { useResource } from "./useResource";
import "./discovery.css";

const groups = [
  ["Mammals", "Mammalia"], ["Birds", "Aves"], ["Turtles", "Testudines"],
  ["Crocodilians", "Crocodylia"], ["Cartilaginous fishes", "Chondrichthyes"], ["Mollusks", "Mollusca"],
] as const;
const periods = ["Pleistocene", "Pliocene", "Miocene", "Eocene"];
const number = (value: number) => value.toLocaleString("en-US");

export function Discovery({ context, search, intervals, onSearch, onTaxonomy, onInterval, onCatalog, onClose }: {
  context: string; search: string; intervals: GeologicalInterval[];
  onSearch: (value: string) => void; onTaxonomy: (id: string) => void;
  onInterval: (interval: GeologicalInterval) => void; onCatalog: () => void; onClose: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, []);
  const params = new URLSearchParams(taxonomyContext(context));
  params.set("q", search.trim()); params.set("limit", "12");
  const query = params.toString();
  const key = search.trim().length >= 2 ? browseKey("/taxonomy/search", query) : null;
  const result = useResource(key, signal => taxonomy.search(query, signal), 180, retry);
  const data = result.dataKey === key ? result.data : undefined;
  const source = params.get("source") ?? "all";
  const error = result.key === key ? result.error : undefined;
  return <aside className="discovery-panel" aria-labelledby="discovery-heading" onKeyDown={event => {
    if (event.key === "Escape") { event.stopPropagation(); onClose(); }
  }}>
    <header className="discovery-header"><div><p className="eyebrow">A field guide to the archive</p><h2 id="discovery-heading" ref={heading} tabIndex={-1}>Follow your curiosity.</h2><p>Find a group, open its classification, and follow the evidence.</p></div><button className="icon-button" aria-label="Close discovery guide" onClick={onClose}>&times;</button></header>
    <div className="discovery-body">
      <section aria-labelledby="discovery-groups"><div className="discovery-section-title"><div><p className="eyebrow">01 / Begin with life</p><h3 id="discovery-groups">Explore a taxonomic group</h3></div><span>{source === "all" ? "UFVP + PBDB" : source.toUpperCase()}</span></div>
        <div className="discovery-starters" role="group" aria-label="Suggested taxonomic groups">{groups.map(([label, name]) => <button key={name} aria-pressed={search === name} onClick={() => onSearch(name)}>{label}</button>)}</div>
        <label className="discovery-search">Find a classification<input type="search" value={search} maxLength={160} placeholder="Try Mammalia, Canis, or a family name" onChange={event => onSearch(event.target.value)} /></label>
        <p className="discovery-context">Across the retained Florida archive, within the selected source, place, and time filters. Counts describe evidence records, not organisms.</p>
        <div className="discovery-results" aria-busy={result.loading}>
          <p className="discovery-status" role="status">{!key ? "Enter at least two characters to find a group." : result.loading ? "Finding represented classifications…" : data ? `${number(data.total)} matching classifications${data.total > data.items.length ? ` · showing ${data.items.length}` : ""}` : ""}</p>
          {error && <p role="alert">{error} <button onClick={() => setRetry(value => value + 1)}>Retry discovery</button></p>}
          <ul className="discovery-cards">{data?.items.map(node => <li key={node.id}><button onClick={() => onTaxonomy(node.id)}>
            <TaxonVisual visual={resolveTaxonVisual({ id: node.id, classification_path_ids: node.classification_path_ids })} />
            <span className="discovery-card-title"><small>{node.rank ?? "Browse grouping"} · {node.placement}</small><strong>{node.name}</strong><span>{node.path.slice(0, -1).map(parent => parent.name).join(" › ") || "Classification entry point"}</span></span>
            <span className="discovery-card-count"><strong>{number(node.counts.evidence_count)}</strong><small>inclusive evidence</small></span>
            <span className="discovery-card-sources">UFVP {number(node.counts.ufvp_material_count)} · PBDB {number(node.counts.pbdb_occurrence_count)}</span>
            <span className="discovery-card-age">Observed envelope: {ageLabel(node.counts)}<small>{number(node.counts.unknown_age_count)} records with unresolved ages</small></span>
            <span className="discovery-card-action">Explore classification <span aria-hidden="true">↗</span></span>
          </button></li>)}</ul>
          {key && !result.loading && !error && data?.items.length === 0 && <div className="discovery-empty"><h4>No represented groups match this context.</h4><p>Try another name or remove a place or time filter. Missing evidence does not establish biological absence.</p><button onClick={onCatalog}>Browse the evidence catalog</button></div>}
        </div>
      </section>
      <section aria-labelledby="discovery-time"><p className="eyebrow">02 / Begin with deep time</p><h3 id="discovery-time">Explore a geological interval</h3><p>Open overlapping evidence in the Catalog using the pinned ICS reference bounds. Records with unresolved numeric ages are excluded.</p><div className="discovery-intervals">{periods.map(name => intervals.find(interval => interval.name === name)).filter((interval): interval is GeologicalInterval => !!interval).map(interval => <button key={interval.id} onClick={() => onInterval(interval)} style={{ borderLeftColor: interval.color }}><strong>{interval.name}</strong><span>{ageLabel(interval)}</span><small>{interval.rank} · ICS reference envelope</small></button>)}</div>{!intervals.length && <p role="status">Geological reference shortcuts will appear when the time configuration is available.</p>}</section>
      <footer className="discovery-footer"><div><h3>Prefer to browse the records?</h3><p>Search catalog numbers, scientific names, and locality labels across the retained Florida archive.</p></div><button onClick={onCatalog}>Open the full Catalog ↗</button></footer>
      <p className="discovery-context">Classification is distinct from phylogeny. Observed age envelopes describe retained evidence, not origin, extinction, or uninterrupted presence.</p>
    </div>
  </aside>;
}
