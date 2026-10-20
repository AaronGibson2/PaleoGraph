import { expect, test } from "@playwright/test";
import type { TaxonomyNode } from "../../lib/api/taxonomy";
import { apiBase } from "./helpers";

// Opt in against the retained Florida database. These tests use read endpoints only;
// the ordinary browser suite owns a much smaller disposable fixture database.
test.skip(process.env.PALEOGRAPH_REAL_FLORIDA !== "1", "Requires the real Florida snapshot");

for (const source of ["all", "ufvp", "pbdb"]) {
  test(`${source} roots remain bounded and never expose species as roots`, async ({ page, request }, testInfo) => {
    const legacyRequests: string[] = [];
    page.on("request", request => {
      if (new URL(request.url()).pathname === "/api/v1/lineage") legacyRequests.push(request.url());
    });
    const response = await request.get(`${apiBase}/taxonomy/roots?source=${source}`);
    expect(response.ok()).toBe(true);
    const roots = await response.json();
    expect(roots.total).toBeLessThan(50);
    expect(roots.items.length).toBe(roots.total);
    expect(roots.items.every((node: TaxonomyNode) => !["species", "subspecies", "genus"].includes(node.rank ?? ""))).toBe(true);
    await page.goto(`/lineage?source=${source}`);
    const tree = page.getByRole("tree");
    await expect(tree).toHaveAttribute("aria-busy", "false");
    await expect(page.getByRole("treeitem")).toHaveCount(roots.total);
    expect(legacyRequests).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`roots-${source}.png`) });
  });
}

test("Animalia, Chordata and Mammalia expand as a tree", async ({ page }, testInfo) => {
  await page.goto("/lineage?source=ufvp");
  for (const name of ["Animalia", "Chordata", "Mammalia"]) {
    await page.getByRole("button", { name: `Expand ${name}`, exact: true }).click();
    await expect(page.getByRole("button", { name: `Collapse ${name}`, exact: true })).toBeVisible();
  }
  await expect(page.getByRole("treeitem").filter({ hasText: "Mammalia" }).first()).toHaveAttribute("aria-level", "3");
  await page.screenshot({ path: testInfo.outputPath("mammalia-expanded.png") });
});

for (const name of ["Lutra canadensis", "Divaricella chipolana", "Bufo woodhousei fowleri", "Velates floridanus"]) {
  test(`${name} remains nested through search, filters, reload and history`, async ({ page, request }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const response = await request.get(`${apiBase}/taxonomy/search?source=pbdb&q=${encodeURIComponent(name)}`);
    expect(response.ok()).toBe(true);
    const node: TaxonomyNode = (await response.json()).items.find((item: TaxonomyNode) => item.name === name);
    expect(node).toBeTruthy();
    expect(node.parent_id).toBeTruthy();
    const ancestryResponse = await request.get(`${apiBase}/taxonomy/nodes/${node.id}/ancestors?source=pbdb`);
    expect(ancestryResponse.ok()).toBe(true);
    const ancestors: TaxonomyNode[] = (await ancestryResponse.json()).items;
    expect(ancestors.length).toBeGreaterThan(3);
    expect(ancestors[0].name).toBe("Life");

    await page.goto("/lineage?source=pbdb");
    await page.getByRole("combobox", { name: "Find a taxonomic group" }).fill(name);
    await page.locator("#taxonomy-matches [role=option]").filter({ hasText: name }).first().click();
    const row = page.locator(`#taxonomy-row-${node.id}`);
    await expect(page.locator(".taxonomy-focus h3")).toHaveText(name);
    await expect(row).toBeFocused();
    await expect(row).toHaveAttribute("aria-level", String(ancestors.length + 1));
    expect(new URL(page.url()).searchParams.get("taxonomy_focus")).toBe(node.id);
    await page.screenshot({ path: testInfo.outputPath("pbdb-nested.png") });

    await page.locator(".source-filter select").selectOption("all");
    await expect(row).toBeFocused();
    await expect(page.locator(".taxonomy-focus h3")).toHaveText(name);
    await page.goBack();
    await expect(page.locator(".source-filter select")).toHaveValue("pbdb");
    await expect(row).toBeFocused();
    await page.goForward();
    await expect(page.locator(".source-filter select")).toHaveValue("all");
    await expect(row).toBeFocused();
    await page.reload();
    await expect(row).toBeFocused();
    await expect(page.locator(".taxonomy-focus h3")).toHaveText(name);
    await expect(row).toHaveAttribute("aria-level", String(ancestors.length + 1));
    await expect(page.locator(".taxonomy-source-hierarchy").first()).toContainText("PBDB");
    expect(errors).toEqual([]);
  });
}
