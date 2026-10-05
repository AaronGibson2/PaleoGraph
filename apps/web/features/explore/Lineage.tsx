"use client";

import { useEffect, useRef, useState } from "react";
import { discovery, type EntityRef, type LineageItem } from "../../lib/api/discovery";
import type { AgeRange, GeologicalInterval } from "../../lib/api/types";
import { TaxonVisual } from "../taxon-visuals/TaxonVisual";
import { resolveTaxonVisual } from "../taxon-visuals/resolve";
import { ageLabel, lineageContext } from "./state";
import { useResource } from "./useResource";
import { browseKey } from "./browseCache";
import { prefetchEntity, prefetchLineage, prefetchLocalities, prefetchMaterial } from "./browseIntent";
import { IntentButton } from "./IntentButton";

const number = (value: number) => value.toLocaleString("en-US");
export function Lineage({ focus, activeTaxon, context, age, intervals, onFocus, onSelect, onAtlas, onLocalities, onMaterial }: { focus?: string | null; activeTaxon?: string | null; context: string; age: AgeRange; intervals: GeologicalInterval[]; onFocus: (id: string | null) => void; onSelect: (entity: EntityRef) => void; onAtlas: (taxon: string | null) => void; onLocalities: (taxon: string | null) => void; onMaterial: (taxon: string | null) => void }) {
  const [navigation, setNavigation] = useState<{ base: string; cursors: string[] }>({ base: "", cursors: [] });
  const [retry, setRetry] = useState(0);
  const [actionsOpen, setActionsOpen] = useState(false);
  const base = `${context}&limit=12${focus ? `&focus=${encodeURIComponent(focus)}` : ""}`;
  const cursors = navigation.base === base ? navigation.cursors : [];
  const query = `${base}${cursors.length ? `&cursor=${encodeURIComponent(cursors.at(-1)!)}` : ""}`;
  const result = useResource(browseKey("/lineage",query), signal => discovery.lineage(query, signal), 0, retry);
  const tree = useRef<HTMLUListElement>(null);
  const restoringFocus = useRef(false);
  const previousFocus = useRef(focus);
  useEffect(() => {
    if (!result.loading && !result.error && result.data && previousFocus.current !== focus) {
      previousFocus.current = focus;
      restoringFocus.current=true;
      try { tree.current?.querySelector<HTMLButtonElement>(".lineage-taxon")?.focus({ preventScroll: true }); }
      finally { restoringFocus.current=false; }
    }
  }, [result.loading, result.error, result.data, focus]);
  const data = result.data;
  const rows = data?.items.length ? data.items : data?.focal ? [data.focal] : [];
  const maximum = Math.max(1, data?.focal?.older_ma ?? 0, ...rows.map(item => item.older_ma ?? 0));
  const scale = maximum <= .1 ? .1 : maximum <= 1 ? 1 : maximum <= 5 ? 5 : maximum <= 12 ? 12 : maximum <= 25 ? 25 : maximum <= 66 ? 66 : Math.ceil(maximum / 50) * 50;
  const position = (value: number) => (1 - value / scale) * 100;
  const select = (item: LineageItem) => onSelect({ kind: "taxon", id: item.id, label: item.label, subtitle: item.subtitle, classification_path_ids:item.classification_path_ids });
  const targetTaxon = lineageContext(activeTaxon, data?.focus?.id, data?.breadcrumbs ?? []);
  return <div className="scientific-surface lineage-surface" aria-label="Lineage explorer" aria-busy={result.loading}>
    <div className="surface-introduction"><div><p className="eyebrow">Classification / observed deep time</p><h2>{data?.focus?.label ?? "The source taxonomic hierarchy"}</h2><p>Published UFVP classification. Taxonomic membership, not a phylogenetic tree.</p></div><span className="plate-number" aria-hidden="true">03 / LINEAGE</span></div>
    {result.error && <p className="snapshot-status" role="alert">{result.error}. Last loaded classification retained. <button onClick={() => setRetry(value => value + 1)}>Retry lineage</button></p>}
    <div className="lineage-navigation"><nav aria-label="Classification path"><IntentButton prepare={() => prefetchLineage(context,null)} onClick={() => onFocus(null)}>All source ranks</IntentButton>{data?.breadcrumbs.map((item,index) => <span key={item.id}><span aria-hidden="true"> / </span><IntentButton prepare={() => prefetchLineage(context,item.id)} aria-current={index === data.breadcrumbs.length - 1 ? "location" : undefined} onClick={() => onFocus(item.id)}>{item.label}<small>{item.subtitle ?? "Rank not supplied"}</small></IntentButton></span>)}</nav><p role="status">{result.loading ? data ? "Updating / last loaded classification retained" : "Reading source hierarchy…" : result.error ?? `${data?.total ?? 0} ${data?.focus ? "direct members" : "top-level groups"}`}</p></div>
    {data?.focal && <div className="lineage-focus"><TaxonVisual visual={resolveTaxonVisual(data.focal)} /><div><p className="eyebrow">{data.focal.is_source_identification ? "Source identification" : "Published classification"} / {data.focal.subtitle ?? "rank not supplied"}</p><p>{number(data.focal.assertion_count)} assertions · {number(data.focal.source_taxon_count)} source identifications · {ageLabel(data.focal)}</p></div><button className="mobile-lineage-actions" aria-expanded={actionsOpen} onClick={() => setActionsOpen(value => !value)}>Taxon actions</button><div className="lineage-actions" data-open={actionsOpen}><button disabled={result.loading || !!result.error} onClick={() => select(data.focal!)}>Select this taxon</button><button disabled={result.loading || !!result.error} onClick={() => onAtlas(targetTaxon)}>Show on Atlas ↗</button><IntentButton prepare={() => prefetchLocalities(context,targetTaxon)} disabled={result.loading || !!result.error} onClick={() => onLocalities(targetTaxon)}>Associated localities ↗</IntentButton><IntentButton prepare={() => {const p=new URLSearchParams(context);if(targetTaxon)p.set("taxon_id",targetTaxon);else p.delete("taxon_id");prefetchMaterial(p.toString());}} disabled={result.loading || !!result.error} onClick={() => onMaterial(targetTaxon)}>Associated material ↗</IntentButton></div></div>}
    <div className="lineage-plate">
      <div className="lineage-axis"><span>CLASSIFICATION MEMBERSHIP<br /><small>Branches carry no divergence dates</small></span><div className="lineage-ruler"><strong>← OLDER</strong><strong>PRESENT →</strong><div className="lineage-ticks">{[0,1,2,3,4].map(index => <span key={index} style={{ left: `${index * 25}%` }}>{Number((scale * (1 - index / 4)).toPrecision(4))} Ma</span>)}</div><div className="lineage-reference">{intervals.filter(unit => unit.rank === "Period" && unit.younger_ma < scale).map(unit => <span key={unit.id} style={{ left: `${position(Math.min(scale,unit.older_ma))}%`, width: `${(Math.min(scale,unit.older_ma) - unit.younger_ma) / scale * 100}%`, background: unit.color }} title={`${unit.name} / ICS v2026/06`}>{unit.name}</span>)}</div>{age.older_ma !== null && age.younger_ma !== null && <div className="lineage-selected-range" aria-hidden="true" style={{ left: `${position(Math.min(scale,age.older_ma))}%`, width: `${Math.max(0,Math.min(scale,age.older_ma) - Math.min(scale,age.younger_ma)) / scale * 100}%` }} />}</div><span>ASSERTIONS</span></div>
      <ul ref={tree} className="lineage-tree" role="tree" aria-label="Published classification members">{rows.map(item => <li key={item.id} className="lineage-node" role="none">
        <IntentButton allowFocus={() => !restoringFocus.current} prepare={() => { prefetchEntity(item); if(item.has_children)prefetchLineage(context,item.id); }} className="lineage-taxon" role="treeitem" aria-selected={activeTaxon === item.id} aria-level={(data?.breadcrumbs.length ?? 0) + (data?.items.length ? 1 : 0) || 1} aria-expanded={item.has_children ? false : undefined} onClick={() => select(item)} onKeyDown={event => {
          if (event.key === "ArrowRight" && item.has_children) { event.preventDefault(); onFocus(item.id); }
          if (event.key === "ArrowLeft") { event.preventDefault(); onFocus(data?.breadcrumbs.at(-2)?.id ?? null); }
          if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) { event.preventDefault(); const buttons = [...event.currentTarget.closest("ul")!.querySelectorAll<HTMLButtonElement>(".lineage-taxon")]; const index = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : buttons.indexOf(event.currentTarget) + (event.key === "ArrowDown" ? 1 : -1); buttons[Math.max(0,Math.min(buttons.length - 1,index))]?.focus(); }
        }}><span className="classification-rail" aria-hidden="true" /><TaxonVisual visual={resolveTaxonVisual(item)} /><span><small>{item.subtitle ?? "rank not supplied"}{item.is_source_identification ? " / identification" : " / source rank"}</small><strong>{item.label}</strong></span></IntentButton>
        <div className="lineage-span">{item.older_ma !== null && item.younger_ma !== null ? <><div className="material-envelope" style={{ left: `${position(item.older_ma)}%`, width: `${Math.max(.6,(item.older_ma - item.younger_ma) / scale * 100)}%` }} /><span>{ageLabel(item)}</span></> : <span className="lineage-unknown">No numeric envelope</span>}<small>{number(item.known_age_count)} known · {number(item.unknown_age_count)} unresolved</small></div>
        <div className="lineage-node-count"><strong>{number(item.assertion_count)}</strong><small>{number(item.source_taxon_count)} source taxa</small></div>
        <IntentButton prepare={() => prefetchLineage(context,item.id)} className="lineage-expand" disabled={!item.has_children} aria-label={`Expand ${item.label}`} onClick={() => onFocus(item.id)}>{item.has_children ? "Focus →" : "Leaf"}</IntentButton>
      </li>)}</ul>
      {!result.loading && !result.error && !rows.length && <p className="panel-message">No indexed material matches this classification and context. Unknown ages remain excluded by a numeric filter.</p>}
    </div>
    <div className="association-pagination"><span>{data?.total ?? 0} direct groups · 12 per page</span><button disabled={!cursors.length || result.loading} onClick={() => setNavigation({ base, cursors: cursors.slice(0,-1) })}>Previous branches</button><button disabled={!data?.next_cursor || result.loading} onClick={() => setNavigation({ base, cursors: [...cursors,data!.next_cursor!] })}>Next branches</button></div>
    <div className="scientific-caveat"><strong>Classification ≠ phylogeny. Material envelope ≠ biological duration.</strong><p>The rail connects source ranks. The separate time axis shows the union envelope of observed indexed material, often derived from broad geological labels. Gaps are not evidence of absence. Silhouettes are generated, curated body-plan cues, never specimen images or species reconstructions. Select a member to inspect its evidence; use Focus or arrow keys to navigate ranks.</p><a href="https://ipt.floridamuseum.ufl.edu/ipt/resource?r=ufvp">UFVP classification source / CC BY-NC 4.0 ↗</a></div>
  </div>;
}
