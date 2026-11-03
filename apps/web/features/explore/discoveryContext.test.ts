import assert from "node:assert/strict";
import { test } from "node:test";
import { catalogContext, catalogScope } from "./discoveryContext.ts";
import { parseExploreState, serializeExploreState } from "./state.ts";

const viewport = { west: -84, south: 25, east: -80, north: 30 };
const id = "de000000-0000-4000-8000-000600000001";

test("catalog search, guide, presentation and scope survive a shareable URL", () => {
  const state = parseExploreState(new URLSearchParams("catalog=open&catalog_q=Canis%20%26%20UF&catalog_scope=archive&catalog_view=records&discover=open&discovery_q=Aves"));
  assert.deepEqual(parseExploreState(new URLSearchParams(serializeExploreState(state))), state);
  assert.equal(state.catalog_q, "Canis & UF");
  assert.equal(state.discovery_q, "Aves");
  const invalid = parseExploreState(new URLSearchParams("catalog_scope=world&catalog_view=bad&discover=yes"));
  assert.equal(invalid.catalog_scope, undefined);
  assert.equal(invalid.catalog_view, undefined);
  assert.equal(invalid.discover, undefined);
  assert.equal(parseExploreState(new URLSearchParams(`catalog_q=${"x".repeat(200)}`)).catalog_q?.length, 160);
});

test("archive discovery removes only the viewport and retains explicit source, place and time", () => {
  const state = parseExploreState(new URLSearchParams(`source=all&taxon_id=${id}&at_lon=-82&at_lat=28&older_ma=3&younger_ma=0&catalog_q=Canis&catalog_scope=archive`));
  const params = new URLSearchParams(catalogContext(state, viewport));
  assert.equal(params.get("west"), null);
  assert.equal(params.get("source"), "all");
  assert.equal(params.get("taxon_id"), id);
  assert.equal(params.get("at_lon"), "-82");
  assert.equal(params.get("older_ma"), "3");
  assert.equal(params.get("younger_ma"), "0");
  assert.equal(params.get("q"), "Canis");
  assert.equal(catalogScope(state, true), "archive");
});

test("map area is bounded, PBDB remains nonspatial, and global search never filters catalog", () => {
  const state = parseExploreState(new URLSearchParams("q=global-only"));
  const params = new URLSearchParams(catalogContext(state, viewport));
  for (const [key, value] of Object.entries(viewport)) assert.equal(params.get(key), String(value));
  assert.equal(params.get("q"), null);
  assert.equal(catalogScope(state, true), "map");
  assert.equal(catalogScope(state, false), "archive");
  assert.equal(new URLSearchParams(catalogContext({ ...state, source: "pbdb" }, viewport)).get("west"), null);
  assert.equal(catalogScope({ ...state, source: "pbdb" }, true), "archive");
});

test("Catalog preserves the effective all-source scope of an implicit Lineage context", () => {
  const state = parseExploreState(new URLSearchParams("surface=lineage&discover=open"));
  assert.equal(new URLSearchParams(catalogContext(state)).get("source"), "all");
  assert.equal(new URLSearchParams(catalogContext({ ...state, source: "pbdb" })).get("source"), "pbdb");
});
