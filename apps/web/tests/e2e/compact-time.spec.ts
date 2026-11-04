import { expect, test } from "@playwright/test";
import { apiBase, openTimeDetails, stubBasemap } from "./helpers";

test.beforeEach(async ({ page }) => stubBasemap(page));

for (const width of [1440, 390, 320]) {
  test(`compact time filters at ${width}px retain context and make room for the map`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: width === 1440 ? 1050 : 844 });
    const configuration = await (await request.get(`${apiBase}/time-intervals`)).json();
    const sample = await (await request.get(`${apiBase}/catalog?limit=1&source=ufvp`)).json();
    const context = new URLSearchParams({ source: "ufvp", taxon_id: sample.items[0].taxon_id, lat: "28.40000", lng: "-83.00000", zoom: "6.20" });
    await page.goto(`/explore?${context}`);
    const choices = page.getByRole("group", { name: "Quick time filters" });
    const allAges = choices.getByRole("button", { name: "All ages", exact: true });
    await expect(allAges).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#time-details")).toBeHidden();
    await expect(page.getByRole("slider")).toHaveCount(0);
    const compactHeight = (await page.locator(".time-control").boundingBox())!.height;
    expect(compactHeight).toBeLessThan(90);
    const canvas = await page.locator(".maplibregl-canvas").elementHandle();
    const initialUrl = page.url();
    const compactMapHeight = (await page.locator(".maplibregl-canvas").boundingBox())!.height;
    await openTimeDetails(page);
    await expect.poll(async () => (await page.locator(".maplibregl-canvas").boundingBox())!.height).toBeLessThan(compactMapHeight - 40);
    await page.getByRole("slider", { name: "Older age bound" }).focus();
    await page.keyboard.press("Escape");
    await expect(page.locator("#time-details")).toBeHidden();
    await expect(page.locator(".time-expand")).toBeFocused();
    await expect(page).toHaveURL(initialUrl);
    await expect.poll(async () => (await page.locator(".maplibregl-canvas").boundingBox())!.height).toBe(compactMapHeight);
    expect(await canvas!.evaluate(element => element.isConnected)).toBe(true);
    for (const name of ["Pleistocene", "Miocene"]) {
      const interval = configuration.units.find((unit: { name: string }) => unit.name === name);
      const button = choices.getByRole("button", { name, exact: true });
      await button.click();
      await expect(button).toHaveAttribute("aria-pressed", "true");
      await expect(allAges).toHaveAttribute("aria-pressed", "false");
      const params = new URL(page.url()).searchParams;
      expect(params.get("older_ma")).toBe(String(interval.older_ma));
      expect(params.get("younger_ma")).toBe(String(interval.younger_ma));
      expect(params.get("interval_id")).toBe(interval.id);
      for (const [key, value] of context) expect(params.get(key)).toBe(value);
      await expect(page.locator("#time-details")).toBeHidden();
    }
    await allAges.click();
    const params = new URL(page.url()).searchParams;
    for (const key of ["older_ma", "younger_ma", "interval_id"]) expect(params.has(key)).toBe(false);
    await page.goBack();
    await expect(choices.getByRole("button", { name: "Miocene", exact: true })).toHaveAttribute("aria-pressed", "true");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const button of await choices.getByRole("button").all()) {
      const box = (await button.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width);
      if (width < 768) expect(box.height).toBeGreaterThanOrEqual(44);
    }
    await expect(page.getByText("ICS v2026/06", { exact: true })).toBeVisible();
  });
}

test("shared custom ranges remain legible and compact without losing hierarchy depth", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/explore?older_ma=11.63&younger_ma=5.333&time_focus=ics%3A2026-06%3AMiocene&lat=28.40000&lng=-83.00000&zoom=6.20");
  await expect(page.locator("#time-heading")).toHaveText("11.63–5.333 Ma");
  await expect(page.locator("#time-heading")).toBeVisible();
  await expect(page.locator("#time-details")).toBeHidden();
  await expect(page.getByRole("group", { name: "Quick time filters" }).getByRole("button", { pressed: true })).toHaveCount(0);
  const url = page.url();
  await openTimeDetails(page);
  await expect(page.locator(".time-windows")).toContainText("Aquitanian");
  await expect(page.getByRole("slider", { name: "Older age bound" })).toHaveAttribute("aria-valuenow", "11.63");
  await page.getByRole("button", { name: "Less detail", exact: true }).click();
  await expect(page).toHaveURL(url);
  await page.reload();
  await expect(page.locator("#time-heading")).toBeVisible();
  await expect(page.locator("#time-details")).toBeHidden();
});
