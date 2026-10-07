"use client";

import { useEffect, useState } from "react";
import { discovery, type EntityRef, type Page } from "../../lib/api/discovery";
import { TaxonVisual } from "../taxon-visuals/TaxonVisual";
import { resolveTaxonVisual } from "../taxon-visuals/resolve";
import { useResource } from "./useResource";
import { browseKey } from "./browseCache";
import { prefetchEntity } from "./browseIntent";
import { IntentButton } from "./IntentButton";
const EMPTY_RESULTS: EntityRef[] = [];

export function Search({ value, context, onChange, onSelect }: { value: string; context: string; onChange: (value: string) => void; onSelect: (entity: EntityRef) => void }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [pagination, setPagination] = useState<{ base: string; cursor: string } | null>(null);
  const base = `${context}&q=${encodeURIComponent(value)}`;
  const query = `${base}&limit=12${pagination?.base === base ? `&cursor=${encodeURIComponent(pagination.cursor)}` : ""}`;
  const result = useResource<Page<EntityRef>>(open && value.trim() ? browseKey("/search",query) : null, signal => discovery.search(query, signal), 180);
  const items = result.data?.items ?? EMPTY_RESULTS;
  useEffect(() => {
    if (open) document.getElementById(`search-option-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [active, open, result.key]);
  useEffect(() => {
    if(!open || result.loading || !items[active])return;
    const timer=setTimeout(()=>prefetchEntity(items[active]),100);
    return ()=>clearTimeout(timer);
  },[open,active,items,result.loading]);
  const select = (entity: EntityRef) => { onSelect(entity); setOpen(false); setActive(0); };
  return <div className="atlas-search" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <span className="search-symbol" aria-hidden="true">⌕</span>
    <label className="sr-only" htmlFor="atlas-search">Search material, published occurrences, taxa, places and references</label>
    <input id="atlas-search" role="combobox" aria-autocomplete="list" aria-expanded={open && !!value.trim()} aria-controls="search-results" aria-activedescendant={open && items[active] ? `search-option-${active}` : undefined}
      placeholder="Search taxa, places, catalog numbers…" value={value} maxLength={160}
      onFocus={() => setOpen(true)} onChange={event => { onChange(event.target.value); setOpen(true); setActive(0); }}
      onKeyDown={event => {
        if (event.key === "Escape") { setOpen(false); event.preventDefault(); }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); setActive(index => Math.max(0, Math.min(items.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))); }
        if (event.key === "Home" && open) { event.preventDefault(); setActive(0); }
        if (event.key === "End" && open) { event.preventDefault(); setActive(items.length - 1); }
        if (event.key === "Enter" && open && items[active] && !result.loading) { event.preventDefault(); select(items[active]); }
      }} />
    {value && <button aria-label="Clear search" className="search-clear" onClick={() => { onChange(""); setOpen(false); }}>×</button>}
    {open && value.trim() && <div className="search-popover">
      <p className="search-meta" role="status">{result.loading ? "Searching the local catalog…" : result.error ?? `${result.data?.total.toLocaleString("en-US") ?? 0} matching entities`}</p>
      <ul role="listbox" id="search-results" aria-label="Evidence search results" aria-busy={result.loading}>
        {items.map((entity, index) => <li key={`${entity.kind}:${entity.id}`} id={`search-option-${index}`} role="option" aria-selected={index === active}>
          <IntentButton prepare={() => prefetchEntity(entity)} disabled={result.loading} tabIndex={-1} onMouseDown={event => event.preventDefault()} onClick={() => select(entity)}><span className="search-kind">{entity.kind === "occurrence" ? "Published occurrence" : entity.kind === "locality" && entity.source === "pbdb" ? "Collection context" : entity.kind}</span><strong>{(entity.kind === "taxon" || entity.kind === "specimen") && <TaxonVisual visual={resolveTaxonVisual(entity)} />}{entity.label}</strong><small>{entity.source?.toUpperCase()} · {entity.subtitle}</small></IntentButton>
        </li>)}
      </ul>
      {!result.loading && !result.error && items.length === 0 && <p className="search-meta">No current material matches. Try a taxon, locality or accession.</p>}
      {result.data?.next_cursor && <button className="search-more" disabled={result.loading} onClick={() => { setPagination({ base, cursor: result.data!.next_cursor! }); setActive(0); }}>Next search results →</button>}
      {pagination?.base === base && <button className="search-more" onClick={() => setPagination(null)}>First search results</button>}
    </div>}
  </div>;
}
