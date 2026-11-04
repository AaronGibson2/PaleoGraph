import { ageLabel } from "./state";
import type { RecordAction, RecordOverviewData } from "./recordOverview";

export function RecordOverviewCard({ record, onExplore }: { record: RecordOverviewData; onExplore: (action: RecordAction) => void }) {
  const knownAge = record.age.older_ma !== null && record.age.younger_ma !== null;
  return <div className="record-overview" aria-label="Record overview">
    <dl className="record-facts">
      <div><dt>{record.source === "pbdb" ? "Collection context" : "Locality"}</dt><dd><strong>{record.locality?.label ?? "Locality not supplied"}</strong><small>{record.source === "pbdb" ? "Published context · not mapped" : "Source locality"}</small></dd></div>
      <div><dt>Geological age</dt><dd><strong>{record.ageLabel ?? (knownAge ? ageLabel(record.age) : "Age unresolved")}</strong>{record.ageLabel && knownAge && <span>{ageLabel(record.age)}</span>}<small>{record.ageBasis}</small></dd></div>
    </dl>
    <div className="record-actions" role="group" aria-label="Explore this record">
      {record.locality && <button className="record-locality-action" onClick={() => onExplore({ intent: "locality", target: record.locality! })}>{record.source === "pbdb" ? "Explore collection context" : "Explore locality"}<span aria-hidden="true">↗</span></button>}
      {record.taxon && <><button onClick={() => onExplore({ intent: "classification", target: record.taxon! })}>View classification<span aria-hidden="true">↗</span></button><button onClick={() => onExplore({ intent: "material", target: record.taxon! })}>{record.source === "pbdb" ? "Related occurrences" : "Related material"}<span aria-hidden="true">↗</span></button></>}
    </div>
  </div>;
}
