import { expect, test } from "@playwright/test";
import { apiBase, stubBasemap } from "./helpers";
import type { TaxonomyNode } from "../../lib/api/taxonomy";

test.beforeEach(async ({ page }) => stubBasemap(page));

test("PBDB synonym details preserve names and separate classification references", async ({ page, request }) => {
  const found = await (await request.get(`${apiBase}/taxonomy/search?q=Velates%20floridanus&source=pbdb`)).json();
  const node = found.items.find((item: TaxonomyNode) => item.name === "Velates floridanus");
  expect(node).toBeTruthy();
  await page.route(`**/taxonomy/nodes/${node.id}?*`, async route => {
    const response = await route.fetch();
    const body = await response.json();
    for (const concept of body.concepts) if (concept.source === "pbdb") concept.details.hierarchy = {
      orig_no: "txn:155289", taxon_no: "var:155289", taxon_name: "Velates floridanus",
      taxon_rank: "species", accepted_no: "txn:114119", accepted_name: "Velates perversus",
      difference: "subjective synonym of", parent_no: "txn:9369", parent_name: "Velates",
      reference_no: "ref:124",
      classification_opinions: [{ opinion_no: "opn:1", status: "belongs to", parent_no: "txn:9369", reference_no: "ref:2" }],
      snapshot_hash: "a".repeat(64), proof: { row_hash: "b".repeat(64), object: "c".repeat(64) },
    };
    await route.fulfill({ response, json: body });
  });
  await page.goto(`/lineage?source=pbdb&taxonomy_focus=${node.id}`);
  await expect(page.locator(".taxonomy-source-hierarchy").first()).toContainText("Accepted: Velates perversus");
  await expect(page.locator(".taxonomy-source-hierarchy").first()).toContainText("subjective synonym of");
  await page.getByText("Classification evidence and archived revision", { exact: true }).first().click();
  await expect(page.locator(".taxonomy-source-hierarchy").first()).toContainText("Name authority reference: ref:124");
  await expect(page.locator(".taxonomy-source-hierarchy").first()).toContainText("Classification opinion opn:1: belongs to");
});

test("roots are bounded and expansion fetches one immediate branch", async ({ page }) => {
  const urls: string[] = [];
  page.on("request", request => { if (request.url().includes("/taxonomy/")) urls.push(request.url()); });
  await page.goto("/lineage");
  await expect(page.getByRole("tree")).toHaveAttribute("aria-busy", "false");
  expect(urls.filter(url => url.includes("/children"))).toHaveLength(0);
  await page.getByRole("button", { name: "Expand Animalia", exact: true }).click();
  const chordata = page.getByRole("treeitem").filter({ hasText: "Chordata" });
  await expect(chordata).toHaveAttribute("aria-level", "2");
  expect(urls.filter(url => url.includes("/children"))).toHaveLength(1);
  await page.getByRole("button", { name: "Expand Chordata", exact: true }).click();
  await expect(page.getByRole("treeitem").filter({ hasText: "Mammalia" })).toHaveAttribute("aria-level", "3");
  expect(urls.filter(url => url.includes("/children"))).toHaveLength(2);
  expect(urls.some(url => url.includes("/entities/"))).toBe(false);
});

test("search selects a genus, restores ancestors and supports reload and history", async ({ page }) => {
  await page.goto("/lineage");
  const search = page.getByRole("combobox", { name: "Find a taxonomic group" });
  await search.fill("Smilodon");
  const result = page.locator("#taxonomy-matches [role=option]").filter({ hasText: /genus/ }).first();
  await expect(result).toBeVisible();
  const focus = (await result.getAttribute("id"))!.replace("taxonomy-match-", "");
  await result.click();
  await expect(page.locator(".taxonomy-focus h3")).toHaveText("Smilodon");
  const row = page.locator(`#taxonomy-row-${focus}`);
  await expect(row).toBeFocused();
  await expect(row).toHaveAttribute("aria-selected", "true");
  expect(new URL(page.url()).searchParams.get("taxonomy_focus")).toBe(focus);
  await page.locator(".lineage-navigation button").filter({ hasText: /^Mammalia$/ }).click();
  await expect(page.locator(".taxonomy-focus h3")).toHaveText("Mammalia");
  await page.goBack(); await expect(page.locator(".taxonomy-focus h3")).toHaveText("Smilodon");
  await page.goForward(); await expect(page.locator(".taxonomy-focus h3")).toHaveText("Mammalia");
  await page.goBack(); await expect(page.locator(".taxonomy-focus h3")).toHaveText("Smilodon");
  await page.reload(); await expect(row).toBeFocused();
  expect(new URL(page.url()).searchParams.has("expanded")).toBe(false);
});

test("a mixed branch exposes separate material and occurrence counts across source filters", async ({ page, request }) => {
  const found = await (await request.get(`${apiBase}/taxonomy/search?q=Mammalia`)).json();
  const mixed: TaxonomyNode = found.items.find((node: TaxonomyNode) => node.name === "Mammalia" && node.sources.length === 2);
  expect(mixed).toBeTruthy();
  await page.goto(`/lineage?taxonomy_focus=${mixed.id}`);
  const counts = page.locator(".taxonomy-evidence-counts dd");
  await expect(counts.nth(0)).toHaveText(mixed.counts.ufvp_material_count.toLocaleString("en-US"));
  await expect(counts.nth(1)).toHaveText(mixed.counts.pbdb_occurrence_count.toLocaleString("en-US"));
  await page.locator(".source-filter select").selectOption("pbdb");
  await expect(counts.nth(0)).toHaveText("0");
  await expect(counts.nth(1)).toHaveText(mixed.counts.pbdb_occurrence_count.toLocaleString("en-US"));
  expect(new URL(page.url()).searchParams.get("taxonomy_focus")).toBe(mixed.id);
  await page.locator(".source-filter select").selectOption("ufvp");
  await expect(counts.nth(1)).toHaveText("0");
  await expect(counts.nth(0)).toHaveText(mixed.counts.ufvp_material_count.toLocaleString("en-US"));
});

test("taxonomy combobox supports keyboard selection and Escape", async ({ page }) => {
  await page.goto("/lineage");
  const input = page.getByRole("combobox", { name: "Find a taxonomic group" });
  await input.fill("Smilodon");
  await expect(page.locator("#taxonomy-matches [role=option]").first()).toBeVisible();
  await input.press("ArrowDown");
  await expect(input).toHaveAttribute("aria-activedescendant", /taxonomy-match-/);
  await input.press("Enter");
  await expect(page.locator(".taxonomy-focus h3")).toContainText("Smilodon");
  await expect(input).toHaveValue("");
  await input.fill("Animalia"); await input.press("Escape");
  await expect(page.locator("#taxonomy-matches")).toHaveCount(0);
});

test("a linked Atlas view from the direct Lineage route restores on reload", async ({ page, request }) => {
  const found = await (await request.get(`${apiBase}/taxonomy/search?q=Smilodon&source=ufvp`)).json();
  const genus: TaxonomyNode = found.items.find((node: TaxonomyNode) => node.name === "Smilodon" && node.rank === "genus");
  expect(genus).toBeTruthy();
  await page.goto(`/lineage?taxonomy_focus=${genus.id}`);
  await expect(page.locator(".taxonomy-focus h3")).toHaveText("Smilodon");
  await page.getByRole("button", { name: "Show on Atlas", exact: false }).click();
  const atlas = page.getByRole("button", { name: "Atlas", exact: true });
  await expect(atlas).toHaveAttribute("aria-pressed", "true");
  const taxon = new URL(page.url()).searchParams.get("taxon_id");
  expect(taxon).toBeTruthy();
  await page.reload();
  await expect(atlas).toHaveAttribute("aria-pressed", "true");
  expect(new URL(page.url()).searchParams.get("taxon_id")).toBe(taxon);
});

test("mobile focused taxonomy stays above attribution and its detail remains reachable", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const found = await (await request.get(`${apiBase}/taxonomy/search?q=Smilodon&source=ufvp`)).json();
  const genus: TaxonomyNode = found.items.find((node: TaxonomyNode) => node.name === "Smilodon" && node.rank === "genus");
  await page.goto(`/lineage?taxonomy_focus=${genus.id}`);
  const row = page.locator(`#taxonomy-row-${genus.id}`);
  await expect(row).toBeFocused();
  const rowBox = (await row.boundingBox())!;
  const footerBox = (await page.locator(".canvas-source").boundingBox())!;
  expect(rowBox.y + rowBox.height).toBeLessThanOrEqual(footerBox.y + 1);
  const title = page.locator(".taxonomy-focus h3");
  await title.scrollIntoViewIfNeeded();
  await expect(title).toHaveText("Smilodon");
  const titleBox = (await title.boundingBox())!;
  expect(titleBox.y + titleBox.height).toBeLessThanOrEqual(footerBox.y + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("child loading and recoverable failure preserve the tree and retry one branch", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(done => { release = done; });
  await page.route("**/api/v1/taxonomy/nodes/*/children?**", async route => {
    await gate; await route.fulfill({ status: 503, json: { error: { message: "Branch temporarily unavailable" } } });
  });
  await page.goto("/lineage");
  await page.getByRole("button", { name: "Expand Animalia", exact: true }).click();
  await expect(page.getByRole("treeitem").filter({ hasText: "Animalia" })).toContainText("Loading children");
  release(); await expect(page.locator(".taxonomy-pagination")).toContainText("Branch temporarily unavailable");
  await page.unroute("**/api/v1/taxonomy/nodes/*/children?**");
  await page.getByRole("button", { name: "Retry children", exact: true }).click();
  await expect(page.getByRole("treeitem").filter({ hasText: "Chordata" })).toBeVisible();
  await expect(page.locator(".taxonomy-pagination [role=alert]")).toHaveCount(0);
});

test("a failed node selection never labels the previous node as the requested identity", async ({ page, request }) => {
  const roots: TaxonomyNode[] = (await (await request.get(`${apiBase}/taxonomy/roots`)).json()).items;
  const first = roots[0], second = roots[1];
  expect(second).toBeTruthy();
  await page.goto(`/lineage?taxonomy_focus=${first.id}`);
  await expect(page.locator(".taxonomy-focus h3")).toHaveText(first.name);
  await page.route(`**/api/v1/taxonomy/nodes/${second.id}?**`, route => route.fulfill({ status: 503, json: { error: { message: "Node unavailable" } } }));
  await page.locator(`#taxonomy-row-${second.id}`).click();
  await expect(page.locator(".snapshot-status")).toContainText("Node unavailable");
  await expect(page.locator(".taxonomy-focus")).toHaveCount(0);
  expect(new URL(page.url()).searchParams.get("taxonomy_focus")).toBe(second.id);
});

test("focused path batch failure is explicit and retry reconstructs the branch", async ({ page, request }) => {
  const found = await (await request.get(`${apiBase}/taxonomy/search?q=Smilodon&source=ufvp`)).json();
  const node: TaxonomyNode = found.items.find((item: TaxonomyNode) => item.name === "Smilodon" && item.rank === "genus");
  const route = `**/api/v1/taxonomy/nodes/${node.id}/branch-children?**`;
  await page.route(route, request => request.fulfill({ status: 503, json: { error: { message: "Classification path unavailable" } } }));
  await page.goto(`/lineage?source=ufvp&taxonomy_focus=${node.id}`);
  await expect(page.locator(".snapshot-status")).toContainText("Classification path unavailable");
  await page.unroute(route);
  await page.getByRole("button", { name: "Retry taxonomy", exact: true }).click();
  await expect(page.locator(`#taxonomy-row-${node.id}`)).toBeFocused();
  await expect(page.locator(".snapshot-status")).toHaveCount(0);
});


test("a focused sibling beyond page one remains reachable and large branches keep a bounded DOM", async ({ page, request }) => {
  const roots = await (await request.get(`${apiBase}/taxonomy/roots`)).json();
  const root: TaxonomyNode = roots.items.find((node: TaxonomyNode) => node.name === "Animalia");
  const children: TaxonomyNode[] = Array.from({ length: 160 }, (_, index) => ({
    ...root, id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    parent_id: root.id, name: `Fixture genus ${String(index).padStart(3, "0")}`, rank: "genus",
    path: [...root.path], counts: { ...root.counts, child_count: 0 },
  }));
  const focused = children.at(-1)!;
  await page.route(`**/api/v1/taxonomy/nodes/${root.id}/children?**`, route => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset") ?? 0);
    return route.fulfill({ json: { items: children.slice(offset, offset + 100), total: 160, next_offset: offset ? null : 100, version: roots.version, scope: "florida" } });
  });
  await page.route(`**/api/v1/taxonomy/nodes/${focused.id}?**`, route => route.fulfill({ json: { node: focused, ancestors: [root], concepts: [], concept_total: 0, evidence: [], version: roots.version } }));
  await page.route(`**/api/v1/taxonomy/nodes/${children[0].id}?**`, route => route.fulfill({ json: { node: children[0], ancestors: [root], concepts: [], concept_total: 0, evidence: [], version: roots.version } }));
  for (const id of [focused.id, children[0].id]) await page.route(`**/api/v1/taxonomy/nodes/${id}/branch-children?**`, route => route.fulfill({ json: { items: [{ parent_id: root.id, page: { items: children.slice(0, 100), total: 160, next_offset: 100, version: roots.version, scope: "florida" } }], next_offset: null, version: roots.version } }));
  await page.goto(`/lineage?taxonomy_focus=${focused.id}`);
  await expect(page.locator(`#taxonomy-row-${focused.id}`)).toBeFocused();
  await expect(page.locator(".taxonomy-focus h3")).toHaveText(focused.name);
  await expect(page.locator(".taxonomy-pagination")).toContainText("100 of 160 children");
  await page.getByRole("button", { name: "Load more children", exact: true }).click();
  await expect.poll(() => page.getByRole("treeitem").count()).toBeLessThanOrEqual(26);
  await page.locator(".taxonomy-scroll").evaluate(element => { element.scrollTop = 0; });
  const first = page.locator(`#taxonomy-row-${root.id}`); await first.focus(); await first.press("End");
  await expect(page.getByRole("treeitem").last()).toBeFocused();
  await page.locator(".taxonomy-scroll").evaluate(element => { element.scrollTop = 0; });
  await page.locator(`#taxonomy-row-${children[0].id}`).click();
  await expect(page.locator(`#taxonomy-row-${children[0].id}`)).toBeFocused();
  await page.goBack(); await expect(page.locator(`#taxonomy-row-${focused.id}`)).toBeFocused();
  await page.goForward(); await expect(page.locator(`#taxonomy-row-${children[0].id}`)).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
