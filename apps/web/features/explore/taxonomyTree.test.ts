import test from "node:test";
import assert from "node:assert/strict";
import { adjacentRow, flattenTree, taxonomyContext, treeWindow, treeIndent } from "./taxonomyTree.ts";
import { parseExploreState, serializeExploreState } from "./state.ts";
import type { TaxonomyNode } from "../../lib/api/taxonomy.ts";

function node(id: string, parent_id: string | null = null): TaxonomyNode {
  return { id, parent_id, name: id, rank: "genus", placement: "supported", path: [], sources: ["ufvp"], classification_path_ids: [], counts: { evidence_count: 3, direct_count: 1, ufvp_material_count: 3, pbdb_occurrence_count: 0, child_count: 1, known_age_count: 1, unknown_age_count: 2, older_ma: 2, younger_ma: 1, derived_count: 1, source_numeric_count: 0, derived_older_ma: 2, derived_younger_ma: 1, source_older_ma: null, source_younger_ma: null } };
}
const roots = [node("Animalia"), node("Partial")];
const branches = { Animalia: { page: { items: [node("Chordata", "Animalia")], total: 1, next_offset: null, version: "v1", scope: "florida" as const } }, Chordata: { page: { items: [node("Mammalia", "Chordata")], total: 1, next_offset: null, version: "v1", scope: "florida" as const } } };

test("initial tree does not include any unloaded or collapsed descendants", () => {
  assert.deepEqual(flattenTree(roots, branches, new Set()).map(row => row.node.id), ["Animalia", "Partial"]);
});
test("one lazy level expands without loading the entire hierarchy", () => {
  assert.deepEqual(flattenTree(roots, branches, new Set(["Animalia"])).map(row => row.node.id), ["Animalia", "Chordata", "Partial"]);
});
test("restored ancestor path expands with correct accessibility levels", () => {
  assert.deepEqual(flattenTree(roots, branches, new Set(["Animalia", "Chordata"])).map(row => [row.node.id, row.level]), [["Animalia", 1], ["Chordata", 2], ["Mammalia", 3], ["Partial", 1]]);
});
test("collapse retains cached branch data without rendering it", () => {
  assert.equal(flattenTree(roots, branches, new Set()).length, 2);
  assert.equal(branches.Animalia.page.items.length, 1);
});
test("tree flattener refuses accidental cycles and duplicate node rendering", () => {
  const cyclic = { Animalia: { page: { ...branches.Animalia.page, items: [roots[0]] } } };
  assert.equal(flattenTree(roots, cyclic, new Set(["Animalia"])).length, 2);
});
test("keyboard movement remains bounded and supports Home and End", () => {
  const rows = flattenTree(roots, branches, new Set(["Animalia"]));
  assert.equal(adjacentRow(rows, "Animalia", "ArrowUp"), "Animalia");
  assert.equal(adjacentRow(rows, "Animalia", "ArrowDown"), "Chordata");
  assert.equal(adjacentRow(rows, "Chordata", "End"), "Partial");
  assert.equal(adjacentRow(rows, "Partial", "Home"), "Animalia");
});
test("large visible branches are windowed to a bounded DOM budget", () => {
  const window = treeWindow(5000, 5800);
  assert.equal(window.start, 92);
  assert.ok(window.end - window.start <= 26);
  assert.ok(window.after > 0);
});
test("deep provider genus and species retain distinct visible indentation", () => {
  assert.equal(treeIndent(48, 48) - treeIndent(47, 48), 19);
  assert.equal(treeIndent(1, 48), 8);
  assert.ok(treeIndent(48, 48) <= 198);
  assert.equal(treeIndent(3, 4) - treeIndent(2, 4), 19);
});
test("source cache keys remain distinct while catalog search and cursors are removed", () => {
  assert.equal(new URLSearchParams(taxonomyContext("q=Canis&cursor=old")).get("source"), "all");
  assert.notEqual(taxonomyContext("source=ufvp"), taxonomyContext("source=pbdb"));
  assert.equal(new URLSearchParams(taxonomyContext("older_ma=2&younger_ma=0")).get("older_ma"), "2");
});
test("focused node URL restores without serializing manual expansion lists", () => {
  const id = "098a01be-7418-41c1-8d46-ff3436e419d4";
  const state = parseExploreState(new URLSearchParams(`surface=lineage&source=all&taxonomy_focus=${id}`));
  assert.equal(parseExploreState(new URLSearchParams(serializeExploreState(state))).taxonomy_focus, id);
  assert.equal(state.source, "all");
  assert.ok(!serializeExploreState(state).includes("expanded"));
});
