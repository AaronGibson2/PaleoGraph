import { expect, test } from "@playwright/test";
import { apiBase, stubBasemap } from "./helpers";

test.beforeEach(async ({ page }) => stubBasemap(page));

test("Atlas keeps source metadata out of the everyday view and reveals retained credits on request", async ({ page, request }) => {
  const dataset = await (await request.get(`${apiBase}/datasets/ufvp`)).json();
  await page.goto("/explore?source=all");
  await expect(page.locator(".map-status")).toHaveCount(0);
  const sources = page.locator(".atlas-source-information");
  const sheet = page.locator(".atlas-source-sheet");
  await expect(sources).toBeVisible();
  await expect(sheet).toBeHidden();
  await expect(page.locator(".canvas-source")).toHaveCount(0);
  const canvas = await page.locator(".map-canvas").elementHandle();
  const before = page.url();
  await sources.locator("summary").click();
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole("link", { name: "CC BY-NC 4.0", exact: false })).toHaveAttribute("href", "https://creativecommons.org/licenses/by-nc/4.0/");
  await expect(sheet.getByRole("link", { name: "CC0 1.0", exact: false })).toHaveAttribute("href", "https://creativecommons.org/publicdomain/zero/1.0/");
  await expect(sheet).toContainText(dataset.creator);
  await expect(sheet.locator(".source-import-status")).toContainText(`${dataset.current_records.toLocaleString("en-US")} assertions`);
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(sources.locator("summary")).toBeFocused();
  expect(page.url()).toBe(before);
  expect(await canvas?.evaluate(element => element.isConnected)).toBeTruthy();
  await expect(page.locator(".unmapped-evidence")).toBeVisible();
});

test("source information closes on an outside click without stealing the new focus", async ({ page }) => {
  await page.goto("/explore");
  const sources = page.locator(".atlas-source-information");
  await sources.locator("summary").click();
  await expect(page.locator(".atlas-source-sheet")).toBeVisible();
  await page.locator("#atlas-search").click();
  await expect(page.locator(".atlas-source-sheet")).toBeHidden();
  await expect(page.locator("#atlas-search")).toBeFocused();
});

test("phone source sheet stays within the screen and preserves map attribution and record space", async ({ page, request }) => {
  const sample = await (await request.get(`${apiBase}/catalog?source=all&limit=1`)).json();
  expect(sample.items.length).toBeGreaterThan(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/explore?catalog=open&catalog_scope=archive&source=all&catalog_q=${encodeURIComponent(sample.items[0].scientific_name)}`);
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
  expect((await page.locator(".catalog-list").boundingBox())!.height).toBeGreaterThan(150);
  const panel = (await page.locator(".catalog-panel").boundingBox())!;
  const attribution = (await page.locator(".maplibregl-ctrl-attrib").boundingBox())!;
  expect(attribution.y).toBeGreaterThanOrEqual(panel.y + panel.height);
  await page.getByRole("button", { name: "Close catalog", exact: true }).click();
  const sources = page.locator(".atlas-source-information");
  const trigger = sources.locator("summary");
  expect((await trigger.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await trigger.click();
  const sheet = page.locator(".atlas-source-sheet");
  await expect(sheet).toBeVisible();
  const bounds = (await sheet.boundingBox())!;
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
  expect(bounds.y).toBeGreaterThanOrEqual(156);
  await expect(page.locator(".maplibregl-ctrl-attrib")).toBeVisible();
  const credit = (await page.locator(".maplibregl-ctrl-attrib").boundingBox())!;
  expect(credit.y + credit.height).toBeLessThanOrEqual((await trigger.boundingBox())!.y);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByRole("button", { name: "Close sources and data" }).click();
  await expect(sheet).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("metadata refresh failure retains the source snapshot without reopening the panel", async ({ page, request }) => {
  const dataset = await (await request.get(`${apiBase}/datasets/ufvp`)).json();
  await page.goto("/explore");
  const sources = page.locator(".atlas-source-information");
  await sources.locator("summary").click();
  await expect(sources.locator(".source-import-status")).toContainText(`${dataset.current_records.toLocaleString("en-US")} assertions`);
  await page.keyboard.press("Escape");
  await page.route("**/api/v1/datasets/ufvp", route => route.fulfill({ status: 503, json: { error: { message: "Test metadata unavailable" } } }));
  await page.evaluate(() => { const original = Date.now; Date.now = () => original() + 61_000; window.dispatchEvent(new Event("focus")); });
  await expect(sources.locator(".source-import-status")).toContainText("Last loaded import status / refresh unavailable");
  await expect(page.locator(".atlas-source-sheet")).toBeHidden();
  await sources.locator("summary").click();
  await expect(sources.locator(".source-import-status")).toContainText(`${dataset.current_records.toLocaleString("en-US")} assertions`);
});
