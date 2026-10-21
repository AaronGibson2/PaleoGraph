import { expect, test } from "@playwright/test";
import { stubBasemap } from "./helpers";

test.beforeEach(async ({ page }) => stubBasemap(page));

test("section navigation dismisses the archive overlay and Back restores its context", async ({ page }) => {
  await page.goto("/explore?catalog=open&source=ufvp&older_ma=12&younger_ma=2&lat=29&lng=-82&zoom=8");
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
  const archive = page.url();
  await page.getByRole("button", { name: "Lineage", exact: true }).click();
  await expect(page.locator(".catalog-panel")).toBeHidden();
  await expect(page.getByRole("treeitem").first()).toBeVisible();
  for (const [key, value] of Object.entries({ source: "ufvp", older_ma: "12", younger_ma: "2", lat: "29.00000", lng: "-82.00000", zoom: "8.00" })) expect(new URL(page.url()).searchParams.get(key)).toBe(value);
  await page.getByRole("treeitem").first().locator(".taxonomy-name").click();
  await expect(page.locator(".taxonomy-focus h3")).toBeVisible();
  await page.goBack();
  await page.goBack();
  await expect(page).toHaveURL(archive);
  await expect(page.locator(".catalog-panel")).toBeVisible();
  await page.getByRole("button", { name: "Atlas", exact: true }).click();
  await expect(page.locator(".catalog-panel")).toBeHidden();
  await expect(page.getByRole("button", { name: "Atlas", exact: true })).toHaveAttribute("aria-pressed", "true");
});

test("taxon previews preserve navigation and support hover, focus and Escape", async ({ page }) => {
  const children: string[] = [];
  page.on("request", request => { if (request.url().includes("/children?")) children.push(request.url()); });
  await page.goto("/lineage?source=ufvp");
  const row = page.getByRole("treeitem").first();
  await expect.poll(() => new URL(page.url()).searchParams.has("zoom")).toBe(true);
  const url = page.url();
  await row.hover();
  await expect(page.locator("#taxonomy-preview")).toContainText("UFVP material records");
  await page.locator("#taxonomy-preview").hover();
  await expect(page.locator("#taxonomy-preview")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator("#taxonomy-preview")).toHaveCount(0);
  await row.focus();
  await expect(row).toHaveAttribute("aria-describedby", "taxonomy-preview");
  await expect(page.locator("#taxonomy-preview")).toContainText("Observed envelope");
  await page.keyboard.press("Escape");
  await expect(page.locator("#taxonomy-preview")).toHaveCount(0);
  await expect(row).toBeFocused();
  expect(new Set(children).size).toBeLessThanOrEqual(1);
  await expect(row).toHaveAttribute("aria-expanded", "false");
  await expect(page).toHaveURL(url);
});

test("taxonomy expansion animates and preserves the 58px keyboard row contract", async ({ page }) => {
  await page.goto("/lineage?source=ufvp");
  const root = page.getByRole("treeitem").first();
  await root.focus();
  await page.keyboard.press("ArrowRight");
  const child = page.getByRole("treeitem").filter({ hasText: "Chordata" });
  await expect(child).toHaveAttribute("aria-level", "2");
  expect(await child.evaluate(element => getComputedStyle(element).animationName)).toBe("branch-arrive");
  expect((await child.boundingBox())!.height).toBe(58);
  await page.keyboard.press("ArrowDown");
  await expect(child).toBeFocused();
  await expect.poll(() => root.locator(".taxonomy-chevron svg").evaluate(element => getComputedStyle(element).transform)).toBe("matrix(0, 1, -1, 0, 0, 0)");
});

test("archive presentation preserves filters and opens an animated source dossier", async ({ page }) => {
  await page.goto("/explore?catalog=open&source=pbdb&lat=29&lng=-82&zoom=8");
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
  const url = page.url();
  await page.getByRole("group", { name: "Catalog presentation" }).getByRole("button", { name: "Records", exact: true }).click();
  await expect(page.locator(".catalog-panel")).toHaveAttribute("data-view", "records");
  await expect(page).toHaveURL(url);
  await page.locator(".catalog-entry").first().click();
  await expect(page.locator(".inspector")).toBeVisible();
  expect(await page.locator(".inspector").evaluate(element => getComputedStyle(element).animationName)).toBe("dossier-arrive");
  await expect(page.locator(".dossier-edition")).toContainText("SOURCE DOSSIER");
  await page.getByRole("button", { name: "Close occurrence inspection", exact: true }).click();
  await expect(page.locator(".catalog-panel")).toHaveAttribute("data-view", "records");
  await expect(page.locator(".catalog-entry").first()).toBeFocused();
});

for (const width of [1024, 768, 390]) {
  test(`taxon sheet at ${width}px clears expanded time and restores focus`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1050 });
    await page.goto("/lineage?source=ufvp");
    const row = page.getByRole("treeitem").first();
    await row.locator(".taxonomy-name").click();
    const sheet = page.getByRole("complementary", { name: "Taxonomy node details" });
    await expect(sheet).toHaveAttribute("data-open", "true");
    await expect(page.locator(".taxonomy-focus h3")).toHaveText("Animalia");
    await page.getByRole("button", { name: "Time details", exact: true }).click();
    await expect.poll(async () => {
      const box = await sheet.boundingBox();
      const time = await page.locator(".time-control").boundingBox();
      return Math.round(box!.y + box!.height) <= Math.round(time!.y);
    }).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("button", { name: "Close taxon dossier", exact: true }).focus();
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    await expect(row).toBeFocused();
  });
}

test("compact time disclosure preserves URL semantics and filter transitions", async ({ page }) => {
  await page.goto("/explore?catalog=open&lat=28.40000&lng=-83.00000&zoom=6.20");
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
  const url = page.url();
  await expect(page.locator(".time-windows")).toBeHidden();
  await page.getByRole("button", { name: "Time details", exact: true }).click();
  await expect(page).toHaveURL(url);
  await page.locator(".time-window").filter({ hasText: "Quaternary" }).click();
  await expect(page.locator("#time-heading")).toContainText("2.58");
  expect(new URL(page.url()).searchParams.get("older_ma")).toBe("2.58");
  expect(await page.locator(".context-assertion").first().evaluate(element => getComputedStyle(element).animationName)).toBe("context-arrive");
  await page.getByRole("button", { name: "Less detail", exact: true }).click();
  await expect(page.locator(".time-windows")).toBeHidden();
  await page.goBack();
  await expect(page.locator("#time-heading")).toHaveText("All ages");
  await expect(page.getByRole("slider", { name: "Older age bound" })).toBeVisible();
});

test("reduced motion removes tree and dossier animations and preserves visible focus", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/lineage?source=ufvp");
  const row = page.getByRole("treeitem").first();
  await row.focus();
  expect(await row.evaluate(element => getComputedStyle(element).animationName)).toBe("none");
  expect(await row.evaluate(element => getComputedStyle(element).transitionDuration)).toBe("0s");
  expect(await row.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page.locator(".taxonomy-focus h3")).toHaveText("Animalia");
  expect(await page.locator(".taxonomy-focus").evaluate(element => getComputedStyle(element).animationName)).toBe("none");
});
