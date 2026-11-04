import type { EntityDetail, EntityRef } from "../../lib/api/discovery.ts";
import type { AgeRange, OccurrenceDetail } from "../../lib/api/types.ts";
import { explorationSource } from "./discoveryContext.ts";
import type { ExploreState } from "./state.ts";

export type RecordAction = { intent: "locality" | "classification" | "material"; target: EntityRef };
export type RecordOverviewData = {
  source: "ufvp" | "pbdb";
  locality: EntityRef | null;
  taxon: EntityRef | null;
  age: AgeRange;
  ageLabel: string | null;
  ageBasis: "Source numeric bounds" | "Interpreted reference envelope" | "PBDB provider envelope" | "Numeric age unresolved";
};

const wording = (value: unknown) => typeof value === "string" && value.trim() ? value : null;
function bound(value: unknown): number | null {
  if (typeof value !== "number" && !(typeof value === "string" && value.trim())) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= 0 ? numeric : null;
}
function complete(older: unknown, younger: unknown): AgeRange | null {
  const older_ma = bound(older), younger_ma = bound(younger);
  return older_ma !== null && younger_ma !== null && older_ma >= younger_ma ? { older_ma, younger_ma } : null;
}

export function meaningfulPreparation(value: string | null | undefined): boolean {
  return !!value?.trim() && !/^(?:default|none|unspecified|unknown|not supplied|n\/a)(?:\s*-\s*\d+)?$/i.test(value.trim());
}

export function recordOverview(detail: EntityDetail, occurrence?: OccurrenceDetail): RecordOverviewData | null {
  if (detail.entity.kind !== "specimen" && detail.entity.kind !== "occurrence") return null;
  // A cached assertion from another selection must never supply this record's facts.
  const specimen = occurrence?.specimen?.id === detail.entity.id && occurrence.id === detail.properties.occurrence_id ? occurrence : undefined;
  const source: RecordOverviewData["source"] = detail.entity.source === "pbdb" ? "pbdb" : "ufvp";
  const localities = detail.related.filter(entity => entity.kind === "locality");
  const locality: EntityRef | null = specimen?.locality_id ? { kind: "locality" as const, id: specimen.locality_id, label: specimen.locality_name ?? "Locality", subtitle: null, source } : localities.length === 1 ? { ...localities[0], source } : null;
  const taxa = detail.related.filter(entity => entity.kind === "taxon");
  const taxon: EntityRef | null = specimen ? { kind: "taxon" as const, id: specimen.taxon_id, label: specimen.scientific_name, subtitle: "Source identification", source } : detail.entity.kind === "occurrence" && taxa.length === 1 ? { ...taxa[0], source } : null;
  let age: AgeRange | null = null;
  let ageBasis: RecordOverviewData["ageBasis"] = "Numeric age unresolved";
  let ageLabel: string | null = null;
  if (detail.occurrence) {
    const provider = detail.occurrence.provider_age;
    age = complete(provider.older_ma, provider.younger_ma);
    if (age) ageBasis = "PBDB provider envelope";
    ageLabel = [...new Set([provider.early_interval, provider.late_interval].filter((value): value is string => !!wording(value)))].join(" / ") || null;
  } else {
    ageLabel = wording(detail.properties.source_label);
    age = specimen ? complete(specimen.older_ma, specimen.younger_ma) : null;
    if (age) ageBasis = "Source numeric bounds";
    else if (detail.properties.status === "mapped") {
      age = complete(detail.properties.older_ma, detail.properties.younger_ma);
      if (age) ageBasis = "Interpreted reference envelope";
    }
  }
  return { source, locality, taxon, age: age ?? { older_ma: null, younger_ma: null }, ageLabel, ageBasis };
}

export function recordNavigationPatch(state: Pick<ExploreState, "source" | "surface">, action: RecordAction): Partial<ExploreState> {
  const current = explorationSource(state);
  const owner = action.target.source;
  const source = current === "all" || !owner || current === owner ? current : owner;
  const common: Partial<ExploreState> = { source, selected: null, selected_kind: undefined, inspect: "closed", discover: null, catalog: null, at_lon: null, at_lat: null };
  if (action.intent === "locality") return { ...common, surface: "localities", locality_id: action.target.id };
  if (action.intent === "classification") return { ...common, surface: "lineage", lineage_focus: action.target.id, taxonomy_focus: null };
  return { ...common, catalog: "open", catalog_scope: "archive", catalog_q: "", taxon_id: action.target.id, locality_id: null };
}
