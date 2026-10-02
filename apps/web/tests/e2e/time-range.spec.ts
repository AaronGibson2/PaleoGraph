import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/styles/paleograph.json", route => route.fulfill({ json: { version: 8, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#94b5af" } }] } }));
  await page.route("https://tiles.openfreemap.org/**", route => route.fulfill({
    json: { version: 8, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#dfe7e3" } }] },
  }));
});

test("shared timeline keyboard direction, constraints, presets, URL and all ages", async ({ page }) => {
  await page.goto("/explore?data_mode=demo");
  const older = page.getByRole("slider", { name: "Older age bound" });
  const younger = page.getByRole("slider", { name: "Younger age bound" });
  await page.getByRole("button", { name: "5–2 Ma", exact: true }).click();
  await expect(older).toHaveAttribute("aria-valuenow", "5");
  await expect(younger).toHaveAttribute("aria-valuenow", "2");
  await older.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(older).toHaveAttribute("aria-valuenow", "5.01");
  await page.keyboard.press("Shift+ArrowRight");
  await expect(older).toHaveAttribute("aria-valuenow", "4.91");
  await younger.focus();
  await page.keyboard.press("ArrowRight");
  await expect(younger).toHaveAttribute("aria-valuenow", "1.99");
  await expect(page.locator("#time-heading")).toHaveText("4.91–1.99 Ma");
  await expect(page.locator(".time-window[aria-pressed=true]")).toHaveCount(0);
  await expect.poll(() => new URL(page.url()).searchParams.get("older_ma")).toBe("4.91");
  await page.reload();
  await expect(older).toHaveAttribute("aria-valuenow", "4.91");
  await younger.focus();
  await page.keyboard.press("End");
  await page.keyboard.press("ArrowLeft");
  await expect(younger).toHaveAttribute("aria-valuenow", "4.91");
  await expect(older).toHaveAttribute("aria-valuemin", "4.91");
  await older.focus();
  await page.keyboard.press("Home");
  await page.keyboard.press("ArrowRight");
  await expect(older).toHaveAttribute("aria-valuenow", "4.91");
  await page.getByRole("button", { name: "All ages", exact: true }).click();
  expect(new URL(page.url()).searchParams.has("older_ma")).toBe(false);
  expect(new URL(page.url()).searchParams.has("younger_ma")).toBe(false);
  await expect(page.locator("#time-heading")).toHaveText("All ages");
});

test("both handles drag on the same track and send custom ranges to the API", async ({ page }) => {
  await page.goto("/explore?data_mode=demo&older_ma=8&younger_ma=2");
  const older = page.getByRole("slider", { name: "Older age bound" });
  const younger = page.getByRole("slider", { name: "Younger age bound" });
  await older.scrollIntoViewIfNeeded();
  const track = await page.locator(".time-track").boundingBox();
  expect(track).not.toBeNull();
  if (!track) throw new Error("Missing timeline");
  for (const [handle, delta, expected] of [[older, track.width / 12, "7"], [younger, -track.width / 12, "3"]] as const) {
    await handle.scrollIntoViewIfNeeded();
    const box = await handle.boundingBox();
    if (!box) throw new Error("Missing range handle");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + delta, box.y + box.height / 2, { steps: 8 });
    await page.mouse.up();
    await expect(handle).toHaveAttribute("aria-valuenow", expected);
  }
  await expect(page.locator("#time-heading")).toHaveText("7–3 Ma");
  const query = page.waitForResponse(response => response.url().includes("/map/occurrences?") && new URL(response.url()).searchParams.get("younger_ma") === "2.99");
  await younger.press("ArrowRight");
  expect((await query).ok()).toBe(true);
  const band = await page.locator(".time-selection").boundingBox();
  expect(band?.width).toBeCloseTo(track.width * (7 - 2.99) / 12, 0);
});

test("narrow intervals keep both handles accessible on mobile with reduced motion", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/explore?data_mode=demo");
  await page.getByRole("button", { name: "0.1–0 Ma", exact: true }).click();
  const older = page.getByRole("slider", { name: "Older age bound" });
  const younger = page.getByRole("slider", { name: "Younger age bound" });
  await older.focus();
  await page.keyboard.press("ArrowRight");
  await expect(older).toHaveAttribute("aria-valuenow", "0.09");
  await page.keyboard.press("Tab");
  await expect(younger).toBeFocused();
  await page.keyboard.press("ArrowLeft");
  await expect(younger).toHaveAttribute("aria-valuenow", "0.01");
  const labels = page.locator(".time-handle-label");
  const a = await labels.nth(0).boundingBox();
  const b = await labels.nth(1).boundingBox();
  expect(a && b && a.y + a.height < b.y).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.locator(".time-footnote")).toContainText("not a formal geological timescale");
});
