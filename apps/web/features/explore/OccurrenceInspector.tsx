"use client";

import { useEffect, useRef } from "react";
import type { OccurrenceDetail } from "../../lib/api/types";
import { ageLabel } from "./state";

type Props = { selected: string; data?: OccurrenceDetail; error?: string; outsideResults: boolean; onClose: () => void; onRetry: () => void };
function externalUrl(value: string | null): string | undefined {
  if (!value) return undefined;
  try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? url.href : undefined; } catch { return undefined; }
}

export function OccurrenceInspector({ selected, data, error, outsideResults, onClose, onRetry }: Props) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [selected]);
  return <aside className="inspector" aria-labelledby="inspection-heading" onKeyDown={event => { if (event.key === "Escape") onClose(); }}>
    <div className="inspector-top"><p className="eyebrow">{data?.specimen ? "Museum catalog / UFVP" : "Occurrence · inspection"}</p><button className="icon-button" aria-label="Close occurrence inspection" onClick={onClose}>×</button></div>
    {data?.specimen && <p className="specimen-accession">{data.specimen.collection_code ?? "Collection unknown"} / {data.specimen.catalog_number ?? "Catalog number not supplied"}</p>}
    <h2 id="inspection-heading" tabIndex={-1} ref={heading}>{data ? <em>{data.scientific_name}</em> : "Occurrence"}</h2>
    {!data && !error && <p role="status">Loading scientific context…</p>}
    {error && <div role="alert"><p>{error}</p><button className="quiet-button" onClick={onRetry}>Retry inspection</button></div>}
    {data && <>
      <p className="inspection-age">{data.specimen ? data.early_interval_name ?? ageLabel(data) : ageLabel(data)}{data.specimen && <span className="fact-note">Source geological label · numeric age unknown</span>}</p>
      {data.evidence.some(record => record.is_synthetic) && <p className="demo-note">Synthetic demo assertion. This is not evidence of a real fossil occurrence.</p>}
      {outsideResults && <p className="uncertainty-label">Selected record is outside the current map results.</p>}
      <p className="inspection-source">{data.evidence.length ? `Source: ${data.evidence.map(record => record.dataset_title).join(" · ")}` : "Source evidence unavailable"}</p>
      <dl className="scientific-facts">
        {data.specimen && <><div><dt>Institution / collection</dt><dd>{data.specimen.institution ?? "Not supplied"}<span className="fact-note">{data.specimen.institution_code} · {data.specimen.collection_code}</span></dd></div><div><dt>Cataloged material</dt><dd>{data.specimen.preparations ?? "Preparation not supplied"}<span className="fact-note">Source individualCount: {data.specimen.individual_count ?? "not supplied"} · a catalog entry may contain several pieces</span></dd></div></>}
        <div><dt>Locality</dt><dd>{data.locality_name ?? "Not recorded"}</dd></div>
        <div><dt>Collection context</dt><dd>{data.collection_event_name}</dd></div>
        {(data.older_ma === null || data.younger_ma === null) && <div><dt>Age bounds</dt><dd>Older: {data.older_ma ?? "unknown"}{data.older_ma !== null && " Ma"}<br />Younger: {data.younger_ma ?? "unknown"}{data.younger_ma !== null && " Ma"}</dd></div>}
        {!data.specimen && <div><dt>Stratigraphy</dt><dd>{data.stratigraphy ?? "Not recorded"}</dd></div>}
        <div><dt>Location</dt><dd>{data.location_is_withheld ? "Coordinates withheld" : data.latitude === null || data.longitude === null ? "Coordinates unknown" : `${data.latitude.toFixed(3)}°, ${data.longitude.toFixed(3)}°`}
          {data.location_is_generalized && <span className="fact-note">Generalized position</span>}
          {data.coordinate_uncertainty_m !== null && <span className="fact-note">Uncertainty: {data.coordinate_uncertainty_m.toLocaleString("en-US")} m</span>}
        </dd></div>
      </dl>
      {!data.specimen && <p className="context-note">{data.context}</p>}
      {data.specimen && <>
        <section className="source-values" aria-labelledby="source-values-heading"><h3 id="source-values-heading">Source-supplied field label</h3><dl className="scientific-facts">{Object.entries(data.source_values ?? {}).map(([term, value]) => <div key={term}><dt>{term.replace(/([a-z])([A-Z])/g, "$1 $2")}</dt><dd>{value}</dd></div>)}</dl></section>
        <section className="specimen-identifiers"><h3>Material & assertion identifiers</h3><dl className="scientific-facts"><div><dt>Occurrence ID · source</dt><dd>{data.specimen.occurrence_identifier ?? "Not supplied"}</dd></div><div><dt>Material entity ID · source</dt><dd>{data.specimen.material_entity_identifier ?? "Not supplied"}</dd></div><div><dt>Specimen · PaleoGraph</dt><dd>{data.specimen.id}</dd></div></dl><p className="context-note">PaleoGraph retains the source identification and published WGS84 position for navigation. No numeric age was inferred from geological names. Original modified times without a time zone remain verbatim.</p></section>
      </>}
      <section className="provenance" aria-labelledby="provenance-heading">
        <h3 id="provenance-heading">Sources & evidence</h3>
        {data.evidence.length === 0 && <p>No source evidence is available.</p>}
        {data.evidence.map(record => <div className="evidence-record" key={`${record.dataset_id}:${record.source_record_id}`}>
          <strong>{record.dataset_title}</strong><p>{record.source_name}</p>
          <dl><div><dt>Record</dt><dd>{record.source_record_id}</dd></div><div><dt>Version</dt><dd>{record.dataset_version ?? "Not supplied"}</dd></div><div><dt>License</dt><dd>{record.license ?? "Not supplied"}</dd></div></dl>
          <p>{record.citation ?? `${record.publisher ?? record.source_name}. ${record.dataset_title}, version ${record.dataset_version ?? "not supplied"}. Normalized for PaleoGraph; no publisher-supplied formatted citation.`}</p>
          {!record.is_current && <p className="uncertainty-label">Historical source record</p>}
          {record.information_withheld && <p>{record.information_withheld}</p>}
          {record.data_generalizations && <p>{record.data_generalizations}</p>}
          {externalUrl(record.source_url) && <a href={externalUrl(record.source_url)} target="_blank" rel="noopener noreferrer">Source record ↗</a>}
          {externalUrl(record.dataset_url) && <a href={externalUrl(record.dataset_url)} target="_blank" rel="noopener noreferrer">Source dataset ↗</a>}
        </div>)}
      </section>
      <p className="context-note">{data.specimen ? "This occurrence assertion is linked to cataloged fossil material; it does not imply a single organism or fragment. " : "A source-supported assertion is not a physical specimen. "}Taxon names are navigation concepts, not a universal taxonomic authority.</p>
    </>}
  </aside>;
}
