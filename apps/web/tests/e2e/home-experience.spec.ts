import { expect, test } from "@playwright/test";
import { apiBase, stubBasemap } from "./helpers";

test.beforeEach(async ({ page }) => stubBasemap(page));

test("a real hard refresh replays the entrance despite the previous session marker", async ({ page, context }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/");
  await expect(page.locator(".opening-scene")).toHaveAttribute("data-phase", "playing");
  await page.evaluate(() => sessionStorage.setItem("paleograph:opening:atlas-beneath:v1", "seen"));
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  await Promise.all([page.waitForEvent("domcontentloaded"), cdp.send("Page.reload", { ignoreCache: true })]);
  expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(false);
  await expect(page.locator(".opening-scene")).toHaveAttribute("data-phase", "playing", { timeout: 2500 });
  const names = await page.locator(".opening-art").evaluate(element => element.getAnimations().map(animation => (animation as CSSAnimation).animationName));
  expect(names).toContain("opening-earth-uncover");
  await expect(page.getByRole("searchbox")).toBeEditable();
});

test("late artwork gets its own visible reveal while search remains usable", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.route("**/home/atlas-beneath-*", async route => {
    await new Promise(resolve => setTimeout(resolve, 2200));
    await route.continue();
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("searchbox")).toBeEditable();
  await expect(page.locator(".opening-scene")).toHaveAttribute("data-phase", "playing", { timeout: 4000 });
  await expect(page.locator(".opening-art")).toHaveJSProperty("complete", true);
  const progress = await page.locator(".opening-art").evaluate(element => element.getAnimations().find(animation => (animation as CSSAnimation).animationName.startsWith("opening-earth-"))?.currentTime);
  expect(typeof progress).toBe("number");
  expect(progress).toBeLessThan(1000);
});

test("Home opening leaves search and destinations immediately usable and shows live source totals", async ({ page, request }) => {
  const dataset = await (await request.get(`${apiBase}/datasets/ufvp`)).json();
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Life,recorded.");
  await expect(page.getByRole("searchbox")).toBeEditable();
  await expect(page.locator("#home-title")).toHaveCSS("opacity", "1");
  await expect(page.locator(".home-search")).toHaveCSS("animation-name", "none");
  const context = page.getByRole("region", { name: "Current Florida evidence" });
  await expect(context).toContainText(dataset.current_records.toLocaleString("en-US"));
  await expect(context).toContainText(dataset.published_occurrences.toLocaleString("en-US"));
  const destinations = page.getByRole("navigation", { name: "Choose an exploration destination" });
  await expect(destinations.getByRole("link", { name: /Atlas/ })).toHaveAttribute("href", "/explore");
  await expect(destinations.getByRole("link", { name: /Catalog/ })).toHaveAttribute("href", "/explore?catalog=open");
  await expect(destinations.getByRole("link", { name: /Lineage/ })).toHaveAttribute("href", "/lineage");
  expect(await page.locator("video,audio,canvas").count()).toBe(0);
});

test("Home reduced motion keeps content immediate, focus visible and phone navigation usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  for (const selector of ["#home-title", ".opening-art", ".opening-brand-bands i", ".home-destinations"]) {
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

test("the illustration can fail without blocking entry to the working Atlas", async ({ page }) => {
  await page.route("**/home/atlas-beneath-*", route => route.abort());
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("searchbox")).toBeEditable();
  await expect(page.locator(".opening-scene")).toHaveAttribute("data-art", "fallback");
  await expect(page.locator(".opening-fallback")).toBeVisible();
  await page.getByRole("navigation", { name: "Choose an exploration destination" }).getByRole("link", { name: "Atlas", exact: true }).click();
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
});

test("the finite opening settles on return, supports replay, and stops for reduced motion", async ({ page }) => {
  await page.goto("/");
  const scene = page.locator(".opening-scene");
  await expect(scene).toHaveAttribute("data-phase", "playing");
  await expect(page.locator(".home-opening")).toHaveAttribute("data-uncovered", "true", { timeout: 2500 });
  await expect(scene).toHaveAttribute("data-phase", "playing");
  await expect(page.locator(".opening-uncover-window")).toHaveCSS("animation-name", "none");
  await expect(scene).toHaveAttribute("data-phase", "still", { timeout: 6000 });
  expect(await page.locator(".opening-world").evaluate(element => element.getAnimations({ subtree: true }).filter(animation => animation.playState === "running").length)).toBe(0);
  await page.mouse.move(1300, 400);
  await expect.poll(() => page.locator(".opening-art-depth").evaluate(element => new DOMMatrixReadOnly(getComputedStyle(element).transform).m41)).toBeGreaterThan(1);
  expect(await page.locator(".opening-art-depth").evaluate(element => Math.abs(new DOMMatrixReadOnly(getComputedStyle(element).transform).m41))).toBeLessThanOrEqual(5);
  const life = page.getByRole("button", { name: "Life", exact: true });
  await life.focus();
  expect(await life.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe("none");
  await page.keyboard.press("Space");
  await expect(life).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Atlas", exact: true }).click();
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  await page.goBack();
  await expect(scene).toHaveAttribute("data-phase", "still");
  await page.getByRole("button", { name: "Replay the opening illustration" }).click();
  await expect(scene).toHaveAttribute("data-phase", "playing");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(scene).toHaveAttribute("data-phase", "still");
  expect(await page.locator(".opening-world").evaluate(element => element.getAnimations({ subtree: true }).filter(animation => animation.playState === "running").length)).toBe(0);
  await expect(page.locator(".opening-art")).toHaveCSS("opacity", "1");
});

test("the mobile composition chooses one portrait asset and supports touch without hover", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, reducedMotion: "reduce" });
  try {
    const page = await context.newPage();
    const artwork: string[] = [];
    page.on("request", request => { if (/\/home\/atlas-beneath-/.test(request.url())) artwork.push(request.url()); });
    await page.goto("/");
    expect(await page.locator(".opening-art").evaluate(element => (element as HTMLImageElement).currentSrc)).toContain("atlas-beneath-mobile.avif");
    expect(artwork).toHaveLength(1);
    await page.getByRole("button", { name: "Life", exact: true }).tap();
    await expect(page.locator(".opening-scene")).toHaveAttribute("data-focus", "life");
    await expect(page.locator(".opening-layer-caption")).toHaveText("Life leaves an impression.");
    await expect(page.getByRole("button", { name: "Life", exact: true })).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "Evidence", exact: true }).tap();
    await expect(page.locator(".opening-layer-caption")).toContainText("A trace becomes a record.");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await page.getByRole("button", { name: "Evidence", exact: true }).boundingBox())!.height).toBeGreaterThanOrEqual(44);
  } finally {
    await context.close();
  }
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
