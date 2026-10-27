import { expect, test } from "@playwright/test";
import { apiBase, stubBasemap } from "./helpers";

test.beforeEach(async ({ page }) => stubBasemap(page));

test("Home entrance leaves search usable and shows live source totals", async ({ page, request }) => {
  const dataset = await (await request.get(`${apiBase}/datasets/ufvp`)).json();
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Life,recorded.");
  await expect(page.getByRole("searchbox")).toBeEditable();
  const entrance = await page.locator("#home-title").evaluate(element => ({ name: getComputedStyle(element).animationName, duration: parseFloat(getComputedStyle(element).animationDuration) }));
  expect(entrance.name).toBe("home-reveal");
  expect(entrance.duration).toBeGreaterThanOrEqual(.45);
  expect(entrance.duration).toBeLessThanOrEqual(.7);
  const context = page.getByRole("region", { name: "Current Florida evidence" });
  await expect(context).toContainText(dataset.current_records.toLocaleString("en-US"));
  await expect(context).toContainText(dataset.published_occurrences.toLocaleString("en-US"));
  const destinations = page.getByRole("navigation", { name: "Choose an exploration destination" });
  await expect(destinations.getByRole("link", { name: /Atlas/ })).toHaveAttribute("href", "/explore");
  await expect(destinations.getByRole("link", { name: /Catalog/ })).toHaveAttribute("href", "/explore?catalog=open");
  await expect(destinations.getByRole("link", { name: /Lineage/ })).toHaveAttribute("href", "/lineage");
  expect(await page.locator("video,canvas").count()).toBe(0);
});

test("Home reduced motion keeps content immediate, focus visible and phone navigation usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  for (const selector of ["#home-title", ".home-specimen-silhouette", ".home-strata i", ".home-destinations"]) {
    const styles = await page.locator(selector).first().evaluate(element => ({ animation: getComputedStyle(element).animationName, opacity: getComputedStyle(element).opacity }));
    expect(styles).toEqual({ animation: "none", opacity: "1" });
  }
  const input = page.getByRole("searchbox");
  await input.focus();
  expect(await input.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe("none");
  expect((await page.getByRole("button", { name: "Search the archive" }).boundingBox())!.height).toBeGreaterThanOrEqual(44);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Lineage", exact: true }).click();
  await expect(page.getByRole("treeitem").first()).toBeVisible();
  await page.goBack();
  await expect(input).toBeVisible();
  await page.goForward();
  await expect(page.getByRole("treeitem").first()).toBeVisible();
});

test("Home search opens source search results with a shareable query", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("searchbox").fill("TEST-000");
  await page.getByRole("button", { name: "Search the archive" }).click();
  await expect(page.locator("#search-results [role=option]").first()).toContainText("TEST-000");
  expect(new URL(page.url()).searchParams.get("q")).toBe("TEST-000");
  expect(new URL(page.url()).searchParams.get("source")).toBe("all");
  await page.reload();
  await expect(page.locator("#search-results [role=option]").first()).toContainText("TEST-000");
  await page.getByRole("combobox", { name: /Search material/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#inspection-heading")).toContainText("TEST-000");
});

test("Home remains navigable when live source totals are unavailable", async ({ page }) => {
  await page.route("**/api/v1/datasets/ufvp", route => route.fulfill({ status: 503, json: {} }));
  await page.goto("/");
  await expect(page.locator(".home-context-note")).toContainText("Live totals unavailable");
  await expect(page.getByRole("searchbox")).toBeEditable();
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Atlas", exact: true }).click();
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
});

test("Home editorial studies offer keyboard navigation, source search and a creator credit", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /There is more beneath the surface/ }).click();
  await expect(page.getByRole("heading", { name: "A past worth looking into." })).toBeInViewport();
  await expect(page.getByRole("link", { name: "Explore proboscideans in the evidence archive" })).toHaveAttribute("href", "/explore?source=all&q=Proboscidea");
  await expect(page.getByRole("link", { name: "Explore crocodilians in the evidence archive" })).toHaveAttribute("href", "/explore?source=all&q=Crocodylia");
  await expect(page.getByRole("link", { name: /Aaron Gibson/ })).toHaveAttribute("href", "https://github.com/AaronGibson2");
  const place = page.getByRole("tab", { name: /Place/ });
  await place.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: /Material/ })).toBeFocused();
  await expect(page.getByRole("tabpanel")).toContainText("Get closer to the record.");
  await expect(page.getByRole("tabpanel").getByRole("link")).toHaveAttribute("href", "/explore?catalog=open&source=all");
  await page.keyboard.press("End");
  await expect(page.getByRole("tab", { name: /Lineage/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel")).toContainText("Follow another branch.");
  await page.keyboard.press("Home");
  await expect(place).toBeFocused();
  await expect(page.getByRole("tabpanel")).toContainText("Begin with a landscape.");
  await page.keyboard.press("ArrowLeft");
  await page.getByRole("tabpanel").getByRole("link", { name: /Explore Lineage/ }).click();
  await expect(page.getByRole("treeitem").first()).toBeVisible();
});

test("Home extended sections stay readable on phones and stop motion when preferences change", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.locator(".home-collection").scrollIntoViewIfNeeded();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect.poll(() => page.locator(".home-experience").evaluate(element => element.getAnimations({ subtree: true }).filter(animation => animation.playState === "running").length)).toBe(0);
  for (const selector of [".home-cabinet", ".home-pathways", ".home-principles", ".home-maker"]) {
    await page.locator(selector).scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.getByRole("tab", { name: /Material/ }).click();
  expect(await page.locator(".home-study-content").evaluate(element => getComputedStyle(element).animationName)).toBe("none");
  expect((await page.getByRole("tab", { name: /Material/ }).boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await expect(page.getByRole("tabpanel")).toContainText("Get closer to the record.");
});

test("Home story and primary exploration remain available without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  try {
    const page = await context.newPage();
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /For the curious\.\s*For the record\./ })).toBeVisible();
    await expect(page.getByRole("link", { name: /Aaron Gibson/ })).toBeVisible();
    await expect(page.getByRole("searchbox")).toBeEditable();
    await expect(page.getByRole("link", { name: /Begin exploring/ })).toHaveAttribute("href", "/explore");
    await expect(page.locator("[data-home-reveal]").first()).toHaveCSS("opacity", "1");
  } finally {
    await context.close();
  }
});
