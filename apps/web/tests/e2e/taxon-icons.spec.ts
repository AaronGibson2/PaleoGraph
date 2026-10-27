import { expect, test } from "@playwright/test";
import { stubBasemap } from "./helpers";

test.beforeEach(async ({ page }) => stubBasemap(page));

test("specific, broad-group and unassigned icons remain visible on desktop and phones", async ({ page }) => {
  let path = ["pbdb:txn:42984"];
  await page.route("**/api/v1/taxonomy/roots?**", async route => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.items[0] = { ...payload.items[0], name: "Visual coverage check", rank: null, placement: "qualified", classification_path_ids: path };
    await route.fulfill({ response, json: payload });
  });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [ids, attribute, value] of [
      [["pbdb:txn:42984"], "data-archetype", "horse"],
      [["pbdb:txn:36319"], "data-generic", "amphibian"],
      [["unknown-source-membership"], "data-visual-kind", "neutral"],
    ] as const) {
      path = [...ids];
      await page.goto("/lineage");
      const row = page.getByRole("treeitem").filter({ hasText: "Visual coverage check" });
      const icon = row.locator(".taxon-visual");
      await expect(icon).toBeVisible();
      await expect(icon).toHaveAttribute(attribute, value);
      await expect(icon).toHaveAttribute("aria-hidden", "true");
      expect(Math.round((await icon.boundingBox())!.width * 100) / 100).toBeGreaterThanOrEqual(24);
      expect((await row.boundingBox())!.height).toBeCloseTo(58, 3);
      // Qualification text stays in its row when the phone icon reserves space.
      expect((await row.locator(".taxonomy-name small").boundingBox())!.height).toBeLessThanOrEqual(15);
      await expect(row.locator(".taxonomy-name small")).toContainText("qualified");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
  }
});

test("failed icon assets keep a visible classification glyph and usable row", async ({ page }) => {
  await page.route("**/taxonomy/silhouettes/horse.svg", route => route.abort());
  await page.route("**/api/v1/taxonomy/roots?**", async route => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.items[0] = { ...payload.items[0], classification_path_ids: ["pbdb:txn:42984"] };
    await route.fulfill({ response, json: payload });
  });
  await page.goto("/lineage");
  const row = page.getByRole("treeitem").first();
  const icon = row.locator(".taxon-visual");
  await expect(icon).toHaveAttribute("data-asset-status", "failed");
  await expect(icon).toHaveAttribute("data-visual-kind", "neutral");
  await expect(icon.locator("svg path")).toHaveAttribute("d", /^M.+/);
  await expect(icon).toBeVisible();
  await row.focus();
  await expect(row).toBeFocused();
  expect(await row.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe("none");
});
