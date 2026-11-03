import { expect, test } from "@playwright/test";
import { apiBase, stubBasemap } from "./helpers";

test.beforeEach(async ({ page }) => stubBasemap(page));

for (const width of [1440, 390]) {
  test(`museum dossier at ${width}px keeps technical metadata optional and source evidence reachable`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    const sample = await (await request.get(`${apiBase}/catalog?source=ufvp&limit=1`)).json();
    const item = sample.items[0];
    expect(item.specimen_id).toBeTruthy();
    await page.goto(`/explore?source=ufvp&selected_kind=specimen&selected=${item.specimen_id}`);
    const inspector = page.locator(".inspector");
    const details = inspector.locator("#record-details");
    await expect(inspector.locator("#record-material")).toBeVisible();
    await expect(details).not.toHaveAttribute("open");
    await expect(inspector.locator("#record-identifiers")).toBeHidden();
    await expect(inspector.locator("#record-provenance")).toBeHidden();
    await expect(inspector.locator("#record-references")).toBeHidden();
    expect(await inspector.innerText()).not.toContain(item.specimen_id);
    const url = page.url();
    await inspector.getByRole("navigation", { name: "Dossier sections" }).getByRole("button", { name: "Sources", exact: true }).click();
    await expect(details).toHaveAttribute("open", "");
    await expect(details.locator(":scope > summary")).toBeFocused();
    await expect(details.locator("#record-identifiers")).toContainText(item.specimen_id);
    await expect(details.locator("#record-provenance")).toContainText("by-nc/4.0");
    await expect(details.getByRole("link", { name: "Source dataset", exact: false })).toHaveAttribute("href", /^https:/);
    expect(page.url()).toBe(url);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await details.locator(":scope > summary").click();
    await expect(details.locator(".record-details-body")).toBeHidden();
    await expect(inspector.locator("#inspection-heading")).toHaveText(item.label);
  });
}
