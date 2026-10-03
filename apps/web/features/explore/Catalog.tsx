"use client";

import { useState } from "react";
import { discovery, type CatalogItem, type EntityRef, type Page } from "../../lib/api/discovery";
import { useResource } from "./useResource";

export function Catalog({ query, onSelect, onClose, retry }: { query: string; onSelect: (entity: EntityRef) => void; onClose: () => void; retry: number }) {
  const [navigation, setNavigation] = useState<{ base: string; cursors: string[] }>({ base: "", cursors: [] });
  const cursors = navigation.base === query ? navigation.cursors : [];
  const pageQuery = `${query}&limit=30${cursors.length ? `&cursor=${encodeURIComponent(cursors.at(-1)!)}` : ""}`;
  const result = useResource<Page<CatalogItem> & { offset: number }>(`${pageQuery}:retry:${retry}`, async signal => ({ ...await discovery.catalog(pageQuery, signal), offset: cursors.length * 30 }), 180);
  const items = result.data?.items ?? [];
  return <aside className="catalog-panel" aria-labelledby="results-heading" aria-busy={result.loading}>
    <div className="panel-heading"><div><p className="eyebrow">The material record</p><h2 id="results-heading" tabIndex={-1}>Museum catalog</h2></div><button className="icon-button" aria-label="Close catalog" onClick={onClose}>×</button></div>
    <p className="result-count" role="status">{result.data ? `${result.data.total.toLocaleString("en-US")} assertions` : "Loading catalog…"}{result.loading && result.data ? " · Updating…" : ""}</p>
    <p className="continuity-note">{result.loading && result.data ? "Showing last loaded results." : result.error ?? "Catalog assertions can contain multiple pieces."}</p>
    <ol className="catalog-list occurrence-list" start={(result.data?.offset ?? 0) + 1}>
      {items.map(item => <li key={item.id}>
        <button id={`result-${item.specimen_id}`} className="catalog-entry" disabled={result.loading && result.data === undefined} onClick={() => onSelect({ kind: "specimen", id: item.specimen_id, label: item.label, subtitle: item.scientific_name })}>
          <span className="entry-mark" aria-hidden="true">◇</span><span><small className="catalog-label">{item.label}</small><strong><em>{item.scientific_name}</em></strong><span>{item.locality_name ?? "Location not supplied"}</span><span className="catalog-age">{item.source_age_label ?? "Geological age not supplied"}{item.age_basis === "derived-interval" ? " · interpreted" : ""}</span></span><span className="entry-arrow" aria-hidden="true">↗</span>
        </button>
        <div className="entry-pivots"><button onClick={() => onSelect({ kind: "taxon", id: item.taxon_id, label: item.scientific_name, subtitle: "Source identification" })}>Taxon</button>{item.locality_id && <button onClick={() => onSelect({ kind: "locality", id: item.locality_id!, label: item.locality_name ?? "Locality", subtitle: null })}>Locality</button>}</div>
      </li>)}
    </ol>
    {!result.loading && !result.error && items.length === 0 && <p className="panel-message">No material matches this view and context. Unknown ages are excluded by a time filter.</p>}
    <div className="catalog-pagination"><span>{result.data ? `${result.data.offset + (items.length ? 1 : 0)}–${result.data.offset + items.length} of ${result.data.total.toLocaleString("en-US")}` : ""}</span><button disabled={!cursors.length || result.loading} onClick={() => setNavigation({ base: query, cursors: cursors.slice(0, -1) })}>← Previous</button><button disabled={!result.data?.next_cursor || result.loading} onClick={() => setNavigation({ base: query, cursors: [...cursors, result.data!.next_cursor!] })}>Next →</button></div>
  </aside>;
}
