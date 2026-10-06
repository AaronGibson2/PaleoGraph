"use client";

import { useState } from "react";
import { discovery, type AssociationItem, type EntityRef, type Page } from "../../lib/api/discovery";
import { ageLabel } from "./state";
import { useResource } from "./useResource";
import { browseKey } from "./browseCache";
import { prefetchLocality, prefetchLineage, prefetchMaterial, pivotContext } from "./browseIntent";
import { IntentButton } from "./IntentButton";
import { TaxonVisual } from "../taxon-visuals/TaxonVisual";
import { resolveTaxonVisual } from "../taxon-visuals/resolve";

const number = (value: number) => value.toLocaleString("en-US");

function AssociationList({ context, locality, onPivot }: { context: string; locality?: string | null; onPivot: (entity: EntityRef) => void }) {
  const [filter, setFilter] = useState("");
  const [order, setOrder] = useState("count");
  const [retry, setRetry] = useState(0);
  const [navigation, setNavigation] = useState<{ base: string; cursors: string[] }>({ base: "", cursors: [] });
  const base = `${context}&q=${encodeURIComponent(filter)}&order=${order}&limit=20`;
  const cursors = navigation.base === base ? navigation.cursors : [];
  const query = `${base}${cursors.length ? `&cursor=${encodeURIComponent(cursors.at(-1)!)}` : ""}`;
  const result = useResource<Page<AssociationItem>>(browseKey(locality ? `/localities/${locality}/taxa` : "/localities",query), signal => locality ? discovery.fauna(locality, query, signal) : discovery.localities(query, signal), 0, retry);
  return <section className="association-list" aria-busy={result.loading}>
    <div className="association-list-heading"><h3>{locality ? "Associated source identifications" : "Published localities"}</h3><span role="status">{result.data ? `${number(result.data.total)} ${locality ? "source taxa" : "localities"}` : "Reading associations…"}{result.loading && result.data && " / updating"}</span></div>
    <div className="association-tools"><label><span className="sr-only">Filter {locality ? "taxa" : "localities"}</span><input value={filter} onChange={event => setFilter(event.target.value)} placeholder={locality ? "Filter source identifications…" : "Filter localities…"} /></label><label><span className="sr-only">Association ordering</span><select aria-label="Association ordering" value={order} onChange={event => setOrder(event.target.value)}><option value="count">Most material</option><option value="name">Alphabetical</option>{locality && <option value="hierarchy">Source rank</option>}</select></label></div>
    <ol className="association-rows" start={cursors.length * 20 + 1}>{result.data?.items.map(item => <li key={item.id}><IntentButton prepare={() => item.kind==="locality" ? prefetchLocality(context,item) : prefetchLineage(pivotContext(context,item),item.id)} onClick={() => onPivot(item)}><span className="association-ordinal" aria-hidden="true">{locality ? <TaxonVisual visual={resolveTaxonVisual(item)} /> : "⌖"}</span><span><strong>{item.label}</strong><small>{item.subtitle ?? "Rank not supplied"} · {ageLabel(item)} · indexed material</small></span><span className="association-count"><strong>{number(item.assertion_count)}</strong><small>assertions</small></span><span aria-hidden="true">↗</span></IntentButton></li>)}</ol>
    {!result.loading && !result.error && !result.data?.items.length && <p className="panel-message">No current public material matches this context. Unknown ages do not match a numeric time filter.</p>}
    {result.error && <p role="alert">{result.error}. Last loaded associations retained. <button onClick={() => setRetry(value => value + 1)}>Retry associations</button></p>}
    <div className="association-pagination"><span>{cursors.length * 20 + (result.data?.items.length ? 1 : 0)}–{cursors.length * 20 + (result.data?.items.length ?? 0)}</span><button disabled={!cursors.length || result.loading} onClick={() => setNavigation({ base, cursors: cursors.slice(0, -1) })}>Previous associations</button><button disabled={!result.data?.next_cursor || result.loading} onClick={() => setNavigation({ base, cursors: [...cursors, result.data!.next_cursor!] })}>Next associations</button></div>
  </section>;
}

export function Localities({ id, identity, context, onPivot, onMaterial, onAtlas, onLineage, onClear }: { id?: string | null; identity?: EntityRef; context: string; onPivot: (entity: EntityRef) => void; onMaterial: () => void; onAtlas: () => void; onLineage: () => void; onClear: () => void }) {
  const [retry, setRetry] = useState(0);
  const result = useResource(id ? browseKey(`/localities/${id}`,context) : null, signal => discovery.locality(id!, context, signal), 0, retry);
  const data = id && result.data?.entity.id===id ? result.data : undefined;
  const p = data?.properties;
  const geography = (p?.geography ?? {}) as Record<string, unknown>;
  return <div className="scientific-surface locality-surface" aria-label="Locality explorer">
    <div className="surface-introduction"><div><p className="eyebrow">Place / collected evidence</p><h2>{data?.entity.label ?? (identity && identity.id===id ? identity.label : id ? "Reading the locality…" : "Localities of Florida")}</h2><p>Source-scoped places, kept distinct even where published coordinates coincide.</p></div><span className="plate-number" aria-hidden="true">02 / LOCALITIES</span></div>
    {id && !data && <p role="status">{result.error ?? "Reading locality associations…"}{result.error && <button onClick={() => setRetry(value => value + 1)}>Retry locality</button>}</p>}
    {id && data && (result.loading || result.error) && <p className="snapshot-status" role={result.error ? "alert" : "status"}>{result.error ?? "Updating locality"}. Showing the last loaded locality and counts.{result.error && <button onClick={() => setRetry(value => value + 1)}>Retry locality</button>}</p>}
    {id && <>
      {data && <div className="locality-actions"><button onClick={onClear}>All matching localities</button><button disabled={result.loading} onClick={onAtlas}>Show on Atlas ↗</button><button disabled={result.loading} onClick={onLineage}>Locality in Lineage ↗</button><IntentButton prepare={() => prefetchMaterial(context)} disabled={result.loading} onClick={onMaterial}>Associated material ↗</IntentButton></div>}
      <div className="locality-columns"><div>{data && <>
        <dl className="locality-counts"><div><dt>Catalog assertions</dt><dd>{number(data.assertion_count)}</dd></div><div><dt>Distinct specimens</dt><dd>{number(data.specimen_count)}</dd></div><div><dt>Distinct source taxa</dt><dd>{number(data.source_taxon_count)}</dd></div><div><dt>Collections / institutions</dt><dd>{data.collection_count} / {data.institution_count}</dd></div></dl>
        <section className="locality-position"><p className="eyebrow">Public position / source precision</p><h3>{p?.location_is_withheld ? "Coordinates withheld" : p?.latitude == null ? "Coordinates unavailable" : `${Math.abs(Number(p.latitude))}° ${Number(p.latitude) < 0 ? "S" : "N"}, ${Math.abs(Number(p.longitude))}° ${Number(p.longitude) < 0 ? "W" : "E"}`}</h3><p>{p?.location_is_generalized ? "Generalized position. " : ""}Uncertainty: {p?.coordinate_uncertainty_m == null ? "not supplied" : `${String(p.coordinate_uncertainty_m)} m`}. Datum: {String(p?.geodetic_datum ?? "not supplied")}.</p><p>{[geography.county, geography.stateProvince, geography.country].filter(Boolean).map(String).join(" / ")}</p></section>
        <section className="locality-geology"><p className="eyebrow">Source geology / verbatim labels</p><h3>Stratigraphic context</h3>{data.source_terms.length ? <dl>{data.source_terms.map(term => <div key={`${term.field}:${term.label}`}><dt>{term.namespace} / {term.field}</dt><dd>{term.label}<small>{number(term.assertion_count)} assertions</small></dd></div>)}</dl> : <p>Source geological labels not supplied.</p>}<p className="context-note">NALMA is regional biochronology. These labels do not infer a formation age or a formal ICS correlation.</p></section>
        <section><p className="eyebrow">Custody / associated material</p>{data.custody.map(item => <p key={item.collection_id ?? "none"}>{item.institution ?? "Institution not supplied"} / {item.collection ?? "Collection not supplied"} · {number(item.assertion_count)} assertions</p>)}</section>
      </>} </div><div>
        {data && <section className="locality-time"><p className="eyebrow">Observed material envelope</p><h3>{ageLabel(data)}</h3><p>Aggregate of material envelopes in this context, not source-supplied locality geology or evidence of contemporaneity. Numeric bounds may be source supplied or derived from versioned geological labels.</p><div className="age-coverage"><strong>{number(data.known_age_count)}</strong><span>assertions with complete numeric bounds</span><strong>{number(data.unknown_age_count)}</strong><span>with unresolved age</span></div><ol>{data.interpreted_intervals.map((interval,index) => <li key={index}><span>{interval.source_label ?? "Age label absent"}<small>{interval.age_basis} · {ageLabel(interval)}</small></span><strong>{number(interval.assertion_count)}</strong></li>)}</ol></section>}
        <AssociationList key={id} context={context} locality={id} onPivot={onPivot} />
      </div></div>
      {data && <section className="related-localities"><h3>Other localities sharing source identifications</h3><p>Showing up to 12 public localities. Shared recorded taxa are an association, not an ecosystem reconstruction.</p><div>{data.related_localities.map(item => <IntentButton key={item.id} prepare={() => prefetchLocality(context,item)} onClick={() => onPivot(item)}>{item.label} ↗</IntentButton>)}</div></section>}
      <div className="scientific-caveat"><strong>Locality association ≠ contemporaneous community.</strong><p>Counts describe current museum assertions under the active taxon, custody and time filters. Multiple specimens and source identifications may represent different collection events and intervals. <a href="https://ipt.floridamuseum.ufl.edu/ipt/resource?r=ufvp">UFVP source evidence / CC BY-NC 4.0 ↗</a></p></div>
    </>}
    {!id && <AssociationList context={context} onPivot={onPivot} />}
  </div>;
}
