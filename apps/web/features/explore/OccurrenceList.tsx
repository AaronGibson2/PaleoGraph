import type { MapOccurrence } from "../../lib/api/types";
import { ageLabel } from "./state";

type Props = { items: MapOccurrence[]; selected: string | null; onSelect: (id: string) => void };

export function OccurrenceList({ items, selected, onSelect }: Props) {
  return <ol className="occurrence-list" aria-label="Occurrences in the current viewport">
    {items.map(item => <li key={item.id}>
      <button id={`result-${item.id}`} aria-pressed={selected === item.id} onClick={() => onSelect(item.id)}>
        <span className={`record-dot${item.older_ma === null || item.younger_ma === null ? " unknown" : ""}`} aria-hidden="true" />
        <span className="record-copy">{item.catalog_label && <span className="catalog-label">{item.catalog_label}</span>}<em>{item.scientific_name}</em><span>{item.locality_name}</span><span className="record-age">{!item.is_synthetic && item.source_age_label && (item.older_ma === null || item.younger_ma === null) ? `${item.source_age_label} · source label` : ageLabel(item)}</span>
          {item.location_is_generalized && <span className="uncertainty-label">Approximate location</span>}
        </span>{selected === item.id && <span className="record-selected">Selected</span>}
      </button>
    </li>)}
  </ol>;
}
