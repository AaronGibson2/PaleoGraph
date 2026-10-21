import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { resolveTaxonVisual } from "./resolve.ts";
import { archetypeAssets } from "./assets.ts";

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
  assert.deepEqual(resolveTaxonVisual({ classification_path_ids: ["unknown", "e6eca45b-f3ce-464c-8343-db258136619c", "421cb554-9eb9-4f0a-8add-217d50a2f072"] }), { kind: "neutral" });
});
test("fourteen raster masks and thirteen vector archetypes stay small and local", () => {
  assert.equal(Object.keys(archetypeAssets).length, 27);
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
