"use client";

import { useEffect, useRef } from "react";
import { api } from "../../lib/api/client";
import { discovery, type EntityDetail, type EntityKind, type EntityRef } from "../../lib/api/discovery";
import type { GeologicalInterval, OccurrenceDetail, Viewport } from "../../lib/api/types";
import { SpecimenVisual } from "./ScientificVisual";
import { TaxonVisual } from "../taxon-visuals/TaxonVisual";
import { resolveTaxonVisual } from "../taxon-visuals/resolve";
import { useResource } from "./useResource";
import { entityKey, occurrenceKey, inspectionAssertion, type BrowseTarget } from "./browseIntent";

const numeric = (value: unknown) => typeof value === "number" || typeof value === "string" ? Number(value).toLocaleString("en-US", { maximumFractionDigits: 4 }) : "unknown";
const safeUrl = (value: string | null) => { try { const url = new URL(value ?? ""); return ["http:", "https:"].includes(url.protocol) ? url.href : undefined; } catch { return undefined; } };

export function EntityInspector({ kind, id, identity, context, viewport, onPivot, onClose, onGraph, onLocality, onLineage, onInterval, onPosition, retry }: { kind: EntityKind; id: string; identity?: BrowseTarget; context: string; viewport: Viewport; onPivot: (entity: EntityRef) => void; onClose: () => void; onGraph: () => void; onLocality: () => void; onLineage: () => void; onInterval: (interval: GeologicalInterval) => void; onPosition: (id: string, longitude: number, latitude: number) => void; retry: number }) {
  const result = useResource<EntityDetail>(entityKey({kind,id}), signal => discovery.entity(kind, id, context, signal), 0, retry);
  const occurrenceId = inspectionAssertion(kind,id,result.data,identity);
  const occurrence = useResource<OccurrenceDetail>(typeof occurrenceId === "string" ? occurrenceKey(occurrenceId) : null, signal => api.occurrence(String(occurrenceId), signal), 0, retry);
  const data = result.data?.entity.id === id ? result.data : undefined;
  const specimen = occurrence.data && occurrence.data.id===occurrenceId && occurrence.data.specimen?.id === id ? occurrence.data : undefined;
  const longitude = specimen?.longitude;
  const latitude = specimen?.latitude;
  useEffect(() => {
    if (typeof longitude === "number" && typeof latitude === "number") onPosition(id, longitude, latitude);
  }, [id, longitude, latitude, onPosition]);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [id, kind]);
  const known = data?.entity ?? (identity?.id===id && identity.kind===kind ? identity : undefined);
  const p = data?.properties;
  const interval = p?.interval as GeologicalInterval | undefined;
  const outside = specimen?.longitude != null && specimen.latitude != null && (specimen.latitude < viewport.south || specimen.latitude > viewport.north || (viewport.west <= viewport.east ? specimen.longitude < viewport.west || specimen.longitude > viewport.east : specimen.longitude < viewport.west && specimen.longitude > viewport.east));
  const sourceLink = (value: string) => data?.related.find(entity => entity.label === value || entity.subtitle === value);
  return <aside className="inspector" aria-labelledby="inspection-heading" onKeyDown={event => { if (event.key === "Escape") onClose(); }}>
    <div className="inspector-top"><p className="eyebrow">{kind === "specimen" ? "Material / field label" : `${kind} / explorer`}</p><button className="icon-button" aria-label="Close occurrence inspection" onClick={onClose}>×</button></div>
    <h2 id="inspection-heading" ref={heading} tabIndex={-1}>{known?.label ?? "Reading the record…"}</h2>
    {known?.subtitle && <p className="inspector-subtitle inspection-taxon-cue">{(kind === "taxon" || kind === "specimen") && <TaxonVisual visual={resolveTaxonVisual(known)} />}{known.subtitle}</p>}
    {!data && <p role="status">{result.error ?? "Loading scientific context…"}</p>}
    {data && <>
      {outside && <p className="uncertainty-label">Selected record is outside the current map results. Its source evidence remains available.</p>}
      {kind === "specimen" && <SpecimenVisual />}
      <div className="entity-stat"><strong>{data.material_count.toLocaleString("en-US")}</strong><span>catalog assertions<br /><small>{data.mapped_count.toLocaleString("en-US")} with usable coordinates</small></span></div>
      {(kind === "taxon" || kind === "locality") && <div className="inspector-pivots"><button onClick={onLocality}>{kind === "locality" ? "Explore this locality" : "Associated localities"} ↗</button><button onClick={onLineage}>{kind === "locality" ? "Locality in Lineage" : "Explore in Lineage"} ↗</button></div>}
      <button className="relationship-link" onClick={onGraph}>Explore relationships <span aria-hidden="true">↗</span></button>
      {p?.authority && <p className="context-note">{String(p.authority)}</p>}
      {kind === "term" && <p className="context-note">{String(p?.namespace)} / {String(p?.field)}{p?.namespace === "NALMA" || p?.namespace === "source-biochronology" ? ". Regional biochronology; no numeric ICS correlation inferred." : ". Exact source label; no inferred formation age."}</p>}
      {kind === "specimen" && p && <section className="interpretation" aria-labelledby="interpretation-heading"><p className="eyebrow">PaleoGraph interpretation</p><h3 id="interpretation-heading">{p.status === "mapped" ? `${numeric(p.older_ma)}–${numeric(p.younger_ma)} Ma` : "Numerical age unresolved"}</h3>{interval && <button className="scientific-link" onClick={() => onInterval(interval)}>{interval.name} · {interval.rank} ↗</button>}<p>{p.status === "mapped" ? "Reference interval envelope, not a measured specimen age." : `Source interpretation: ${String(p.status)}. No numerical age invented.`}</p><dl><div><dt>Source assertion</dt><dd>{String(p.source_label ?? "Not supplied")}</dd></div><div><dt>Rule / reference</dt><dd>{String(p.rule)}<br />{String(p.policy_version)}</dd></div></dl><details><summary>Interpretation provenance</summary><p>Source content SHA-256: {String(p.content_hash)}</p><p>Interpreted: {String(p.interpreted_at)}</p>{interval?.formal_status && <p>Reference status: {interval.formal_status.replaceAll("_", " ")}</p>}{interval?.older_boundary?.margin_of_error_ma && <p>Older reference calibration uncertainty: ±{interval.older_boundary.margin_of_error_ma} Ma</p>}{interval?.younger_boundary?.margin_of_error_ma && <p>Younger reference calibration uncertainty: ±{interval.younger_boundary.margin_of_error_ma} Ma</p>}</details></section>}
      <section className="entity-connections"><p className="eyebrow">Follow the evidence</p><h3>Associated context</h3>{data.related.map(entity => <button key={`${entity.kind}:${entity.id}`} onClick={() => onPivot(entity)}><span>{entity.kind}<small>{entity.subtitle}</small></span><strong>{entity.label}</strong><span aria-hidden="true">↗</span></button>)}{data.related_has_more && <button className="relationship-link" onClick={onGraph}>More context in relationships →</button>}</section>
      {kind === "locality" && p && <section><h3>Published position</h3><p>{p.location_is_withheld ? "Coordinates withheld" : p.longitude === null ? "Coordinates unavailable" : `${numeric(p.latitude)}°, ${numeric(p.longitude)}°`}</p><p className="context-note">{p.location_is_generalized ? "Generalized location. " : ""}Coordinate uncertainty: {p.coordinate_uncertainty_m === null ? "not supplied" : `${numeric(p.coordinate_uncertainty_m)} m`}. Datum: {String(p.geodetic_datum ?? "not supplied")}.</p></section>}
      {specimen && <>
        <section><h3>Cataloged material</h3><dl className="scientific-facts"><div><dt>Institution / collection</dt><dd>{specimen.specimen?.institution}<small>{specimen.specimen?.collection_code}</small></dd></div><div><dt>Preparation</dt><dd>{specimen.specimen?.preparations ?? "Not supplied"}</dd></div><div><dt>Individual count · source</dt><dd>{specimen.specimen?.individual_count ?? "Not supplied"}</dd></div><div><dt>Source numeric ages</dt><dd>Older: {specimen.older_ma ?? "not supplied"}<br />Younger: {specimen.younger_ma ?? "not supplied"}</dd></div><div><dt>Published position</dt><dd>{specimen.location_is_withheld ? "Coordinates withheld" : specimen.longitude === null ? "Not supplied" : `${numeric(specimen.latitude)}°, ${numeric(specimen.longitude)}°`}{specimen.location_is_generalized && <small>Generalized position</small>}{specimen.coordinate_uncertainty_m !== null && <small>Uncertainty {specimen.coordinate_uncertainty_m.toLocaleString("en-US")} m</small>}</dd></div></dl></section>
        <section className="source-values"><p className="eyebrow">Museum assertion</p><h3>Source-supplied field label</h3><dl className="scientific-facts">{Object.entries(specimen.source_values ?? {}).map(([key, value]) => <div key={key}><dt>{key.replace(/([a-z])([A-Z])/g, "$1 $2")}</dt><dd>{sourceLink(value) ? <button className="scientific-link" onClick={() => onPivot(sourceLink(value)!)}>{value} ↗</button> : value}</dd></div>)}</dl></section>
        <section className="specimen-identifiers"><h3>Material & assertion identifiers</h3><dl className="scientific-facts"><div><dt>Occurrence ID · source</dt><dd>{specimen.specimen?.occurrence_identifier ?? "Not supplied"}</dd></div><div><dt>Material entity ID · source</dt><dd>{specimen.specimen?.material_entity_identifier ?? "Not supplied"}</dd></div><div><dt>Other source identifiers</dt><dd>{JSON.stringify(specimen.specimen?.other_identifiers ?? {})}</dd></div><div><dt>Specimen · PaleoGraph</dt><dd>{id}</dd></div></dl></section>
        <section className="provenance"><p className="eyebrow">Museum source evidence</p><h3>Sources & evidence</h3>{specimen.evidence.map(record => <div key={`${record.dataset_id}:${record.source_record_id}`}><strong>{record.dataset_title}</strong><dl><div><dt>Source record</dt><dd>{record.source_record_id}</dd></div><div><dt>Dataset version</dt><dd>{record.dataset_version}</dd></div><div><dt>License / rights</dt><dd>{record.license}<br />{record.rights_holder}</dd></div><div><dt>Ingestion run</dt><dd>{record.ingestion_run_id}<br />{record.ingested_at}</dd></div></dl><p>{record.citation ?? "Publisher-supplied formatted citation unavailable."}</p>{!record.is_current && <p>Historical source record</p>}{record.information_withheld && <p>{record.information_withheld}</p>}{record.data_generalizations && <p>{record.data_generalizations}</p>}{safeUrl(record.source_url) && <a href={safeUrl(record.source_url)} target="_blank" rel="noopener noreferrer">Museum record ↗</a>}{safeUrl(record.dataset_url) && <a href={safeUrl(record.dataset_url)} target="_blank" rel="noopener noreferrer">Source dataset ↗</a>}</div>)}</section>
      </>}
      <section className="research-evidence"><p className="eyebrow">Research evidence</p><h3>Literature connections</h3><p>{data.research_note}</p><a href="https://ipt.floridamuseum.ufl.edu/ipt/resource?r=ufvp" target="_blank" rel="noopener noreferrer">UFVP dataset · CC BY-NC 4.0 ↗</a></section>
      <p className="context-note">A catalog entry may contain multiple organisms or pieces. Published coordinates and geological interpretations retain source uncertainty. Absence of material here is not evidence of fossil absence.</p>
    </>}
    {(result.error || occurrence.error) && <p role="alert">{result.error ?? occurrence.error}</p>}
  </aside>;
}
