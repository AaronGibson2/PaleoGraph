import assert from "node:assert/strict";
import { test } from "node:test";
import type { EntityDetail, PublishedOccurrence } from "../../lib/api/discovery.ts";
import type { OccurrenceDetail } from "../../lib/api/types.ts";
import { meaningfulPreparation, recordNavigationPatch, recordOverview } from "./recordOverview.ts";

function detail(): EntityDetail {
  return { entity: { kind: "specimen", id: "material-a", label: "UF / 1", subtitle: "Source identification", source: "ufvp" }, material_count: 1, mapped_count: 1, related: [], related_has_more: false, research_note: "", properties: { occurrence_id: "assertion-a", status: "mapped", source_label: "Pleistocene", older_ma: "2.58", younger_ma: "0.0117" } };
}
function occurrence(): OccurrenceDetail {
  return { id: "assertion-a", taxon_id: "source-taxon-a", scientific_name: "Source identification", rank: "species", collection_event_id: "event-a", collection_event_name: "Event", context: null, stratigraphy: null, early_interval_name: null, late_interval_name: null, locality_id: "locality-a", locality_name: "Source locality", latitude: 28, longitude: -82, coordinate_uncertainty_m: 100, location_is_generalized: false, location_is_withheld: false, notes: null, older_ma: null, younger_ma: null, evidence: [], specimen: { id: "material-a", institution: "Museum", institution_code: "UF", collection_code: "UF", catalog_number: "1", occurrence_identifier: "source-id", material_entity_identifier: null, other_identifiers: {}, preparations: null, individual_count: null } };
}

test("overview prioritizes complete source numeric bounds and retains present-day zero", () => {
  const record = recordOverview(detail(), { ...occurrence(), older_ma: 3, younger_ma: 0 });
  assert.deepEqual(record?.age, { older_ma: 3, younger_ma: 0 });
  assert.equal(record?.ageBasis, "Source numeric bounds");
  assert.equal(record?.taxon?.id, "source-taxon-a");
  assert.equal(record?.locality?.id, "locality-a");
});

test("partial source bounds use only a supported interpreted envelope and preserve unresolved wording", () => {
  const partial = recordOverview(detail(), { ...occurrence(), older_ma: 3 });
  assert.deepEqual(partial?.age, { older_ma: 2.58, younger_ma: 0.0117 });
  assert.equal(partial?.ageBasis, "Interpreted reference envelope");
  const unresolved = detail();
  unresolved.properties = { occurrence_id: "assertion-a", status: "unmapped", source_label: "Miocene(?)", older_ma: "", younger_ma: null };
  const record = recordOverview(unresolved, occurrence());
  assert.deepEqual(record?.age, { older_ma: null, younger_ma: null });
  assert.equal(record?.ageLabel, "Miocene(?)");
  assert.equal(record?.ageBasis, "Numeric age unresolved");
});

test("a cached assertion for another specimen cannot populate the current record", () => {
  const data = detail();
  data.related = [{ kind: "taxon", id: "taxon-a", label: "Same name", subtitle: null }, { kind: "taxon", id: "taxon-b", label: "Same name", subtitle: null }];
  const record = recordOverview(data, { ...occurrence(), id: "assertion-b", older_ma: 200, younger_ma: 100 });
  assert.equal(record?.taxon, null);
  assert.equal(record?.locality, null);
  assert.equal(record?.age.older_ma, 2.58);
});

test("published overview keeps provider calibration and explicit collection identity", () => {
  const published: PublishedOccurrence = { external_id: "1", original_identification: {}, latest_identification: {}, modern_position: { longitude: "-82", latitude: "28", status: "datum-unverified", basis: null, precision: null }, provider_age: { older_ma: 5, younger_ma: 0, policy: "provider", early_interval: "Source interval", late_interval: "Source interval", determined_dates: {} }, material_evidence_count: 0, materials: [], materials_has_more: false, content_hash: "hash", normalization_hash: "normalization", license: "CC0" };
  const data: EntityDetail = { ...detail(), entity: { kind: "occurrence", id: "published-a", label: "PBDB occurrence 1", subtitle: "Entered name", source: "pbdb" }, properties: {}, occurrence: published, related: [{ kind: "locality", id: "collection-a", label: "Collection", subtitle: null }, { kind: "taxon", id: "pbdb-taxon", label: "Entered name", subtitle: null }] };
  const record = recordOverview(data);
  assert.equal(record?.source, "pbdb");
  assert.equal(record?.ageBasis, "PBDB provider envelope");
  assert.equal(record?.ageLabel, "Source interval");
  assert.equal(record?.locality?.id, "collection-a");
  assert.equal(record?.taxon?.id, "pbdb-taxon");
});

test("record actions preserve effective source, navigate exact IDs, and remove only superseded place scope", () => {
  const target = { kind: "taxon" as const, id: "source-taxon", label: "Same name", subtitle: null, source: "ufvp" as const };
  const classification = recordNavigationPatch({}, { intent: "classification", target });
  assert.equal(classification.source, "ufvp");
  assert.equal(classification.lineage_focus, target.id);
  assert.equal(classification.taxonomy_focus, null);
  const material = recordNavigationPatch({ surface: "lineage" }, { intent: "material", target });
  assert.equal(material.source, "all");
  assert.equal(material.catalog_scope, "archive");
  assert.equal(material.locality_id, null);
  assert.equal(material.at_lon, null);
  assert.equal(material.taxon_id, target.id);
  assert.equal("older_ma" in material, false);
  const published = recordNavigationPatch({}, { intent: "material", target: { ...target, source: "pbdb" } });
  assert.equal(published.source, "pbdb");
});

test("missing and provider-default preparations stay out of the everyday summary", () => {
  for (const value of [null, "", "  ", "default - 1", "None - 1", "Unknown", "Not supplied"]) assert.equal(meaningfulPreparation(value), false);
  for (const value of ["Skull - 1", "Cast", "Complete skeleton"]) assert.equal(meaningfulPreparation(value), true);
});
