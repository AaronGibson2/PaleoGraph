import { expect, test } from "@playwright/test";
import { apiBase, stubBasemap } from "./helpers";
test.beforeEach(async ({ page }) => stubBasemap(page));

test("locality counts, fauna pivot, material and surface history share scientific context", async ({ page, request }) => {
  const response = await request.get(`${apiBase}/localities?limit=1`);
  const site = (await response.json()).items[0];
  await page.goto(`/explore?surface=localities&locality_id=${site.id}`);
  await expect(page.locator(".locality-counts")).toContainText(String(site.assertion_count));
  await expect(page.locator(".locality-surface")).toContainText("Locality association ≠ contemporaneous community");
  await page.getByRole("button", { name: "Associated material", exact: false }).click();
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
  await page.locator(".catalog-entry").first().click();
  await expect(page.locator(".specimen-placeholder:not(.compact)")).toContainText("Specimen image unavailable");
  expect(new URL(page.url()).searchParams.get("locality_id")).toBe(site.id);
  await page.getByRole("button", { name: "Close occurrence inspection" }).click();
  await page.getByRole("button", { name: "Close catalog" }).click();
  await page.locator(".association-rows button").first().click();
  await expect(page.locator(".lineage-focus")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("surface")).toBe("lineage");
  expect(new URL(page.url()).searchParams.get("locality_id")).toBe(site.id);
  const focus = new URL(page.url()).searchParams.get("lineage_focus");
  await page.reload(); await expect(page.locator(".lineage-focus")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("lineage_focus")).toBe(focus);
  await page.getByRole("button", { name: "Show on Atlas", exact: false }).click();
  await expect(page.getByRole("button", { name: "Atlas", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.goBack(); await expect(page.locator(".lineage-focus")).toBeVisible();
});

test("classification keyboard focus traverses source ranks without asserting ancestry", async ({ page }) => {
  await page.goto("/explore?surface=lineage");
  const root = page.getByRole("treeitem").filter({ hasText: "Animalia" });
  await expect(root).toBeVisible(); await root.focus(); await page.keyboard.press("ArrowRight");
  await expect(page.locator(".lineage-navigation nav")).toContainText("Animalia");
  await expect(page.getByRole("treeitem").first()).toBeFocused();
  const focus = new URL(page.url()).searchParams.get("lineage_focus");
  expect(focus).toBeTruthy();
  await page.keyboard.press("ArrowLeft");
  await expect.poll(() => new URL(page.url()).searchParams.get("lineage_focus")).toBeNull();
  await expect(page.locator(".scientific-caveat")).toContainText("Classification ≠ phylogeny");
  await expect(page.locator(".lineage-span").first()).toContainText("known");
  await expect(page.locator(".lineage-reference span").first()).toBeVisible();
  await expect(page.locator(".taxon-icon").first()).toBeVisible();
});

test("a selected species remains conjunctive when a genus focus returns to Atlas", async ({ page, request }) => {
  const taxa = (await (await request.get(`${apiBase}/search?q=Smilodon&limit=100`)).json()).items;
  const genus = taxa.find((item: { kind: string; subtitle: string }) => item.kind === "taxon" && item.subtitle === "genus");
  const member = (await (await request.get(`${apiBase}/lineage?focus=${genus.id}`)).json()).items[0];
  await page.goto(`/explore?surface=lineage&lineage_focus=${genus.id}&taxon_id=${member.id}`);
  await expect(page.locator(".lineage-focus")).toBeVisible();
  await page.getByRole("button", { name: "Show on Atlas", exact: false }).click();
  expect(new URL(page.url()).searchParams.get("taxon_id")).toBe(member.id);
});

test("locality and lineage views keep time filtering conjunctive and restore it", async ({ page, request }) => {
  const site = (await (await request.get(`${apiBase}/localities?limit=1`)).json()).items[0];
  await page.goto(`/explore?surface=localities&locality_id=${site.id}&older_ma=4000&younger_ma=3000`);
  await expect(page.locator(".locality-counts dd").first()).toHaveText("0");
  await page.getByRole("button", { name: "Locality in Lineage", exact: false }).click();
  await expect(page.locator(".lineage-surface .panel-message")).toContainText("No indexed material");
  await page.getByRole("button", { name: "All ages", exact: true }).click();
  await expect(page.getByRole("treeitem").first()).toBeVisible();
  expect(new URL(page.url()).searchParams.get("locality_id")).toBe(site.id);
  await page.goBack(); await expect(page.locator(".lineage-surface .panel-message")).toBeVisible();
});

test("mobile locality and lineage use semantic cards with reduced motion and visible source credit", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const site = (await (await request.get(`${apiBase}/localities?limit=1`)).json()).items[0];
  await page.goto(`/explore?surface=localities&locality_id=${site.id}`);
  await expect(page.locator(".locality-counts")).toBeVisible();
  await page.getByRole("button", { name: "Locality in Lineage", exact: false }).click();
  await expect(page.getByRole("treeitem").first()).toBeVisible();
  await page.getByRole("treeitem").first().focus(); await page.keyboard.press("ArrowRight");
  await expect(page.locator(".lineage-focus")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.locator(".canvas-source")).toContainText("CC BY-NC 4.0");
  await expect(page.locator(".maplibregl-ctrl-attrib")).toBeHidden();
  await page.getByRole("button", { name: "Taxon actions", exact: true }).click();
  await page.getByRole("button", { name: "Associated localities", exact: false }).click();
  await expect(page.locator(".locality-counts")).toBeVisible();
});

test("locality refresh retains a labeled snapshot on a recoverable failure", async ({ page, request }) => {
  const site = (await (await request.get(`${apiBase}/localities?limit=1`)).json()).items[0];
  await page.goto(`/explore?surface=localities&locality_id=${site.id}`);
  await expect(page.locator(".locality-counts")).toBeVisible();
  await page.route(`**/api/v1/localities/${site.id}?**`, route => route.fulfill({ status: 503, json: { error: { message: "Temporary outage" } } }));
  await page.locator(".time-window").filter({ hasText: "Quaternary" }).click();
  await expect(page.locator(".snapshot-status")).toContainText("Showing the last loaded locality");
  await expect(page.locator(".locality-counts")).toBeVisible();
  await page.unroute(`**/api/v1/localities/${site.id}?**`);
  await page.getByRole("button", { name: "Retry locality", exact: true }).click();
  await expect(page.locator(".snapshot-status")).toHaveCount(0);
});
