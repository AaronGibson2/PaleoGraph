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
  assert.ok(!style.layers.some((layer: {type: string}) => ["hillshade", "raster"].includes(layer.type)));
  for (const layer of style.layers.filter((layer: {type: string}) => layer.type === "fill-extrusion")) {
    assert.equal(layer.source, "atlas");
    assert.equal(layer["source-layer"], "building");
    assert.equal(layer.id, "atlas-building-forms");
  }
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

test("optional building forms respect provider heights and hide_3d outlines", () => {
  const layer = style.layers.find((layer: {id: string}) => layer.id === "atlas-building-forms");
  assert.equal(layer["source-layer"], "building");
  assert.equal(layer.source, "atlas");
  assert.equal(layer.type, "fill-extrusion");
  assert.equal(layer.layout.visibility, "none");
  assert.ok(layer.minzoom >= 14);
  const filter = spec.featureFilter(layer.filter, "layers[0].filter");
  const accepts = (properties: Record<string, unknown>) => filter.filter({zoom: 16}, {type: 3, properties});
  assert.equal(accepts({render_height: 30}), true);
  assert.equal(accepts({render_height: 30, hide_3d: true}), false);
  assert.equal(accepts({render_height: 0}), false);
  assert.equal(accepts({}), false);
  const height = spec.expression.createPropertyExpression(layer.paint["fill-extrusion-height"], "layers[0].paint.fill-extrusion-height", spec.latest["paint_fill-extrusion"]["fill-extrusion-height"]);
  assert.equal(height.result, "success");
  assert.equal(height.value.evaluate({zoom: 16}, {properties: {render_height: 30}}), 30);
  assert.equal(height.value.evaluate({zoom: 14}, {properties: {render_height: 30}}), 0);
});
