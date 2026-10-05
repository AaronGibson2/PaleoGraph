import { expect, test } from "@playwright/test";
import { apiBase, openCatalog, stubBasemap } from "./helpers";

test("Explore and shareable URLs render on direct navigation and reload", async ({ page, request }) => {
  await stubBasemap(page);
  const home = await request.get("/");
  expect(home.status()).toBe(200);
  const material = await request.get(`${apiBase}/catalog?at_lon=-82.19&at_lat=29.36&limit=1`);
  expect(material.ok()).toBe(true);
  const item = (await material.json()).items[0];
  expect(item.locality_id).toBeTruthy();
  expect(item.specimen_id).toBeTruthy();
  const paths = [
    "/explore",
    "/explore?zoom=7.5",
    "/explore?lat=29.36&lng=-82.19&zoom=12",
    `/explore?surface=lineage&lineage_focus=${item.taxon_id}`,
    `/explore?surface=localities&locality_id=${item.locality_id}`,
    `/explore?surface=localities&locality_id=${item.locality_id}&catalog=open`,
    `/explore?surface=localities&locality_id=${item.locality_id}&catalog=open&selected_kind=specimen&selected=${item.specimen_id}`,
  ];
  for (const path of paths) {
    const response = await request.get(path, { maxRedirects: 0 });
    expect(response.status(), `${path} must exist without a redirect`).toBe(200);
    const navigation = await page.goto(path);
    expect(navigation?.status()).toBe(200);
    await expect(page.locator(".explore-workspace")).toBeVisible();
    const reload = await page.reload();
    expect(reload?.status()).toBe(200);
    await expect(page.locator(".explore-workspace")).toBeVisible();
    const expected = new URL(path, "http://route.test").searchParams;
    for (const [key, value] of expected) {
      expect(new URL(page.url()).searchParams.get(key)).toBe(value);
    }
    if (expected.get("surface") === "lineage") {
      await expect(page.locator(".lineage-surface")).toHaveAttribute("aria-busy", "false");
      await expect(page.locator(".lineage-focus")).toBeVisible();
    }
    if (expected.get("locality_id")) await expect(page.locator(".locality-counts")).toBeVisible();
    if (expected.get("selected")) await expect(page.locator(".provenance")).toBeVisible();
  }
});

test("locality, material, specimen and Lineage restore through history and refresh", async ({ page }) => {
  await stubBasemap(page);
  expect((await page.goto("/explore?lat=29.36&lng=-82.19&zoom=12"))?.status()).toBe(200);
  await openCatalog(page);
  await page.locator(".catalog-list > li").first().getByRole("button", { name: "Locality", exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("locality_id")).toBeTruthy();
  const locality = new URL(page.url()).searchParams.get("locality_id");
  await page.getByRole("button", { name: "Localities", exact: true }).click();
  await expect(page.locator(".locality-counts")).toBeVisible();
  const associated = page.getByRole("button", { name: "Associated material", exact: false });
  await expect(associated).toBeEnabled();
  await associated.click();
  await page.locator(".catalog-entry").first().click();
  await expect(page.locator(".provenance")).toBeVisible();
  const specimenURL = page.url();
  await page.getByRole("button", { name: "Lineage", exact: true }).click();
  await expect(page.locator(".lineage-surface")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator(".lineage-node").first()).toBeVisible();
  const lineageURL = page.url();
  await page.goBack();
  await expect(page).toHaveURL(specimenURL);
  await expect(page.locator(".provenance")).toBeVisible();
  await page.goForward();
  await expect(page).toHaveURL(lineageURL);
  expect((await page.reload())?.status()).toBe(200);
  await expect(page.locator(".lineage-surface")).toHaveAttribute("aria-busy", "false");
  expect(new URL(page.url()).searchParams.get("locality_id")).toBe(locality);
});
