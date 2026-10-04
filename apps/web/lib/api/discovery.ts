import type { AgeRange, Viewport } from "./types.ts";
import { request } from "./client.ts";

export type EntityKind = "specimen" | "taxon" | "locality" | "collection" | "institution" | "term";
export type EntityRef = { kind: EntityKind; id: string; label: string; subtitle: string | null; classification?: string[]; classification_path_ids?: string[] };
export type ExplorationContext = {
  taxon_id?: string | null; locality_id?: string | null; collection_id?: string | null;
  institution_id?: string | null; term_id?: string | null; at_lon?: number | null; at_lat?: number | null;
  q?: string;
};
export type CatalogItem = AgeRange & {
  id: string; specimen_id: string; label: string; scientific_name: string; taxon_id: string;
  /** Identification first, then nearest source-classification parents. */
  classification_path_ids?: string[];
  locality_id: string | null; locality_name: string | null; longitude: number | null;
  latitude: number | null; age_basis: string; source_age_label: string | null;
};
export type Page<T> = { items: T[]; total: number; next_cursor: string | null; limit: number };
export type Place = {
  id: string; longitude: number; latitude: number; record_count: number; locality_count: number;
  interpreted_count: number; location_is_generalized: boolean;
};
export type PlacePage = { items: Place[]; total_records: number; total_places: number; unmapped_records: number; next_cursor: string | null; limit: number };
export type EntityDetail = { entity: EntityRef; material_count: number; mapped_count: number; related: EntityRef[]; related_has_more: boolean; properties: Record<string, unknown>; research_note: string };
export type GraphPage = { root: EntityRef; nodes: EntityRef[]; edges: { source: string; target: string; label: string }[]; total_neighbors: number; next_cursor: string | null; limit: number };
export type AssociationItem = EntityRef & AgeRange & { assertion_count: number; specimen_count: number; source_taxon_count: number; known_age_count: number; unknown_age_count: number };
export type LocalitySummary = {
  entity: EntityRef; assertion_count: number; specimen_count: number; source_taxon_count: number;
  collection_count: number; institution_count: number; known_age_count: number; unknown_age_count: number;
  older_ma: number | null; younger_ma: number | null; properties: Record<string, unknown>;
  source_terms: { field: string; namespace: string; label: string; assertion_count: number }[];
  interpreted_intervals: { interval_id: string | null; source_label: string | null; age_basis: string; older_ma: number | null; younger_ma: number | null; assertion_count: number }[];
  custody: { collection_id: string | null; collection: string | null; institution: string | null; assertion_count: number }[];
  related_localities: EntityRef[];
};
export type LineageItem = AssociationItem & { parent_id: string | null; has_children: boolean; classification: string[]; is_source_identification: boolean };
export type LineagePage = Page<LineageItem> & { focus: EntityRef | null; breadcrumbs: EntityRef[]; focal: LineageItem | null; relationship: string };

export const contextKeys = ["taxon_id", "locality_id", "collection_id", "institution_id", "term_id", "at_lon", "at_lat"] as const;
export function contextQuery(age: AgeRange & ExplorationContext, viewport?: Viewport): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of [...contextKeys, "older_ma", "younger_ma"] as const) {
    const value = age[key];
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  if (viewport) for (const [key, value] of Object.entries(viewport)) params.set(key, String(value));
  return params;
}
export const discovery = {
  localities: (query: string, signal?: AbortSignal) => request<Page<AssociationItem>>(`/localities?${query}`, signal),
  locality: (id: string, query: string, signal?: AbortSignal) => request<LocalitySummary>(`/localities/${encodeURIComponent(id)}?${query}`, signal),
  fauna: (id: string, query: string, signal?: AbortSignal) => request<Page<AssociationItem>>(`/localities/${encodeURIComponent(id)}/taxa?${query}`, signal),
  lineage: (query: string, signal?: AbortSignal) => request<LineagePage>(`/lineage?${query}`, signal),
  catalog: (query: string, signal?: AbortSignal) => request<Page<CatalogItem>>(`/catalog?${query}`, signal),
  search: (query: string, signal?: AbortSignal) => request<Page<EntityRef>>(`/search?${query}`, signal),
  places: (query: string, signal?: AbortSignal) => request<PlacePage>(`/map/places?${query}`, signal),
  entity: (kind: EntityKind, id: string, query = "", signal?: AbortSignal) => request<EntityDetail>(`/entities/${kind}/${encodeURIComponent(id)}?${query}`, signal),
  graph: (kind: EntityKind, id: string, query = "", signal?: AbortSignal) => request<GraphPage>(`/graph/${kind}/${encodeURIComponent(id)}?${query}`, signal),
};
