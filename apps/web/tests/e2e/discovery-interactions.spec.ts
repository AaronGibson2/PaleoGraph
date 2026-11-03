import { expect, test, type Page } from "@playwright/test";
import { stubBasemap } from "./helpers";

// Controlled responses exercise transport failures and races independently of
// retained scientific data. The live-data tests are in discovery-guide.spec.ts.
const id = "de000000-0000-4000-8000-000600000001";
const counts = { evidence_count: 14, direct_count: 1, ufvp_material_count: 10, pbdb_occurrence_count: 4, child_count: 2, known_age_count: 11, unknown_age_count: 3, older_ma: 5.333, younger_ma: 0, derived_count: 7, source_numeric_count: 4, derived_older_ma: 5.333, derived_younger_ma: 0, source_older_ma: 2, source_younger_ma: 0 };
const node = (name: string) => ({ id, parent_id: null, name, rank: "class", placement: "supported", sources: ["ufvp", "pbdb"], path: [], counts, classification_path_ids: [] });
const catalogItem = { id, specimen_id: id, source: "ufvp", label: "UF TEST 1", scientific_name: "Test taxon", taxon_id: id, classification_path_ids: [], locality_id: null, locality_name: "Test locality", longitude: null, latitude: null, older_ma: null, younger_ma: null, age_basis: "absent", source_age_label: null };

async function controlledApi(page: Page) {
  await stubBasemap(page);
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/time-intervals")) return route.fulfill({ json: { version: "test", kind: "international_chronostratigraphic_chart", max_ma: 4567, attribution: "Test reference", source_url: "https://example.org", license_url: "https://example.org", units: [{ id: "ics:2026-06:cenozoic", name: "Cenozoic", rank: "Era", parent: null, older_ma: 66, younger_ma: 0, color: "#ffff00" }] } });
    if (url.pathname.endsWith("/datasets/ufvp")) return route.fulfill({ json: { title: "Controlled test dataset", dataset_url: "https://example.org", current_records: 14, mapped_records: 0, numeric_age_records: 11 } });
    if (url.pathname.endsWith("/taxonomy/search")) return route.fulfill({ json: { items: [node(url.searchParams.get("q") ?? "Mammalia")], total: 1, next_offset: null, version: "test", scope: "florida" } });
    if (url.pathname.endsWith("/catalog")) return route.fulfill({ json: { items: url.searchParams.get("q") ? [] : [catalogItem], total: url.searchParams.get("q") ? 0 : 1, next_cursor: null, limit: 30 } });
    return route.fulfill({ json: { items: [], total_records: 0, total_places: 0, unmapped_records: 0, limit: 1500, next_cursor: null } });
  });
}

test("guide dismisses with keyboard and restores focus at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await controlledApi(page);
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/explore?source=all&discover=open");
  await expect(page.locator(".discovery-card-title strong")).toHaveText("Mammalia");
  await expect(page.locator("#discovery-heading")).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByRole("button", { name: "Birds", exact: true }).click();
  await expect(page.locator(".discovery-card-title strong")).toHaveText("Aves");
  await page.reload();
  await expect(page.getByRole("searchbox", { name: "Find a classification" })).toHaveValue("Aves");
  await page.keyboard.press("Escape");
  await expect(page.locator(".discovery-panel")).toHaveCount(0);
  await expect(page.locator("#discovery-toggle")).toBeFocused();
  expect(errors).toEqual([]);
});

test("late discovery response cannot replace a newer group", async ({ page }) => {
  await controlledApi(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/taxonomy/search?**", async route => {
    const q = new URL(route.request().url()).searchParams.get("q");
    if (q === "Mammalia") await held;
    await route.fulfill({ json: { items: [node(q ?? "")], total: 1, next_offset: null, version: "test", scope: "florida" } }).catch(() => {});
  });
  await page.goto("/explore?source=all&discover=open");
  const input = page.getByRole("searchbox", { name: "Find a classification" });
  await expect(page.locator(".discovery-status")).toContainText("Finding");
  await input.fill("Aves");
  await expect(page.locator(".discovery-card-title strong")).toHaveText("Aves");
  release();
  await expect(page.locator(".discovery-card-title strong")).toHaveText("Aves");
});

test("failed discovery has an explicit retry and never invents empty results", async ({ page }) => {
  await controlledApi(page);
  let failed = true;
  await page.route("**/api/v1/taxonomy/search?**", route => failed ? route.fulfill({ status: 503, json: { error: { message: "Test taxonomy unavailable" } } }) : route.fulfill({ json: { items: [node("Mammalia")], total: 1, next_offset: null, version: "test", scope: "florida" } }));
  await page.goto("/explore?discover=open");
  await expect(page.locator(".discovery-results [role=alert]")).toContainText("Test taxonomy unavailable");
  await expect(page.locator(".discovery-empty")).toHaveCount(0);
  failed = false;
  await page.getByRole("button", { name: "Retry discovery" }).click();
  await expect(page.locator(".discovery-card-title strong")).toHaveText("Mammalia");
});

test("catalog area changes request bounds and empty-search recovery clears only catalog text", async ({ page }) => {
  await controlledApi(page);
  const requests: URL[] = [];
  page.on("request", request => { const url = new URL(request.url()); if (url.pathname.endsWith("/catalog")) requests.push(url); });
  await page.goto("/explore?source=all&catalog=open");
  await expect(page.locator(".catalog-entry")).toHaveCount(1);
  expect(requests.at(-1)?.searchParams.has("west")).toBeTruthy();
  await page.locator(".catalog-options summary").click();
  await page.getByLabel("Catalog area", { exact: true }).selectOption("archive");
  await expect.poll(() => requests.at(-1)?.searchParams.has("west")).toBe(false);
  await page.getByRole("searchbox", { name: "Search these evidence records" }).fill("missing");
  await expect(page.locator(".panel-message")).toContainText("No evidence matches");
  await page.getByRole("button", { name: "Clear catalog search", exact: true }).last().click();
  await expect(page.locator(".catalog-entry")).toHaveCount(1);
  await page.getByRole("button", { name: "Records", exact: true }).click();
  await page.reload();
  await expect(page.locator(".catalog-panel")).toHaveAttribute("data-view", "records");
  await expect(page.getByLabel("Catalog area", { exact: true })).toHaveValue("archive");
});
