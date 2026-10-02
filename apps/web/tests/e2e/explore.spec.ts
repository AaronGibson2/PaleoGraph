import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  // External basemap availability must not determine application test results.
  // The real MapLibre worker, WebGL layers, API and database still run.
  await page.route("https://tiles.openfreemap.org/**", route => route.fulfill({
    json: { version: 8, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#dfe7e3" } }] },
  }));
});

test("database occurrences, inspection, time filtering, and URL restoration", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/explore");
  const results = page.locator(".occurrence-list button");
  await expect(results.first()).toBeVisible();
  const initialCount = await results.count();
  expect(initialCount).toBeGreaterThan(5);
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  const mapHeight = await page.locator(".map-canvas").evaluate(element => element.getBoundingClientRect().height);
  expect(mapHeight).toBeGreaterThan(400);
  await expect(page.getByText("Synthetic demo data", { exact: false })).toBeVisible();
  await expect(page.locator(".map-notice")).toHaveCount(0);
  await results.first().click();
  await expect(page.getByRole("heading", { name: "Sources & evidence" })).toBeVisible();
  await expect(page.locator(".demo-note")).toContainText("not evidence of a real fossil");
  const selected = new URL(page.url()).searchParams.get("selected");
  expect(selected).toBeTruthy();
  await page.getByRole("button", { name: "2–0.1 Ma", exact: true }).click();
  await expect(page.locator(".result-count")).not.toContainText("Updating");
  await expect.poll(() => results.count()).toBeLessThan(initialCount);
  expect(new URL(page.url()).searchParams.get("older_ma")).toBe("2");
  await page.reload();
  await expect(page.getByRole("button", { name: "2–0.1 Ma", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".inspector")).toBeVisible();
  await expect(page.locator(".inspector .demo-note")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("selected")).toBe(selected);
  expect(errors).toEqual([]);
});

test("empty view and recoverable API failure", async ({ page }) => {
  await page.goto("/explore?lat=0&lng=0&zoom=7");
  await expect(page.getByText("No occurrences in this view and age range.", { exact: false })).toBeVisible();
  await page.route("**/api/v1/map/occurrences?**", route => route.fulfill({ status: 503, json: { error: { code: "DATABASE_UNAVAILABLE", message: "Occurrence data is temporarily unavailable." } } }));
  await page.getByRole("button", { name: "Return to Florida" }).click();
  await expect(page.getByRole("button", { name: "Retry data" })).toBeVisible();
  await expect(page.locator(".occurrence-list button")).toHaveCount(0);
  await page.unroute("**/api/v1/map/occurrences?**");
  await page.getByRole("button", { name: "Retry data" }).click();
  await expect(page.locator(".occurrence-list button").first()).toBeVisible();
});

test("mobile keyboard inspection and focus restoration", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/explore");
  const first = page.locator(".occurrence-list button").first();
  await expect(first).toBeVisible();
  await first.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#inspection-heading")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.locator(".inspector")).toHaveCount(0);
  await expect(first).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("map markers expose co-located assertions and browser history restores selection", async ({ page, request }) => {
  const response = await request.get("http://localhost:8000/api/v1/map/occurrences?west=-88&south=24&east=-79&north=32");
  expect(response.ok()).toBe(true);
  const { items } = await response.json();
  const point = items[0];
  await page.goto(`/explore?lat=${point.latitude}&lng=${point.longitude}&zoom=9`);
  await expect(page.locator(".occurrence-list button").first()).toBeVisible();
  const canvas = page.locator(".maplibregl-canvas");
  // The API point is at the map center; retry while the real worker paints GeoJSON.
  await expect(async () => {
    await canvas.click();
    await expect(page.locator(".map-choice").first()).toBeVisible({ timeout: 500 });
  }).toPass();
  await page.locator(".map-choice").first().click();
  await expect(page.getByRole("heading", { name: "Sources & evidence" })).toBeVisible();
  const selected = new URL(page.url()).searchParams.get("selected");
  await page.goBack();
  await expect(page.locator(".inspector")).toHaveCount(0);
  await page.goForward();
  await expect(page.locator(".inspector .demo-note")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("selected")).toBe(selected);
});
