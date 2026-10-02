import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

const fixture = JSON.parse(readFileSync(new URL("../../../api/tests/fixtures/ufvp/records.json", import.meta.url), "utf8"))[0];
const bytes = createHash("sha256").update(`ufvp:2fba9985-ac30-46cb-99bf-91ccde0d8d2f:occurrence:${fixture.id}`).digest().subarray(0, 16);
bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
const hex = bytes.toString("hex");
const id = `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
const api = process.env.E2E_API_BASE_URL ?? "http://localhost:8000/api/v1";

test.beforeEach(async ({ page }) => {
  await page.route("**/styles/paleograph.json", route => route.fulfill({ json: { version: 8, sources: { attribution: { type: "geojson", data: { type: "FeatureCollection", features: [] }, attribution: "OpenFreeMap / OpenMapTiles / OpenStreetMap contributors" } }, layers: [{ id: "background", type: "background", paint: { "background-color": "#94b5af" } }, { id: "attribution-source", type: "circle", source: "attribution" }] } }));
});

test("imported UFVP fixture preserves catalog, text age, rights and museum default", async ({ page, request }) => {
  const result = await request.get(`${api}/map/occurrences?west=-88&south=24&east=-79&north=32`);
  expect(result.ok()).toBe(true);
  const body = await result.json();
  expect(body.items.length).toBeGreaterThan(0);
  expect(body.items.every((item: {is_synthetic: boolean}) => !item.is_synthetic)).toBe(true);
  await page.goto(`/explore?lat=${fixture.decimalLatitude}&lng=${fixture.decimalLongitude}&zoom=9&selected=${id}`);
  await expect(page.locator(".specimen-accession")).toContainText(fixture.collectionCode);
  await expect(page.locator("#inspection-heading")).toHaveText(fixture.scientificName);
  await expect(page.locator(".inspection-age")).toContainText(fixture.earliestEpochOrLowestSeries);
  await expect(page.locator(".source-values")).toContainText("FossilSpecimen");
  await expect(page.locator(".specimen-identifiers")).toContainText(fixture.occurrenceID);
  await expect(page.locator(".provenance")).toContainText("by-nc/4.0");
  await expect(page.locator(".demo-note")).toHaveCount(0);
  await expect(page.locator(".source-age-note")).toContainText("not numeric Ma bounds");
  await page.getByRole("button", {name:"Close occurrence inspection"}).click();
  await page.getByRole("button", {name:"5–2 Ma",exact:true}).click();
  await expect(page.locator(".result-count")).not.toContainText("Updating");
  await expect(page.locator(".occurrence-list button")).toHaveCount(0);
  await page.getByRole("button", {name:"All ages",exact:true}).click();
  await expect(page.locator(".occurrence-list button").first()).toBeVisible();
});

test("museum marker interaction and catalog layout fit a 390px viewport", async ({ page }) => {
  await page.setViewportSize({width:390,height:844});
  await page.emulateMedia({reducedMotion:"reduce"});
  await page.goto(`/explore?lat=${fixture.decimalLatitude}&lng=${fixture.decimalLongitude}&zoom=12`);
  await expect(page.locator(".occurrence-list button").first()).toBeVisible();
  const canvas = page.locator(".maplibregl-canvas");
  await expect(async () => {
    await canvas.click();
    await expect(page.locator(".map-choice").first().or(page.locator(".specimen-accession"))).toBeVisible({timeout:500});
  }).toPass();
  if (await page.locator(".map-choice").count()) await page.locator(".map-choice").first().click();
  await expect(page.locator(".specimen-accession")).toBeVisible();
  await expect(page.locator("#inspection-heading")).toBeFocused();
  await expect(page.locator(".maplibregl-ctrl-attrib")).toBeVisible();
  // Keep the provider attribution footer outside the catalog overlay.
  expect(await page.evaluate(() => {
    const inspector = document.querySelector(".inspector")!.getBoundingClientRect();
    const attribution = document.querySelector(".maplibregl-ctrl-attrib")!.getBoundingClientRect();
    return attribution.top >= inspector.bottom;
  })).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
