import { expect, test } from "@playwright/test";
import { apiBase, stubBasemap } from "./helpers";

test.beforeEach(async ({ page }) => stubBasemap(page));

for (const width of [1440, 390]) {
  test(`record overview at ${width}px leads with identification and useful context`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    const sample = await (await request.get(`${apiBase}/catalog?source=ufvp&limit=100`)).json();
    const item = sample.items.find((item: { locality_id: string | null }) => item.locality_id);
    expect(item).toBeTruthy();
    await page.goto(`/explore?selected_kind=specimen&selected=${item.specimen_id}`);
    const inspector = page.locator(".inspector");
    await expect(inspector.locator("#inspection-heading")).toHaveText(item.scientific_name);
    await expect(inspector.locator(".record-accession strong")).toHaveText(item.label);
    await expect(inspector.locator(".record-overview")).toContainText(item.locality_name);
    await expect(inspector.locator(".record-actions").getByRole("button", { name: "View classification" })).toBeVisible();
    await expect(inspector.locator(".specimen-placeholder")).toHaveCount(0);
    await expect(inspector.locator(".entity-stat")).toHaveCount(0);
    const facts = (await inspector.locator(".record-facts").boundingBox())!;
    const drawer = (await inspector.boundingBox())!;
    expect(facts.y).toBeGreaterThanOrEqual(drawer.y);
    expect(facts.y + facts.height).toBeLessThanOrEqual(drawer.y + drawer.height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  });
}

test("record actions navigate its own locality and classification while preserving time and source", async ({ page, request }) => {
  const sample = await (await request.get(`${apiBase}/catalog?source=ufvp&limit=100`)).json();
  const item = sample.items.find((item: { locality_id: string | null; older_ma: number | null }) => item.locality_id && item.older_ma !== null);
  expect(item).toBeTruthy();
  const url = `/explore?selected_kind=specimen&selected=${item.specimen_id}&older_ma=100&younger_ma=0`;
  await page.goto(url);
  await page.getByRole("group", { name: "Explore this record" }).getByRole("button", { name: "Explore locality", exact: true }).click();
  await expect(page.locator(".locality-counts")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("locality_id")).toBe(item.locality_id);
  expect(new URL(page.url()).searchParams.get("older_ma")).toBe("100");
  await page.goBack();
  await expect(page.locator("#inspection-heading")).toHaveText(item.scientific_name);
  await page.getByRole("group", { name: "Explore this record" }).getByRole("button", { name: "View classification" }).click();
  const resolved = await (await request.get(`${apiBase}/taxonomy/nodes/${item.taxon_id}`)).json();
  await expect.poll(() => new URL(page.url()).searchParams.get("taxonomy_focus")).toBe(resolved.node.id);
  expect(new URL(page.url()).searchParams.get("source")).toBe("ufvp");
  expect(new URL(page.url()).searchParams.get("older_ma")).toBe("100");
});

test("related material opens the exact taxon across the archive and Back restores the record", async ({ page, request }) => {
  const sample = await (await request.get(`${apiBase}/catalog?source=ufvp&limit=100`)).json();
  const item = sample.items.find((item: { locality_id: string | null }) => item.locality_id);
  await page.goto(`/explore?source=all&locality_id=${item.locality_id}&selected_kind=specimen&selected=${item.specimen_id}`);
  await page.getByRole("group", { name: "Explore this record" }).getByRole("button", { name: "Related material" }).click();
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
  const params = new URL(page.url()).searchParams;
  expect(params.get("source")).toBe("all");
  expect(params.get("taxon_id")).toBe(item.taxon_id);
  expect(params.get("catalog_scope")).toBe("archive");
  expect(params.has("locality_id")).toBe(false);
  expect(params.has("selected")).toBe(false);
  await page.goBack();
  await expect(page.locator("#inspection-heading")).toHaveText(item.scientific_name);
  expect(new URL(page.url()).searchParams.get("locality_id")).toBe(item.locality_id);
});

test("missing record fields produce one clear unresolved summary without invented actions", async ({ page, request }) => {
  const sample = await (await request.get(`${apiBase}/catalog?source=ufvp&limit=1`)).json();
  const item = sample.items[0];
  await page.route(`**/api/v1/entities/specimen/${item.specimen_id}`, async route => {
    const response = await route.fetch();
    const data = await response.json();
    data.related = data.related.filter((entity: { kind: string }) => entity.kind !== "locality");
    data.properties = { ...data.properties, status: "unmapped", source_label: "Miocene(?)", interval: null, older_ma: null, younger_ma: null };
    await route.fulfill({ response, json: data });
  });
  await page.route("**/api/v1/occurrences/*", async route => {
    const response = await route.fetch();
    const data = await response.json();
    Object.assign(data, { locality_id: null, locality_name: null, older_ma: null, younger_ma: null, longitude: null, latitude: null, location_is_withheld: true });
    Object.assign(data.specimen, { preparations: "default - 1", individual_count: null });
    await route.fulfill({ response, json: data });
  });
  await page.goto(`/explore?selected_kind=specimen&selected=${item.specimen_id}`);
  await expect(page.locator(".record-overview")).toContainText("Miocene(?)");
  await expect(page.locator(".record-overview")).toContainText("Numeric age unresolved");
  await expect(page.locator(".record-overview")).toContainText("Locality not supplied");
  await expect(page.getByRole("button", { name: "Explore locality", exact: true })).toHaveCount(0);
  await expect(page.locator("#record-material")).not.toContainText("default - 1");
  await expect(page.locator("#record-material")).not.toContainText("not supplied");
  await expect(page.locator("#record-material")).toContainText("Coordinates withheld");
});

test("phone published overview keeps long collection context and all actions reachable", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const sample = await (await request.get(`${apiBase}/catalog?source=pbdb&limit=1`)).json();
  const item = sample.items[0];
  await page.route(`**/api/v1/entities/occurrence/${item.id}`, async route => {
    const response = await route.fetch();
    const data = await response.json();
    data.related = data.related.map((entity: { kind: string; label: string }) => entity.kind === "locality" ? { ...entity, label: "USGS Loc. 11742 - Caloosahatchee River [Buckingham Mbr, Tamiami Fm]" } : entity);
    await route.fulfill({ response, json: data });
  });
  await page.goto(`/explore?source=pbdb&selected_kind=occurrence&selected=${item.id}`);
  await expect(page.locator(".record-overview")).toContainText("Caloosahatchee River");
  await expect(page.locator(".record-overview")).toContainText("not mapped");
  await expect(page.locator(".record-actions").getByRole("button", { name: "Related occurrences" })).toBeVisible();
  const drawer = (await page.locator(".inspector").boundingBox())!;
  const actions = (await page.locator(".record-actions").boundingBox())!;
  expect(actions.y + actions.height).toBeLessThanOrEqual(drawer.y + drawer.height);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
