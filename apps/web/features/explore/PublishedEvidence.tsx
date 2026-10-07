import type { PublishedOccurrence } from "../../lib/api/discovery";
import { ageLabel } from "./state";

export function PublishedEvidence({ evidence }: { evidence: PublishedOccurrence }) {
  const latest=evidence.latest_identification;
  const original=evidence.original_identification;
  const age=evidence.provider_age;
  const position=evidence.modern_position;
  return <>
    <section><p className="eyebrow">PBDB source supplied</p><h3>Taxonomic evidence</h3><dl className="scientific-facts"><div><dt>Original identification</dt><dd>{original.identified_name ?? "Not supplied"}</dd></div><div><dt>Latest identification</dt><dd>{latest.identified_name ?? "Not supplied"}</dd></div><div><dt>Accepted name · PBDB</dt><dd>{latest.accepted_name ?? "Not supplied"}</dd></div><div><dt>Qualifiers</dt><dd>{[latest.genus_reso,latest.species_reso].filter(Boolean).join(" / ") || "Not supplied"}</dd></div></dl></section>
    <section><p className="eyebrow">Provider calibrated temporal evidence</p><h3>{ageLabel(age)}</h3><p>{[age.early_interval,age.late_interval].filter(Boolean).join(" / ") || "Interval names not supplied"}</p><p className="context-note">PaleoGraph browses the complete PBDB provider envelope. These bounds are separate from determined dates and do not describe biological duration.</p><dl className="scientific-facts">{Object.entries(age.determined_dates).map(([name,date])=><div key={name}><dt>Determined {name} date</dt><dd>{date.value ?? "Not supplied"}{date.value && ` ${date.unit ?? "unit not supplied"}`}{date.error && ` ± ${date.error}`}<small>{date.method}</small></dd></div>)}</dl><small>{age.policy}</small></section>
    <section><h3>Modern position · source evidence</h3><p>{position.longitude===null || position.latitude===null ? "Coordinates not supplied" : `${position.latitude}°, ${position.longitude}°`}</p><p className="context-note">{position.status.replaceAll("-"," ")} · {position.basis ?? "basis not supplied"} · {position.precision ?? "precision not supplied"}. No validated modern map position is assigned.</p></section>
    <section><h3>Explicit material evidence</h3><p>{evidence.material_evidence_count} source material records. No canonical PBDB specimen identity is asserted.</p>{evidence.materials.map(item=><p key={item.source_record_id}>{item.catalog_label ?? "Material label not supplied"}</p>)}{evidence.materials_has_more && <p>Showing the first 10 material labels.</p>}</section>
    <details className="provenance"><summary>Source provenance</summary><p>PBDB occurrence {evidence.external_id} · {evidence.license}</p><p>Source content SHA-256: {evidence.content_hash}</p><p>Normalization SHA-256: {evidence.normalization_hash}</p><a href={`https://paleobiodb.org/classic/basicCollectionSearch?occurrence_no=${encodeURIComponent(evidence.external_id)}`} target="_blank" rel="noopener noreferrer">PBDB source evidence ↗</a></details>
  </>;
}
