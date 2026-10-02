import { expect, test, type Page } from "@playwright/test";

const endpoint = "**/api/v1/map/occurrences?**";
async function pan(page: Page, fraction: number) {
  const canvas = page.locator(".maplibregl-canvas");
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("Missing map canvas");
  const x = box.x + box.width * 0.55;
  const y = box.y + box.height * 0.55;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + box.width * fraction, y, { steps: 12 });
  // End without fling so this is a deliberate, reproducible distance.
  await page.waitForTimeout(150);
  await page.mouse.up();
}

test.beforeEach(async ({ page }) => {
  await page.route("https://tiles.openfreemap.org/**", route => route.fulfill({
    json: { version: 8, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#dfe7e3" } }] },
  }));
});

test("small pans reuse the buffer; rapid larger pans retain rows and reject late results", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", request => { if (request.url().includes("/map/occurrences?")) requests.push(request.url()); });
  await page.goto("/explore");
  await expect(page.locator(".occurrence-list button").first()).toBeVisible();
  await expect(page.locator(".result-count")).not.toContainText("Updating");
  await page.waitForTimeout(400);
  await page.locator(".occurrence-list button").first().click();
  await expect(page.locator(".inspector .demo-note")).toBeVisible();
  const selected = new URL(page.url()).searchParams.get("selected");
  const initialRequests = requests.length;
  await pan(page, -0.02);
  await page.waitForTimeout(700);
  expect(requests.length).toBe(initialRequests);

  const held: { release: () => void; url: string; done: Promise<void> }[] = [];
  await page.route(endpoint, async route => {
    const response = await route.fetch();
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    const done = gate.then(async () => { await route.fulfill({ response }).catch(() => {}); });
    held.push({ release, url: route.request().url(), done });
    await done;
  });
  const row = await page.locator(".occurrence-list button").first().elementHandle();
  await page.locator(".results-panel").evaluate(element => { element.scrollTop = 140; });
  const scroll = await page.locator(".results-panel").evaluate(element => element.scrollTop);
  await pan(page, -0.4);
  await expect.poll(() => held.length).toBe(1);
  await expect(page.locator(".result-count")).toContainText("Updating");
  expect(await row?.evaluate(element => element.isConnected)).toBe(true);
  expect(await page.locator(".results-panel").evaluate(element => element.scrollTop)).toBe(scroll);
  await expect(page.locator(".inspector .demo-note")).toBeVisible();
  await pan(page, -0.4);
  await expect.poll(() => held.length).toBe(2);
  held[1].release();
  await held[1].done;
  await expect(page.locator(".result-count")).not.toContainText("Updating");
  const newest = await page.locator(".result-count").textContent();
  const ids = await page.locator(".occurrence-list button").evaluateAll(rows => rows.map(row => row.id));
  held[0].release();
  await held[0].done;
  await page.waitForTimeout(300);
  expect(await page.locator(".result-count").textContent()).toBe(newest);
  expect(await page.locator(".occurrence-list button").evaluateAll(rows => rows.map(row => row.id))).toEqual(ids);
  expect(new URL(page.url()).searchParams.get("selected")).toBe(selected);
  await expect(page.locator(".inspector")).toContainText("outside the current map results");
  await page.unroute(endpoint);
  await page.goBack();
  await expect(page.locator(".inspector")).toHaveCount(0);
  await page.goForward();
  await expect(page.locator(".inspector .demo-note")).toBeVisible();
});

test("a long drag previews immediately, commits once, and preserves rows until completion", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", request => { if (request.url().includes("/map/occurrences?")) requests.push(request.url()); });
  await page.goto("/explore?older_ma=8&younger_ma=2");
  await expect(page.locator(".occurrence-list button").first()).toBeVisible();
  await expect(page.locator(".result-count")).not.toContainText("Updating");
  await page.waitForTimeout(300);
  const mapImage = await page.locator(".map-canvas").screenshot();
  const oldRows = await page.locator(".occurrence-list button").evaluateAll(rows => rows.map(row => row.id));
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(endpoint, async route => {
    const response = await route.fetch();
    await gate;
    await route.fulfill({ response });
  });
  const count = requests.length;
  const oldUrl = page.url();
  const oldHistory = await page.evaluate(() => history.length);
  const handle = page.getByRole("slider", { name: "Older age bound" });
  await handle.scrollIntoViewIfNeeded();
  const box = await handle.boundingBox();
  const track = await page.locator(".time-track").boundingBox();
  if (!box || !track) throw new Error("Missing timeline");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  for (let step = 1; step <= 5; step++) {
    await page.mouse.move(box.x + box.width / 2 + track.width / 12 * step / 5, box.y + box.height / 2);
    await page.waitForTimeout(100);
  }
  await expect(handle).toHaveAttribute("aria-valuenow", "7");
  expect(page.url()).toBe(oldUrl);
  expect(requests.length).toBe(count);
  await expect(page.locator(".time-explanation")).toContainText("Previewing");
  await page.mouse.up();
  await expect.poll(() => requests.length).toBe(count + 1);
  await expect.poll(() => new URL(page.url()).searchParams.get("older_ma")).toBe("7");
  expect(await page.evaluate(() => history.length)).toBe(oldHistory + 1);
  await expect(page.locator(".result-count")).toContainText("Updating");
  expect(await page.locator(".occurrence-list button").evaluateAll(rows => rows.map(row => row.id))).toEqual(oldRows);
  expect(await page.locator(".map-canvas").screenshot()).toEqual(mapImage);
  release();
  await expect(page.locator(".result-count")).not.toContainText("Updating");
  await page.goBack();
  await expect(handle).toHaveAttribute("aria-valuenow", "8");
  await page.goForward();
  await expect(handle).toHaveAttribute("aria-valuenow", "7");
});

test("failed background queries keep usable rows, and rapid key presses settle once", async ({ page }) => {
  await page.goto("/explore?older_ma=8&younger_ma=2");
  await expect(page.locator(".occurrence-list button").first()).toBeVisible();
  await expect(page.locator(".result-count")).not.toContainText("Updating");
  const ids = await page.locator(".occurrence-list button").evaluateAll(rows => rows.map(row => row.id));
  let queries = 0;
  await page.route(endpoint, async route => { queries++; await route.fulfill({ status: 503, json: { error: { message: "Temporary outage" } } }); });
  const handle = page.getByRole("slider", { name: "Older age bound" });
  await handle.focus();
  for (let i = 0; i < 8; i++) await page.keyboard.press("ArrowRight");
  await expect(handle).toHaveAttribute("aria-valuenow", "7.92");
  await expect(page.getByRole("button", { name: "Retry data" })).toBeVisible();
  expect(queries).toBe(1);
  expect(await page.locator(".occurrence-list button").evaluateAll(rows => rows.map(row => row.id))).toEqual(ids);
  await expect(page.locator(".result-count")).toContainText("last loaded");
  await page.unroute(endpoint);
  await page.getByRole("button", { name: "Retry data" }).click();
  await expect(page.locator(".result-count")).not.toContainText("Updating");
  await expect(page.getByRole("button", { name: "Retry data" })).toHaveCount(0);
});
