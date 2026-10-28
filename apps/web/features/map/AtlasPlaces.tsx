"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { MapOccurrence, Viewport } from "../../lib/api/types";
import { discovery } from "../../lib/api/discovery";
import { browseKey } from "../explore/browseCache";
import type { BrowseTarget } from "../explore/browseIntent";
import { ageLabel } from "../explore/state";
import { useResource } from "../explore/useResource";

const number = (value: number) => value.toLocaleString("en-US");
export function PositionPreview({ item }: { item: MapOccurrence }) {
  return <><span className="eyebrow">Published position · UFVP</span><strong>{number(item.record_count ?? 1)} evidence records</strong><span>{item.locality_name}</span><small>{item.interpreted_count == null ? ageLabel(item) : `${number(item.interpreted_count)} with numeric age bounds · ${number((item.record_count ?? 1) - item.interpreted_count)} unresolved`}</small>{item.location_is_generalized && <small>Generalized source position</small>}</>;
}

/** A bounded, keyboard-accessible equivalent to geographic point selection. */
export function AtlasPlaces({ items, viewport, selected, preview, onPreview, onSelect }: { items: MapOccurrence[]; viewport: Viewport; selected?: string; preview: string | null; onPreview: (id: string | null) => void; onSelect: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const visible = useMemo(() => items.filter(p => p.latitude >= viewport.south && p.latitude <= viewport.north && (viewport.west <= viewport.east ? p.longitude >= viewport.west && p.longitude <= viewport.east : p.longitude >= viewport.west || p.longitude <= viewport.east)).sort((a,b) => (b.record_count ?? 1) - (a.record_count ?? 1) || a.id.localeCompare(b.id)), [items,viewport]);
  const current = Math.min(page, Math.max(0, Math.ceil(visible.length / 6) - 1));
  const focused = visible.find(item => item.id === preview);
  return <div className="atlas-position-index">
    <button className="atlas-index-toggle" aria-expanded={open} aria-controls="atlas-position-list" onClick={() => { setOpen(!open); onPreview(null); }}><span aria-hidden="true">⌖</span> Mapped positions <small>{number(visible.length)}</small><span aria-hidden="true">{open ? "−" : "+"}</span></button>
    {open && <section id="atlas-position-list" aria-label="Mapped positions in view" className="atlas-position-list">
      <p>Published positions in this view, ordered by evidence. Coordinates may represent several distinct source localities.</p>
      <ol start={current * 6 + 1}>{visible.slice(current * 6, current * 6 + 6).map(item => <li key={item.id}><button aria-pressed={selected === item.id} onFocus={() => onPreview(item.id)} onBlur={() => onPreview(null)} onPointerEnter={() => onPreview(item.id)} onPointerLeave={() => onPreview(null)} onClick={() => { onSelect(item.id); setOpen(false); onPreview(null); }}><span><strong>{number(item.record_count ?? 1)}</strong><small>records · {item.locality_name}</small></span><span className="atlas-coordinate">{item.latitude.toFixed(3)}°<br />{item.longitude.toFixed(3)}°</span></button></li>)}</ol>
      {!visible.length && <p>No retained mapped evidence matches this view and its filters. Unresolved ages do not match a numeric time filter. Pan or clear filters to explore more.</p>}
      <div className="atlas-index-pagination"><button disabled={current === 0} onClick={() => setPage(current - 1)}>Previous positions</button><button disabled={(current + 1) * 6 >= visible.length} onClick={() => setPage(current + 1)}>Next positions</button></div>
      {focused && <div className="atlas-focus-preview" role="status"><PositionPreview item={focused} /></div>}
    </section>}
  </div>;
}

/** Exact source identities at a position; never merges co-located localities. */
export function AtlasPositionSelection({ context, onPivot, onEvidence, onClear }: { context: string; onPivot: (entity: BrowseTarget) => void; onEvidence: () => void; onClear: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus({preventScroll:true}); }, []);
  const [cursor, setCursor] = useState<{ context: string; value: string }>();
  const query = `${context}&limit=6${cursor?.context === context ? `&cursor=${encodeURIComponent(cursor.value)}` : ""}`;
  const result = useResource(browseKey("/localities", query), signal => discovery.localities(query, signal));
  return <aside className="atlas-position-selection" aria-label="Selected published position" onKeyDown={event => { if(event.key === "Escape") onClear(); }}>
    <div className="atlas-drawer-edition"><span>FIELD ATLAS / SELECTED POSITION</span><button aria-label="Clear selected position" onClick={onClear}>×</button></div>
    <h2 ref={heading} tabIndex={-1}>One position.<br /> Distinct histories.</h2><p>Open a source locality to follow its evidence, time and represented taxa.</p>
    <ol>{result.data?.items.map(item => <li key={item.id}><button onClick={() => onPivot(item)}><span><small>{item.source === "pbdb" ? "PBDB collection context" : "UFVP locality"}</small><strong>{item.label}</strong><small>{ageLabel(item)}</small></span><span>{number(item.assertion_count)}<small>{item.source === "pbdb" ? "occurrences" : "assertions"}</small></span></button></li>)}</ol>
    {result.loading && <p role="status">Reading source localities…</p>}{result.error && <p role="alert">{result.error}</p>}
    {!result.loading && !result.error && !result.data?.items.length && <p>No source locality matches this position under the current filters.</p>}
    {result.data?.next_cursor && <button onClick={() => setCursor({context,value:result.data!.next_cursor!})}>More localities at this position →</button>}
    {cursor?.context === context && <button onClick={() => setCursor(undefined)}>First localities</button>}
    <button className="atlas-evidence-link" onClick={onEvidence}>Inspect related evidence ↗</button>
    <small>Shared coordinates do not establish shared locality identity or contemporaneity.</small>
  </aside>;
}
