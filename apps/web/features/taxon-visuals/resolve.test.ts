import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { resolveTaxonVisual } from "./resolve.ts";
import { archetypeAssets } from "./assets.ts";
import { generalGlyphs, unassignedGlyph } from "./glyphs.ts";

// Fixed reviewed source UUID paths, independently recorded from the Florida snapshot.
const cases: { label: string; path: string[]; kind: string; archetype?: string; visual?: string }[] = JSON.parse(readFileSync(new URL("./reviewed-cases.json", import.meta.url), "utf8"));
for (const { label, path, ...expected } of cases) {
  test(`${label}: reviewed source membership resolves safely`, () => {
    assert.deepEqual(resolveTaxonVisual({ classification_path_ids: path }), expected);
    assert.deepEqual(resolveTaxonVisual({ classification_path_ids: Object.freeze([...path]) }), expected);
  });
}
test("missing paths and lookalike labels do not invent membership", () => {
  assert.deepEqual(resolveTaxonVisual({}), { kind: "neutral" });
  assert.deepEqual(resolveTaxonVisual({ id: "Rodentia" }), { kind: "neutral" });
  assert.deepEqual(resolveTaxonVisual({ id: "unknown", classification_path_ids: [] }), { kind: "neutral" });
});
test("identification-only snake rules do not become inherited roots", () => {
  assert.deepEqual(resolveTaxonVisual({ classification_path_ids: ["unknown", "e6eca45b-f3ce-464c-8343-db258136619c", "421cb554-9eb9-4f0a-8add-217d50a2f072"] }), { kind: "generic", visual: "reptile" });
});
test("fourteen raster masks and forty-four vector archetypes stay small and local", () => {
  assert.equal(Object.keys(archetypeAssets).length, 58);
  for (const asset of Object.values(archetypeAssets).filter(asset => asset.src.endsWith(".png"))) {
    const bytes = readFileSync(new URL(`../../public${asset.src}`, import.meta.url));
    assert.equal(bytes.subarray(1, 4).toString(), "PNG");
    assert.equal(bytes.readUInt32BE(16), 256);
    assert.equal(bytes.readUInt32BE(20), 256);
    assert.equal(bytes[25], 6); // RGBA
    assert.ok(bytes.length < 15000);
  }
  for (const asset of Object.values(archetypeAssets).filter(asset => asset.src.endsWith(".svg"))) {
    const svg = readFileSync(new URL(`../../public${asset.src}`, import.meta.url), "utf8");
    assert.match(svg, /viewBox="0 0 128 96"/);
    assert.match(svg, /<path d="[^"]+"/);
    assert.doesNotMatch(svg, /<script|<image|href=|onload=/i);
    assert.ok(svg.length < 2000);
  }
});

test("nearest crocodilian membership wins over a broad neutral reptile ancestor", () => {
  assert.deepEqual(resolveTaxonVisual({ classification_path_ids: ["unknown", "7446b9c1-9e06-4143-85c1-3add186115b6", "5fa0ef36-ee22-4759-8e0f-cb487a7fe246"] }), { kind: "archetype", archetype: "crocodilian" });
});

test("explicit PBDB memberships support crocodilians, frogs and salamanders without labels", () => {
  for (const [id, archetype] of [["pbdb:txn:36582", "crocodilian"], ["pbdb:txn:97112", "frog"], ["pbdb:txn:37339", "salamander"]]) {
    assert.deepEqual(resolveTaxonVisual({ classification_path_ids: [id] }), { kind: "archetype", archetype });
  }
  assert.deepEqual(resolveTaxonVisual({ id: "Crocodylia" }), { kind: "neutral" });
});

for (const [label, ids, archetype] of [
  ["horses", ["pbdb:txn:42984", "8d289d8c-71af-47ac-8a53-30841b9796a2"], "horse"],
  ["cats", ["pbdb:txn:41045", "21d6fcd2-dd73-45f2-889e-f2311c10cec1"], "cat"],
  ["owls", ["pbdb:txn:39403", "7fcda90a-9334-4791-806e-de4dbd4f459f"], "owl"],
  ["waterfowl", ["pbdb:txn:39624", "4a0a85e8-26e7-4635-812c-db627b8cee28"], "waterfowl"],
  ["catfish", ["pbdb:txn:110631", "f4b5d55b-8863-4eea-8add-f6c7ebef0e1d"], "catfish"],
  ["sea turtles", ["pbdb:txn:37695", "054f7cde-c8db-4031-8b8a-02050cdf113b"], "sea-turtle"],
] as const) {
  test(`${label} inherit a specific form through retained provider and source UUID paths`, () => {
    for (const id of ids) assert.deepEqual(resolveTaxonVisual({ classification_path_ids: ["unmapped-descendant", id] }), { kind: "archetype", archetype });
  });
}

test("specific forms win before broad-group symbols, and broad symbols do not invent a species", () => {
  assert.deepEqual(resolveTaxonVisual({ classification_path_ids: ["unknown", "pbdb:txn:34422"] }), { kind: "generic", visual: "cartilaginous-fish" });
  assert.deepEqual(resolveTaxonVisual({ classification_path_ids: ["unknown", "pbdb:txn:97112", "pbdb:txn:36319"] }), { kind: "archetype", archetype: "frog" });
  assert.deepEqual(resolveTaxonVisual({ classification_path_ids: ["unknown", "pbdb:txn:36319"] }), { kind: "generic", visual: "amphibian" });
  assert.deepEqual(resolveTaxonVisual({ classification_path_ids: ["unknown", "pbdb:txn:16005", "pbdb:txn:7805"] }), { kind: "archetype", archetype: "bivalve" });
  assert.deepEqual(resolveTaxonVisual({ id: "Equidae" }), { kind: "neutral" });
});

test("every broad group and unassigned context has a local, nonempty vector glyph", () => {
  assert.equal(Object.keys(generalGlyphs).length, 10);
  for (const path of [...Object.values(generalGlyphs), unassignedGlyph]) {
    assert.match(path, /^M/);
    assert.ok(path.length > 30 && path.length < 2000);
  }
});
