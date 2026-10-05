export type AgeRange = { older_ma: number | null; younger_ma: number | null };
export type Viewport = { west: number; south: number; east: number; north: number };

export type MapOccurrence = AgeRange & {
  id: string;
  scientific_name: string;
  locality_name: string;
  longitude: number;
  latitude: number;
  location_is_generalized: boolean;
  is_synthetic: boolean;
  catalog_label?: string | null;
  source_age_label?: string | null;
  record_count?: number;
  locality_count?: number;
  interpreted_count?: number;
};

export type MapResponse = {
  items: MapOccurrence[];
  returned: number;
  truncated: boolean;
  limit: number;
};

export type Evidence = {
  source_record_id: string;
  source_name: string;
  source_url: string | null;
  dataset_id: string;
  dataset_title: string;
  dataset_url: string | null;
  publisher: string | null;
  citation: string | null;
  license: string | null;
  rights_holder: string | null;
  dataset_version: string | null;
  ingestion_run_id: string;
  ingested_at: string;
  is_current: boolean;
  is_synthetic: boolean;
  information_withheld: string | null;
  data_generalizations: string | null;
};

export type OccurrenceDetail = AgeRange & {
  id: string;
  taxon_id: string;
  scientific_name: string;
  rank: string | null;
  collection_event_id: string;
  collection_event_name: string;
  context: string | null;
  stratigraphy: string | null;
  early_interval_name: string | null;
  late_interval_name: string | null;
  locality_id: string | null;
  locality_name: string | null;
  latitude: number | null;
  longitude: number | null;
  coordinate_uncertainty_m: number | null;
  location_is_generalized: boolean;
  location_is_withheld: boolean;
  notes: string | null;
  evidence: Evidence[];
  specimen?: {
    id: string; institution: string | null; institution_code: string | null;
    collection_code: string | null; catalog_number: string | null;
    occurrence_identifier: string | null; material_entity_identifier: string | null;
    other_identifiers: Record<string, unknown> | null; preparations: string | null;
    individual_count: string | null;
  } | null;
  source_values?: Record<string, string>;
};

export type DatasetStatus = {
  title: string; dataset_url: string; license: string | null; version: string | null;
  current_records: number; mapped_records: number; numeric_age_records: number;
  latest_scope: string | null; latest_status: string | null;
  creator: string | null;
  browse_revision?: string | null;
};

export type TimeConfiguration = {
  version: string;
  kind: "international_chronostratigraphic_chart";
  max_ma: number;
  attribution: string;
  source_url: string;
  license_url: string;
  units: GeologicalInterval[];
};

export type GeologicalInterval = {
  id: string; name: string; rank: string; parent: string | null;
  older_ma: number; younger_ma: number; color: string;
  formal_status?: string; ratified_gssp?: boolean | null;
  older_boundary?: { source_decimal: string; margin_of_error_ma: number | null; note: string | null };
  younger_boundary?: { source_decimal: string; margin_of_error_ma: number | null; note: string | null };
};
