import { expect, test } from "@playwright/test";
import { openCatalog, stubBasemap } from "./helpers";

test.beforeEach(async ({ page }) => stubBasemap(page));

for (const width of [1440, 390]) {
  test(`perspective at ${width}px keeps context and one map while filters and surfaces change`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1050 });
    await page.goto("/explore?source=ufvp&older_ma=12&younger_ma=2&lat=29.36000&lng=-82.19000&zoom=12.00");
    const control = page.getByRole("button", { name: "Perspective map", exact: true });
    const map = page.locator(".map-canvas");
    await expect(control).toBeEnabled();
    await expect(map).toHaveAttribute("data-map-pitch", "0.0");
    const canvas = await page.locator(".maplibregl-canvas").elementHandle();
    const before = new URL(page.url()).searchParams;
    await control.click();
    await expect(control).toHaveAttribute("aria-pressed", "true");
    await expect(map).toHaveAttribute("data-map-pitch", "50.0");
    const after = new URL(page.url()).searchParams;
    for (const key of ["source", "older_ma", "younger_ma", "lat", "lng", "zoom"]) expect(after.get(key)).toBe(before.get(key));
    await page.getByRole("group", { name: "Quick time filters" }).getByRole("button", { name: "Pleistocene", exact: true }).click();
    await expect(map).toHaveAttribute("data-map-pitch", "50.0");
    await page.getByRole("button", { name: "Lineage", exact: true }).click();
    await expect(control).toBeHidden();
    await page.getByRole("button", { name: "Atlas", exact: true }).click();
    await expect(control).toHaveAttribute("aria-pressed", "true");
    await expect(map).toHaveAttribute("data-map-pitch", "50.0");
    expect(await canvas!.evaluate(element => element.isConnected)).toBe(true);
    expect(await page.locator(".maplibregl-canvas").count()).toBe(1);
    await control.focus();
    await page.keyboard.press("Enter");
    await expect(map).toHaveAttribute("data-map-pitch", "0.0");
    await expect(control).toBeFocused();
    await expect(control).toHaveAttribute("aria-pressed", "false");
    const box = (await control.boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(44);
    expect(box.height).toBeGreaterThanOrEqual(44);
    const zoomOut = (await page.getByRole("button", { name: "Zoom out", exact: true }).boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(zoomOut.y + zoomOut.height);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.locator(".maplibregl-ctrl-attrib")).toBeVisible();
  });
}

test("reduced motion changes perspective immediately and Return to Florida restores flat view", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/explore?lat=29.36000&lng=-82.19000&zoom=12.00");
  const control = page.getByRole("button", { name: "Perspective map", exact: true });
  await expect(control).toBeEnabled();
  await control.click();
  // No in-between animation frame when the visitor requests reduced motion.
  expect(await page.locator(".map-canvas").getAttribute("data-map-pitch")).toBe("50.0");
  await page.getByRole("button", { name: "Return to Florida", exact: true }).click();
  await expect(control).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator(".map-canvas")).toHaveAttribute("data-map-pitch", "0.0");
  await openCatalog(page);
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
});

test("rapid perspective changes settle and shared links restore a flat view", async ({ page }) => {
  await page.goto("/explore?source=ufvp&lat=29.36000&lng=-82.19000&zoom=12.00");
  const control = page.getByRole("button", { name: "Perspective map", exact: true });
  await expect(control).toBeEnabled();
  await control.click();
  await expect(control).toHaveAttribute("aria-pressed", "true");
  await control.click();
  await expect(page.locator(".map-canvas")).toHaveAttribute("data-map-pitch", "0.0");
  await control.click();
  await expect(page.locator(".map-canvas")).toHaveAttribute("data-map-pitch", "50.0");
  const before = new URL(page.url()).searchParams;
  await page.reload();
  await expect(control).toBeEnabled();
  await expect(page.locator(".map-canvas")).toHaveAttribute("data-map-pitch", "0.0");
  await expect(control).toHaveAttribute("aria-pressed", "false");
  const after = new URL(page.url()).searchParams;
  for (const key of ["source", "lat", "lng", "zoom"]) expect(after.get(key)).toBe(before.get(key));
});
