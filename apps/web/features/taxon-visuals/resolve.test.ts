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
test("all fourteen static derivatives are small transparent square PNGs", () => {
  assert.equal(Object.keys(archetypeAssets).length, 14);
  for (const asset of Object.values(archetypeAssets)) {
    const bytes = readFileSync(new URL(`../../public${asset.src}`, import.meta.url));
    assert.equal(bytes.subarray(1, 4).toString(), "PNG");
    assert.equal(bytes.readUInt32BE(16), 256);
    assert.equal(bytes.readUInt32BE(20), 256);
    assert.equal(bytes[25], 6); // RGBA
    assert.ok(bytes.length < 15000);
  }
});
