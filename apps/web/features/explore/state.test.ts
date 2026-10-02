import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_VIEW, normalizeViewport, parseExploreState, serializeExploreState } from "./state.ts";
import { occurrenceQuery } from "../../lib/api/client.ts";

test("shareable state round-trips including selection and age zero", () => {
  const state = { ...DEFAULT_VIEW, data_mode: "museum" as const, selected: "de000000-0000-4000-8000-000600000001", older_ma: 2, younger_ma: 0 };
  assert.deepEqual(parseExploreState(new URLSearchParams(serializeExploreState(state))), state);
});

test("invalid URL bounds never turn unknown ages into present", () => {
  for (const query of ["older_ma=3", "older_ma=1&younger_ma=3", "older_ma=NaN&younger_ma=0", "older_ma=&younger_ma="]) {
    const result = parseExploreState(new URLSearchParams(query));
    assert.equal(result.older_ma, null);
    assert.equal(result.younger_ma, null);
  }
  const result = parseExploreState(new URLSearchParams("lat=999&lng=no&zoom=-1&selected=script"));
  assert.equal(result.lat, DEFAULT_VIEW.lat);
  assert.equal(result.selected, null);
});

test("serialization removes stale filters but preserves unrelated URL state", () => {
  const result = serializeExploreState({ ...DEFAULT_VIEW, older_ma: null, younger_ma: null, selected: null }, new URLSearchParams("older_ma=2&younger_ma=0&selected=old&note=keep"));
  const params = new URLSearchParams(result);
  assert.equal(params.get("note"), "keep");
  assert.equal(params.has("older_ma"), false);
  assert.equal(params.has("selected"), false);
});

test("map bounds support antimeridian and full world views", () => {
  assert.deepEqual(normalizeViewport(170, -10, 190, 10), { west: 170, east: -170, south: -10, north: 10 });
  assert.deepEqual(normalizeViewport(-200, -95, 200, 95), { west: -180, east: 180, south: -90, north: 90 });
});

test("API query sends bounds unchanged and omits inactive age filters", () => {
  const viewport = { west: 170, east: -170, south: -10, north: 10 };
  const all = new URLSearchParams(occurrenceQuery(viewport, { older_ma: null, younger_ma: null }));
  assert.equal(all.get("east"), "-170");
  assert.equal(all.has("older_ma"), false);
  const bounded = new URLSearchParams(occurrenceQuery(viewport, { older_ma: 2, younger_ma: 0 }));
  assert.equal(bounded.get("younger_ma"), "0");
});
