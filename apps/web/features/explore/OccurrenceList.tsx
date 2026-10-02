import type { MapOccurrence } from "../../lib/api/types";
import { ageLabel } from "./state";

type Props = { items: MapOccurrence[]; selected: string | null; onSelect: (id: string) => void };

export function OccurrenceList({ items, selected, onSelect }: Props) {
  return <ol className="occurrence-list" aria-label="Occurrences in the current viewport">
    {items.map((item, index) => <li key={item.id}>
      <button id={`result-${item.id}`} aria-pressed={selected === item.id} onClick={() => onSelect(item.id)}>
        <span className="record-index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
        <span className="record-copy"><em>{item.scientific_name}</em><span>{item.locality_name}</span><span className="record-age">{ageLabel(item)}</span>
          {item.location_is_generalized && <span className="uncertainty-label">Approximate location</span>}
        </span><span aria-hidden="true" className="record-arrow">↗</span>
      </button>
    </li>)}
  </ol>;
}
