import { expect, test, type Page } from "@playwright/test";
import { stubBasemap } from "./helpers";

async function holdBasemap(page: Page) {
  await stubBasemap(page);
  let release!: () => void;
  let requestedStyle!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const requested = new Promise<void>(resolve => { requestedStyle = resolve; });
  await page.route("**/styles/paleograph.json", async route => {
    requestedStyle();
    await gate;
    await route.fallback();
  });
  return { release, requested };
}

for (const width of [1440, 390]) {
  test(`late basemap initialization at ${width}px cannot rewrite a Lineage URL`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1050 });
    const style = await holdBasemap(page);
    try {
      await page.goto("/lineage?source=ufvp");
      await style.requested;
      await expect(page.getByRole("treeitem").first()).toBeVisible();
      // Resize before style arrival reproduces initial layout settling on CI.
      await page.setViewportSize({ width: width - 1, height: 1050 });
      await expect.poll(() => new URL(page.url()).searchParams.has("zoom")).toBe(true);
      const url = page.url();
      // Initial framing still shows the whole state on phones; a stable regional
      // default would hide the race by silently dropping this behavior.
      if (width < 768) expect(Number(new URL(url).searchParams.get("zoom"))).toBeLessThan(6);
      style.release();
      await expect(page.locator(".map-canvas")).toHaveAttribute("data-map-stage", "ready");
      expect(page.url()).toBe(url);
    } finally {
      style.release();
    }
  });
}

test("late basemap initialization preserves a visitor's newer zoom and scientific filters", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const style = await holdBasemap(page);
  try {
    await page.goto("/explore?source=ufvp&older_ma=12&younger_ma=2");
    await style.requested;
    await page.setViewportSize({ width: 1439, height: 1050 });
    await expect.poll(() => new URL(page.url()).searchParams.has("zoom")).toBe(true);
    const zoom = Number(new URL(page.url()).searchParams.get("zoom"));
    await page.getByRole("button", { name: "Zoom in", exact: true }).click();
    await expect.poll(() => Number(new URL(page.url()).searchParams.get("zoom"))).toBeCloseTo(zoom + 1, 2);
    const url = page.url();
    style.release();
    await expect(page.locator(".map-canvas")).toHaveAttribute("data-map-stage", "ready");
    expect(page.url()).toBe(url);
    const params = new URL(url).searchParams;
    expect(params.get("source")).toBe("ufvp");
    expect(params.get("older_ma")).toBe("12");
    expect(params.get("younger_ma")).toBe("2");
  } finally {
    style.release();
  }
});
