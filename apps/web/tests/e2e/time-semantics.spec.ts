import { expect, test } from "@playwright/test";
import { apiBase, stubBasemap } from "./helpers";

type Material = { id: string; specimen_id: string; taxon_id: string; locality_id: string;
  age_basis: string; source_age_label: string | null; longitude: number | null; latitude: number | null };

test.beforeEach(async ({ page }) => stubBasemap(page));

test("scientific revision refreshes the timescale configuration alongside material caches", async ({ page }) => {
  let changed = false;
  let referenceRequests = 0;
  await page.route("**/api/v1/datasets/ufvp", async route => {
    const response = await route.fetch();
    const data = await response.json();
    if (changed) data.browse_revision += ":test-policy-change";
    await route.fulfill({ response, json: data });
  });
  await page.route("**/api/v1/time-intervals", async route => {
    referenceRequests++;
    const response = await route.fetch();
    const data = await response.json();
    if (changed) data.attribution = "Updated reference fixture";
    await route.fulfill({ response, json: data });
  });
  await page.goto("/explore");
  await expect(page.locator(".time-footnote")).toBeVisible();
  const initial = referenceRequests;
  changed = true;
  await page.evaluate(() => {
    const original = Date.now;
    Date.now = () => original() + 61_000;
    window.dispatchEvent(new Event("focus"));
  });
  await expect.poll(() => referenceRequests).toBeGreaterThan(initial);
  await expect(page.locator(".time-footnote a").first()).toHaveAttribute("title", "Updated reference fixture");
});

test("source wording, reference provenance, and unresolved label evidence remain distinct", async ({ page, request }) => {
  const response = await request.get(`${apiBase}/catalog?limit=100`);
  expect(response.ok()).toBe(true);
  const material: Material[] = (await response.json()).items;
  const derived = material.find(item => item.age_basis === "derived-interval")!;
  const unresolved = material.find(item => ["ambiguous", "unmapped"].includes(item.age_basis))!;
  expect(derived).toBeTruthy(); expect(unresolved).toBeTruthy();
  await page.goto(`/explore?selected_kind=specimen&selected=${derived.specimen_id}`);
  await expect(page.locator(".source-values")).toContainText(derived.source_age_label!);
  await expect(page.locator(".interpretation")).toContainText("Reference interval envelope, not a measured specimen age");
  await expect(page.locator(".interpretation")).toContainText("ufvp-geology-v1:ics-2026-06");
  await expect(page.getByText("Source numeric bounds · Ma", { exact: true })).toBeVisible();
  await page.goto(`/explore?selected_kind=specimen&selected=${unresolved.specimen_id}`);
  await expect(page.locator(".source-values")).toContainText(unresolved.source_age_label!);
  await expect(page.locator("#interpretation-heading")).toHaveText("Geological label unresolved");
  await expect(page.locator(".interpretation")).toContainText("No interval bounds derived");
  await expect(page.locator(".interpretation .scientific-link")).toHaveCount(0);
});

test("locality, Lineage and Atlas describe material coverage without inventing locality or biological ages", async ({ page, request }) => {
  const material: Material[] = (await (await request.get(`${apiBase}/catalog?limit=100`)).json()).items;
  const unresolved = material.find(item => ["ambiguous", "unmapped"].includes(item.age_basis) && item.longitude !== null)!;
  expect(unresolved).toBeTruthy();
  const summary = await (await request.get(`${apiBase}/localities/${unresolved.locality_id}`)).json();
  await page.goto(`/explore?surface=localities&locality_id=${unresolved.locality_id}&inspect=closed`);
  await expect(page.locator(".locality-time")).toContainText("Observed material envelope");
  await expect(page.locator(".locality-time")).toContainText("not source-supplied locality geology");
  await expect(page.locator(".age-coverage")).toContainText(summary.unknown_age_count.toLocaleString("en-US"));
  await page.goto(`/explore?surface=lineage&lineage_focus=${unresolved.taxon_id}&inspect=closed`);
  await expect(page.locator(".surface-introduction")).toContainText("observed temporal distribution");
  await expect(page.locator(".scientific-caveat")).toContainText("Classification ≠ phylogeny");
  await expect(page.locator(".scientific-caveat")).toContainText("no origin, extinction, or total biological range");
  const branch = await (await request.get(`${apiBase}/lineage?focus=${unresolved.taxon_id}`)).json();
  expect(branch.focal.unknown_age_count).toBeGreaterThan(0);
  // The source-identification cohort can also contain mapped material. Its outer
  // envelope must not turn the unresolved member into an interpreted specimen.
  await expect(page.locator(".lineage-focus")).toContainText("assertions");
  const params = new URLSearchParams({ at_lon: String(unresolved.longitude), at_lat: String(unresolved.latitude), inspect: "closed" });
  await page.goto(`/explore?${params}`);
  await expect(page.locator(".map-legend")).toContainText("Age unresolved");
  await expect(page.locator(".atlas-context")).toContainText("with numeric bounds");
  await expect(page.locator(".atlas-context")).toContainText("unresolved");
  await page.locator(".time-window").filter({ hasText: "Quaternary" }).click();
  await expect(page.locator(".time-explanation")).toContainText("including boundary equality");
});
