import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { occurrenceFeature } from "../map/layers.ts";

const style = JSON.parse(readFileSync(new URL("../../public/styles/paleograph.json", import.meta.url), "utf8"));
const spec = createRequire(import.meta.resolve("maplibre-gl"))("@maplibre/maplibre-gl-style-spec");

test("the owned Atlas style satisfies the locked MapLibre style specification", () => {
  assert.deepEqual(spec.validateStyleMin(style), []);
  assert.match(style.name, /PaleoGraph/);
});
test("cartography retains the free vector provider and all attribution links", () => {
  assert.equal(style.sources.atlas.url, "https://tiles.openfreemap.org/planet");
  for (const domain of ["openfreemap.org", "openmaptiles.org", "openstreetmap.org/copyright"]) assert.ok(style.sources.atlas.attribution.includes(domain));
  assert.equal(Object.keys(style.sources).length, 1);
  assert.equal(style.sources.atlas.type, "vector");
});
test("physical context uses real schema layers and does not fabricate relief", () => {
  const layers = new Set(style.layers.map((layer: {"source-layer"?: string}) => layer["source-layer"]));
  for (const layer of ["landcover", "water", "waterway", "landuse", "park", "boundary"]) assert.ok(layers.has(layer));
  assert.ok(!style.terrain && !style.sprite);
  assert.ok(!style.layers.some((layer: {type: string}) => ["hillshade", "raster", "fill-extrusion"].includes(layer.type)));
});
test("geographic detail and labels have distinct zoom-dependent hierarchy", () => {
  const layer = (id: string) => style.layers.find((value: {id: string}) => value.id === id);
  assert.ok(layer("atlas-local-roads").minzoom > layer("atlas-major-roads").minzoom);
  assert.ok(layer("atlas-town-names").minzoom > layer("atlas-city-names").minzoom);
  assert.ok(layer("atlas-natural-names").minzoom > layer("atlas-state-names").minzoom);
  assert.notEqual(layer("atlas-water").paint["fill-color"], layer("atlas-mineral").paint["background-color"]);
});
test("label fonts stay within verified provider glyph stacks", () => {
  for (const layer of style.layers) for (const font of layer.layout?.["text-font"] ?? []) assert.ok(["Noto Sans Regular", "Noto Sans Italic"].includes(font));
});
test("mapped notation preserves exact positions and evidence counts at a shared position", () => {
  const item = { id:"position", scientific_name:"73 evidence records", locality_name:"2 source place contexts", longitude:-82.19,latitude:29.36,record_count:73,locality_count:2,interpreted_count:60,older_ma:null,younger_ma:null,location_is_generalized:true,is_synthetic:false };
  const feature = occurrenceFeature(item,2);
  assert.deepEqual(feature.geometry,{type:"Point",coordinates:[-82.19,29.36]});
  assert.equal(feature.properties?.record_count,73);
  assert.equal(feature.properties?.locality_count,2);
  assert.equal(feature.properties?.unknown,false);
  assert.equal(feature.properties?.generalized,true);
});
