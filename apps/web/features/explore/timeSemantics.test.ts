import test from "node:test";
import assert from "node:assert/strict";
import { ageLabel } from "./state.ts";
import { occurrenceFeature } from "../map/layers.ts";
import type { MapOccurrence } from "../../lib/api/types.ts";

test("time display keeps calibrated reference endpoints as a range, never a midpoint", () => {
  assert.equal(ageLabel({ older_ma: 11.63, younger_ma: 5.333 }), "11.63–5.333 Ma");
  assert.equal(ageLabel({ older_ma: 0.129, younger_ma: 0.0117 }), "0.129–0.0117 Ma");
  assert.equal(ageLabel({ older_ma: 56, younger_ma: 33.9 }), "56–33.9 Ma");
  assert.equal(ageLabel({ older_ma: 0, younger_ma: 0 }), "0–0 Ma");
});

test("a missing or partial envelope is explicit and never turns null into present", () => {
  assert.equal(ageLabel({ older_ma: null, younger_ma: null }), "No numeric envelope");
  assert.equal(ageLabel({ older_ma: 10, younger_ma: null }), "Partial numeric bounds");
  assert.equal(ageLabel({ older_ma: null, younger_ma: 0 }), "Partial numeric bounds");
});

test("a very small nonzero bound cannot be rounded into present", () => {
  assert.equal(ageLabel({ older_ma: 0.0000082, younger_ma: 0 }), "8.2e-6–0 Ma");
});

test("Atlas notation distinguishes numeric coverage, unknown ages, and mixed stacks", () => {
  const item: MapOccurrence = { id: "fixture", scientific_name: "Fixture", locality_name: "Fixture",
    longitude: -82, latitude: 29, location_is_generalized: false, is_synthetic: false,
    older_ma: null, younger_ma: null };
  assert.equal(occurrenceFeature(item, 1).properties?.glyph, "atlas-unknown");
  assert.equal(occurrenceFeature({ ...item, older_ma: 10 }, 1).properties?.unknown, true);
  assert.equal(occurrenceFeature({ ...item, older_ma: 0, younger_ma: 0 }, 1).properties?.glyph, "atlas-record");
  const mixed = occurrenceFeature({ ...item, record_count: 10, interpreted_count: 4 }, 1);
  assert.equal(mixed.properties?.glyph, "atlas-stack");
  assert.equal(mixed.properties?.unknown, false); // Some complete envelopes, not all ten.
  assert.equal(mixed.properties?.record_count, 10); // Unresolved assertions are retained.
});
