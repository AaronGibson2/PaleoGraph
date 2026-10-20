import { request } from "./client.ts";

export type PbdbHierarchy = {
  orig_no?: string; taxon_no?: string; taxon_name?: string; taxon_rank?: string;
  parent_no?: string; parent_name?: string; immpar_no?: string; immpar_name?: string;
  accepted_no?: string; accepted_name?: string; accepted_rank?: string; difference?: string;
  reference_no?: string; identified_no?: string | null; occurrence_accepted_no?: string | null;
  snapshot_hash?: string; partial_reason?: string | null; relationship?: string; routing?: string; identity_resolution?: string;
  proof?: { object?: string; row_hash?: string; source_record_id?: string; content_hash?: string };
  classification_opinions?: { opinion_no?: string; status?: string; parent_no?: string; reference_no?: string; primary_reference?: string; basis?: string }[];
};

export type TaxonomyCounts = {
  evidence_count: number; direct_count: number; ufvp_material_count: number;
  pbdb_occurrence_count: number; child_count: number; known_age_count: number;
  unknown_age_count: number; older_ma: number | null; younger_ma: number | null;
  derived_count: number; source_numeric_count: number;
  derived_older_ma: number | null; derived_younger_ma: number | null;
  source_older_ma: number | null; source_younger_ma: number | null;
};
export type TaxonomyNode = {
  id: string; parent_id: string | null; name: string; rank: string | null;
  placement: string; identity_hint?: string | null; sources: ("ufvp" | "pbdb")[];
  path: { id: string; name: string; rank: string | null }[]; counts: TaxonomyCounts;
  classification_path_ids: string[];
};
export type TaxonomyPage = { items: TaxonomyNode[]; total: number; next_offset: number | null; version: string; scope: "florida" };
export type TaxonomyDetail = {
  node: TaxonomyNode; ancestors: TaxonomyNode[]; concept_total: number; version: string;
  concepts: { source: "ufvp" | "pbdb"; concept_key: string; taxon_id: string | null; details: { name: string; rank: string | null; qualifiers: string[]; upper_path_placement: boolean; supplied_path: { name: string; rank: string | null }[]; classification_conflict: boolean; hierarchy?: PbdbHierarchy } }[];
  evidence: { id: string; occurrence_id: string; kind: "specimen" | "occurrence"; source: "ufvp" | "pbdb"; label: string; scientific_name: string; locality_id: string | null; locality_name: string | null; older_ma: number | null; younger_ma: number | null; age_basis: string }[];
};
export type SourceConcept = TaxonomyDetail["concepts"][number];
export type BranchChildrenPage = { items: { parent_id: string; page: TaxonomyPage }[]; next_offset: number | null; version: string };
export type ConceptPage = { items: SourceConcept[]; total: number; next_offset: number | null; version: string };
export const taxonomy = {
  branch: (id: string, query: string, signal: AbortSignal) => request<BranchChildrenPage>(`/taxonomy/nodes/${encodeURIComponent(id)}/branch-children?${query}`, signal),
  concepts: (id: string, query: string, signal: AbortSignal) => request<ConceptPage>(`/taxonomy/nodes/${encodeURIComponent(id)}/concepts?${query}`, signal),
  roots: (query: string, signal: AbortSignal) => request<TaxonomyPage>(`/taxonomy/roots?${query}`, signal),
  children: (id: string, query: string, signal: AbortSignal) => request<TaxonomyPage>(`/taxonomy/nodes/${encodeURIComponent(id)}/children?${query}`, signal),
  detail: (id: string, query: string, signal: AbortSignal) => request<TaxonomyDetail>(`/taxonomy/nodes/${encodeURIComponent(id)}?${query}`, signal),
  search: (query: string, signal: AbortSignal) => request<TaxonomyPage>(`/taxonomy/search?${query}`, signal),
};
