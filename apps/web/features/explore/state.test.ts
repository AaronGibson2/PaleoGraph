import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_VIEW, normalizeViewport, parseExploreState, serializeExploreState, lineageContext } from "./state.ts";
import { occurrenceQuery } from "../../lib/api/client.ts";

test("locality and lineage surfaces restore stable classification focus", () => {
  const id = "de000000-0000-4000-8000-000600000001";
  for (const surface of ["localities", "lineage"] as const) {
    const state = parseExploreState(new URLSearchParams(`surface=${surface}&lineage_focus=${id}&locality_id=${id}`));
    assert.equal(state.surface, surface);
    assert.equal(state.lineage_focus, id);
    assert.equal(parseExploreState(new URLSearchParams(serializeExploreState(state))).lineage_focus, id);
  }
  assert.equal(parseExploreState(new URLSearchParams("surface=lineage&lineage_focus=invalid")).lineage_focus, undefined);
});

test("lineage actions narrow ancestors and retain an active descendant context", () => {
  assert.equal(lineageContext(null, "genus", [{ id: "class" }, { id: "genus" }]), "genus");
  assert.equal(lineageContext("class", "genus", [{ id: "class" }, { id: "genus" }]), "genus");
  assert.equal(lineageContext("species", "genus", [{ id: "class" }, { id: "genus" }]), "species");
  assert.equal(lineageContext("species", null, []), "species");
});

test("material and inspector presentation restore with URL context and reject invalid flags",()=>{
  const selected="de000000-0000-4000-8000-000600000001";
  const state=parseExploreState(new URLSearchParams(`selected=${selected}&catalog=open&inspect=closed`));
  const restored=parseExploreState(new URLSearchParams(serializeExploreState(state)));
  assert.equal(restored.catalog,'open');assert.equal(restored.inspect,'closed');assert.equal(restored.selected,selected);
  assert.equal(parseExploreState(new URLSearchParams('catalog=everything&inspect=open')).catalog,undefined);
  assert.equal(parseExploreState(new URLSearchParams('inspect=everything')).inspect,undefined);
});

test("shareable state round-trips including selection and age zero", () => {
  const state = { ...DEFAULT_VIEW, selected: "de000000-0000-4000-8000-000600000001", older_ma: 2, younger_ma: 0 };
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

test("scientific context and calibrated decimal bounds survive URL restoration", () => {
  const state = parseExploreState(new URLSearchParams("older_ma=11.63&younger_ma=5.333&interval_id=ics:2026-06:LateMiocene&time_focus=ics:2026-06:Miocene&surface=relationships&selected_kind=taxon&selected=de000000-0000-4000-8000-000600000001&taxon_id=de000000-0000-4000-8000-000600000001&at_lon=-82.19&at_lat=29.36&q=UF%2FTRO+1"));
  assert.deepEqual(parseExploreState(new URLSearchParams(serializeExploreState(state))), state);
  assert.equal(state.younger_ma, 5.333);
  assert.equal(state.surface, "relationships");
});

test("invalid exact-place coordinates and legacy public demo mode are removed", () => {
  const state = parseExploreState(new URLSearchParams("at_lon=999&at_lat=29.36&data_mode=demo"));
  const params = new URLSearchParams(serializeExploreState(state, new URLSearchParams("data_mode=demo")));
  assert.equal(params.has("at_lon"), false);
  assert.equal(params.has("at_lat"), false);
  assert.equal(params.has("data_mode"), false);
});
