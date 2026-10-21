import { expect, test } from "@playwright/test";
import type { TaxonomyNode } from "../../lib/api/taxonomy";
import { apiBase, stubBasemap } from "./helpers";

test.skip(process.env.PALEOGRAPH_REAL_FLORIDA !== "1", "Requires retained Florida evidence");
test.beforeEach(async ({ page }) => stubBasemap(page));

test("ordinary Animalia search selects the shared kingdom before unresolved same-name assertions", async ({ page, request }) => {
  const found = await (await request.get(`${apiBase}/taxonomy/search?source=all&q=Animalia`)).json();
  const node: TaxonomyNode = found.items[0];
  expect(node.name).toBe("Animalia");
  expect(node.rank).toBe("kingdom");
  expect(node.sources).toEqual(["ufvp", "pbdb"]);
  await page.goto("/lineage?source=all");
  await page.getByRole("combobox", { name: "Find a taxonomic group" }).fill("Animalia");
  await page.locator("#taxonomy-matches [role=option]").first().click();
  expect(new URL(page.url()).searchParams.get("taxonomy_focus")).toBe(node.id);
  await expect(page.locator(".taxonomy-focus .eyebrow").first()).toContainText("kingdom");
});

for (const [name, archetype] of [["Crocodylia", "crocodilian"], ["Testudines", "turtle"], ["Anura", "frog"], ["Canis", "carnivoran"], ["Alligator mississippiensis", "crocodilian"], ["Phalacrocorax", "bird"], ["Centrarchidae", "bony-fish"]]) {
  test(`${name} has one shared search destination, recognizable visual and reversible source paths`, async ({ page, request }) => {
    const found = await (await request.get(`${apiBase}/taxonomy/search?source=all&q=${encodeURIComponent(name)}`)).json();
    const exact: TaxonomyNode[] = found.items.filter((node: TaxonomyNode) => node.name === name);
    expect(exact).toHaveLength(1);
    const node = exact[0];
    expect(node.sources).toEqual(["ufvp", "pbdb"]);
    expect(node.counts.evidence_count).toBe(node.counts.ufvp_material_count + node.counts.pbdb_occurrence_count);
    expect(node.counts.ufvp_material_count).toBeGreaterThan(0);
    expect(node.counts.pbdb_occurrence_count).toBeGreaterThan(0);
    const detail = await (await request.get(`${apiBase}/taxonomy/nodes/${node.id}`)).json();
    expect(detail.concepts.some((c: { source: string }) => c.source === "pbdb")).toBe(true);
    expect(detail.concepts.some((c: { source: string }) => c.source === "ufvp")).toBe(true);
    await page.goto("/lineage?source=all");
    await page.getByRole("combobox", { name: "Find a taxonomic group" }).fill(name);
    await page.locator("#taxonomy-matches [role=option]").filter({ hasText: name }).first().click();
    await expect(page.locator(".taxonomy-focus h3")).toHaveText(name);
    await expect(page.locator(`#taxonomy-row-${node.id} .taxon-visual`)).toHaveAttribute("data-archetype", archetype);
    await expect(page.locator(".taxonomy-unified-note")).toBeVisible();
    await page.getByRole("combobox", { name: "Evidence source", exact: true }).selectOption("pbdb");
    await expect(page.locator(".taxonomy-evidence-counts")).toContainText(node.counts.pbdb_occurrence_count.toLocaleString("en-US"));
    expect(new URL(page.url()).searchParams.get("taxonomy_focus")).toBe(node.id);
    await page.reload();
    await expect(page.locator(".taxonomy-focus h3")).toHaveText(name);
  });
}
