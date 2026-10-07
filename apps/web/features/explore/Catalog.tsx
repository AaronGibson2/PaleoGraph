"use client";

import { useState } from "react";
import { discovery, type CatalogItem, type Page } from "../../lib/api/discovery";
import { TaxonVisual } from "../taxon-visuals/TaxonVisual";
import { resolveTaxonVisual } from "../taxon-visuals/resolve";
import { useResource } from "./useResource";
import { browseKey } from "./browseCache";
import { prefetchEntity, type BrowseTarget } from "./browseIntent";
import { IntentButton } from "./IntentButton";

export function Catalog({ query, open, onSelect, onClose, retry }: { query: string; open: boolean; onSelect: (entity: BrowseTarget) => void; onClose: () => void; retry: number }) {
  const [navigation, setNavigation] = useState<{ base: string; cursors: string[] }>({ base: "", cursors: [] });
  const cursors = navigation.base === query ? navigation.cursors : [];
  const pageQuery = `${query}&limit=30${cursors.length ? `&cursor=${encodeURIComponent(cursors.at(-1)!)}` : ""}`;
  const debounce = /(?:^|&)(?:locality_id|taxon_id)=/.test(query) ? 0 : 180;
  const result = useResource<Page<CatalogItem> & { offset: number }>(open ? browseKey("/catalog",pageQuery) : null, async signal => ({ ...await discovery.catalog(pageQuery, signal), offset: cursors.length * 30 }), debounce, retry);
  const items = result.data?.items ?? [];
  const source=new URLSearchParams(query).get("source") ?? "ufvp";
  return <aside hidden={!open} inert={!open} style={open ? undefined : { display: "none" }} className="catalog-panel" aria-labelledby="results-heading" aria-busy={result.loading}>
    <div className="panel-heading"><div><p className="eyebrow">Source evidence</p><h2 id="results-heading" tabIndex={-1}>{source === "ufvp" ? "Museum catalog" : source === "pbdb" ? "Published occurrences" : "Evidence catalog"}</h2></div><button className="icon-button" aria-label="Close catalog" onClick={onClose}>×</button></div>
    <p className="result-count" role="status">{result.data ? `${result.data.total.toLocaleString("en-US")} ${source === "ufvp" ? "assertions" : source === "pbdb" ? "published occurrences" : "evidence records"}` : "Loading catalog…"}{result.loading && result.data ? " · Updating…" : ""}</p>
    {source === "all" && result.data?.counts && <p className="evidence-source">UFVP museum material: {result.data.counts.museum_material.toLocaleString("en-US")} / PBDB published occurrences: {result.data.counts.published_occurrences.toLocaleString("en-US")}</p>}
    {source === "pbdb" && <p className="context-note catalog-scope">Published occurrences under selected source filters. No map viewport is applied; an exact selected position remains a filter.</p>}
    <p className="continuity-note">{result.loading && result.data ? "Showing last loaded results." : result.error ?? "Museum assertions may contain multiple pieces. Published occurrences describe source evidence."}</p>
    <ol className="catalog-list occurrence-list" start={(result.data?.offset ?? 0) + 1}>
      {items.map(item => <li key={item.id}>
        <IntentButton prepare={() => prefetchEntity({ kind:item.specimen_id ? "specimen" : "occurrence", id:item.specimen_id ?? item.id, label:item.label, subtitle:item.scientific_name, occurrence_id:item.id })} id={`result-${item.specimen_id ?? item.id}`} className="catalog-entry" disabled={result.loading && result.data === undefined} onClick={() => onSelect({ kind: item.specimen_id ? "specimen" : "occurrence", id: item.specimen_id ?? item.id, label: item.label, subtitle: item.scientific_name, source:item.source, occurrence_id:item.id, classification_path_ids:item.classification_path_ids })}>
          <TaxonVisual visual={resolveTaxonVisual({ id: item.taxon_id, classification_path_ids: item.classification_path_ids })} /><span><small className="evidence-source">{item.source === "pbdb" ? "PBDB · Published occurrence" : "UFVP · Museum material"}</small><small className="catalog-label">{item.label}</small><strong><em>{item.scientific_name}</em></strong><span>{item.locality_name ?? "Location not supplied"}</span><span className="catalog-age">{item.source_age_label ?? "Geological age not supplied"}{item.age_basis === "derived-interval" ? " · interpreted" : ""}</span></span><span className="entry-arrow" aria-hidden="true">↗</span>
        </IntentButton>
        <div className="entry-pivots"><button onClick={() => onSelect({ kind: "taxon", id: item.taxon_id, label: item.scientific_name, source:item.source, subtitle: "Source identification" })}>Taxon</button>{item.locality_id && <button onClick={() => onSelect({ kind: "locality", id: item.locality_id!, label: item.locality_name ?? "Locality", source:item.source, subtitle: null })}>{item.source === "pbdb" ? "Collection context" : "Locality"}</button>}</div>
      </li>)}
    </ol>
    {!result.loading && !result.error && items.length === 0 && <p className="panel-message">{source === "ufvp" ? "No material matches this view and context." : "No evidence matches this view and context."} Unknown ages are excluded by a time filter.</p>}
    <div className="catalog-pagination"><span>{result.data ? `${result.data.offset + (items.length ? 1 : 0)}–${result.data.offset + items.length} of ${result.data.total.toLocaleString("en-US")}` : ""}</span><button disabled={!cursors.length || result.loading} onClick={() => setNavigation({ base: query, cursors: cursors.slice(0, -1) })}>← Previous</button><button disabled={!result.data?.next_cursor || result.loading} onClick={() => setNavigation({ base: query, cursors: [...cursors, result.data!.next_cursor!] })}>Next →</button></div>
  </aside>;
}
