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
};

export type TimeConfiguration = {
  version: string;
  kind: "demo_windows";
  max_ma: number;
  windows: { label: string; older_ma: number; younger_ma: number }[];
};
