import { expect, test } from "@playwright/test";
import { apiBase, stubBasemap } from "./helpers";

test.beforeEach(async ({ page }) => stubBasemap(page));

test("discovery opens real classification results and restores the guide through history", async ({ page, request }) => {
  const response = await request.get(`${apiBase}/taxonomy/search?source=all&q=Mammalia&limit=12`);
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  expect(data.items.length).toBeGreaterThan(0);
  await page.goto("/explore?source=all&discover=open");
  const guide = page.getByRole("complementary", { name: "Follow your curiosity." });
  await expect(guide.getByRole("heading", { level: 2 })).toBeFocused();
  await expect(guide.locator(".discovery-cards li")).toHaveCount(data.items.length);
  await expect(guide.locator(".discovery-card-count").first()).toContainText(data.items[0].counts.evidence_count.toLocaleString("en-US"));
  await guide.locator(".discovery-cards li > button").first().click();
  await expect(page).toHaveURL(new RegExp(`taxonomy_focus=${data.items[0].id}`));
  await expect(page.locator(".taxonomy-focus h3")).toHaveText(data.items[0].name);
  await expect(guide).toHaveCount(0);
  await page.goBack();
  await expect(guide).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(guide).toHaveCount(0);
  await expect(page.locator("#discovery-toggle")).toBeFocused();
});

test("catalog searches the API, restores presentation, and can include unmapped archive evidence", async ({ page, request }) => {
  const sample = await (await request.get(`${apiBase}/catalog?source=all&limit=1`)).json();
  const needle = sample.items[0].scientific_name;
  const response = await request.get(`${apiBase}/catalog?source=all&q=${encodeURIComponent(needle)}&limit=30`);
  const expected = await response.json();
  await page.goto("/explore?source=all&catalog=open");
  await page.locator(".catalog-options summary").click();
  await page.getByLabel("Catalog area", { exact: true }).selectOption("archive");
  await page.getByRole("searchbox", { name: "Search these evidence records" }).fill(needle);
  await expect(page.locator(".result-count")).toHaveText(`${expected.total.toLocaleString("en-US")} evidence records`);
  await expect(page.locator(".catalog-entry")).toHaveCount(expected.items.length);
  await page.getByRole("button", { name: "Records", exact: true }).click();
  await page.reload();
  await expect(page.locator(".catalog-panel")).toHaveAttribute("data-view", "records");
  await expect(page.getByRole("searchbox", { name: "Search these evidence records" })).toHaveValue(needle);
  await expect(page.getByLabel("Catalog area", { exact: true })).toHaveValue("archive");
  await page.getByRole("button", { name: "Clear catalog search", exact: true }).click();
  await expect(page.getByRole("searchbox", { name: "Search these evidence records" })).toHaveValue("");
  await expect(page.locator(".result-count")).toHaveText(`${sample.total.toLocaleString("en-US")} evidence records`);
});

test("geological shortcuts use the real pinned interval and retain source context", async ({ page, request }) => {
  const configuration = await (await request.get(`${apiBase}/time-intervals`)).json();
  const interval = configuration.units.find((item: { name: string }) => item.name === "Pleistocene");
  await page.goto("/explore?source=all&discover=open");
  await page.locator(".discovery-intervals").getByRole("button", { name: /Pleistocene/ }).click();
  await expect(page.locator(".catalog-panel")).toBeVisible();
  const params = new URL(page.url()).searchParams;
  expect(params.get("older_ma")).toBe(String(interval.older_ma));
  expect(params.get("younger_ma")).toBe(String(interval.younger_ma));
  expect(params.get("interval_id")).toBe(interval.id);
  expect(params.get("catalog_scope")).toBe("archive");
  expect(params.get("source")).toBe("all");
});

test("PBDB catalog stays unbounded and an empty search offers recovery", async ({ page }) => {
  const catalogRequests: URL[] = [];
  page.on("request", request => { if (new URL(request.url()).pathname.endsWith("/catalog")) catalogRequests.push(new URL(request.url())); });
  await page.goto("/explore?source=pbdb&catalog=open&catalog_q=zzznomatchpaleograph");
  await expect(page.getByLabel("Catalog area", { exact: true })).toBeDisabled();
  await expect(page.getByLabel("Catalog area", { exact: true })).toHaveValue("archive");
  await expect(page.locator(".panel-message")).toContainText("No evidence matches");
  expect(catalogRequests.length).toBeGreaterThan(0);
  expect(catalogRequests.every(url => !url.searchParams.has("west"))).toBeTruthy();
  await page.getByRole("button", { name: "Clear catalog search", exact: true }).last().click();
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
});

test("phone discovery remains usable without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/explore?source=all&discover=open");
  await expect(page.locator(".discovery-cards li").first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByRole("button", { name: "Birds", exact: true }).click();
  await expect(page.getByRole("searchbox", { name: "Find a classification" })).toHaveValue("Aves");
  await page.getByRole("button", { name: "Close discovery guide" }).click();
  await expect(page.locator("#discovery-toggle")).toBeFocused();
});

test("phone catalog leaves room for records with secondary refinements collapsed", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/explore?source=all&catalog=open&catalog_scope=archive&catalog_q=Canis");
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
  const list = await page.locator(".catalog-list").boundingBox();
  expect(list?.height).toBeGreaterThan(150);
  await expect(page.locator(".catalog-options")).not.toHaveAttribute("open");
  await page.locator(".catalog-options summary").click();
  await expect(page.getByLabel("Catalog area", { exact: true })).toBeVisible();
  await page.locator(".catalog-options summary").click();
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
});
