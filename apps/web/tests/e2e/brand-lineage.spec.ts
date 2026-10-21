import { expect, test } from "@playwright/test";
import { apiBase, stubBasemap } from "./helpers";
import type { TaxonomyNode } from "../../lib/api/taxonomy";

test.beforeEach(async ({ page }) => stubBasemap(page));

test("brand mark identifies Home, the workspace and the browser at desktop and phone widths", async ({ page, request }) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("link", { name: "PaleoGraph home", exact: true })).toBeVisible();
    await expect(page.locator(".site-header .brand-mark")).toBeVisible();
    const icon = await page.locator('link[rel="icon"]').getAttribute("href");
    expect(icon).toContain("icon.svg");
    const response = await request.get(icon!);
    expect(response.ok()).toBe(true);
    expect(response.headers()["content-type"]).toContain("image/svg+xml");
    await page.goto("/explore?catalog=open");
    await expect(page.locator(".atlas-wordmark .brand-mark")).toBeVisible();
    await expect(page.locator(".catalog-entry").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("link", { name: "PaleoGraph home", exact: true }).click();
    await expect(page.locator("#home-title")).toBeVisible();
  }
});

test("one classification node exposes combined and source-filtered evidence without changing identity", async ({ page, request }) => {
  const roots = await (await request.get(`${apiBase}/taxonomy/roots?source=all`)).json();
  const root: TaxonomyNode = roots.items.find((node: TaxonomyNode) => node.sources.length === 2);
  expect(root).toBeTruthy();
  await page.goto(`/lineage?taxonomy_focus=${root.id}&source=all`);
  await expect(page.locator(".taxonomy-focus h3")).toHaveText(root.name);
  for (const source of ["all", "ufvp", "pbdb"]) {
    await page.getByRole("combobox", { name: "Evidence source", exact: true }).selectOption(source);
    const detail = await (await request.get(`${apiBase}/taxonomy/nodes/${root.id}?source=${source}`)).json();
    await expect(page.locator(".taxonomy-evidence-counts")).toContainText(detail.node.counts.evidence_count.toLocaleString("en-US"));
    await expect(page.locator(".taxonomy-focus h3")).toHaveText(root.name);
    expect(new URL(page.url()).searchParams.get("taxonomy_focus")).toBe(root.id);
  }
  await page.reload();
  await expect(page.locator(".taxonomy-focus h3")).toHaveText(root.name);
});
