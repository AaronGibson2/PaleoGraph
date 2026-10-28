import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { apiBase, stubBasemap } from "./helpers";

test("the production custom style loads against the declared vector schema and retains attribution", async ({page}) => {
  // Keep the actual style and layer graph, replacing only external geography transport.
  // This is a deterministic renderer check; live geographic QA is performed separately.
  const requests: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("https://tiles.openfreemap.org/planet", route => route.fulfill({json:{tilejson:"3.0.0",tiles:["https://tiles.openfreemap.org/fixture/{z}/{x}/{y}.pbf"],minzoom:0,maxzoom:14}}));
  await page.route("https://tiles.openfreemap.org/fixture/**", route => { requests.push(route.request().url()); return route.fulfill({body:Buffer.alloc(0),contentType:"application/x-protobuf"}); });
  await page.route("https://tiles.openfreemap.org/fonts/**", route => route.fulfill({body:Buffer.alloc(0),contentType:"application/x-protobuf"}));
  const styleResponse = page.waitForResponse(response => response.url().endsWith("/styles/paleograph.json"));
  await page.goto("/explore");
  const style = await (await styleResponse).json();
  expect(style).toEqual(JSON.parse(readFileSync("public/styles/paleograph.json","utf8")));
  await expect(page.locator(".map-canvas")).toHaveAttribute("data-map-stage","ready");
  expect(requests.length).toBeGreaterThan(0);
  const credits = page.locator(".maplibregl-ctrl-attrib");
  for (const name of ["OpenFreeMap","OpenMapTiles","OpenStreetMap contributors"]) await expect(credits.getByRole("link",{name,exact:false})).toHaveAttribute("href",/^https:/);
  expect(errors).toEqual([]);
});

test.describe("Atlas evidence instrument", () => {
  test.beforeEach(async ({page}) => stubBasemap(page));

  test("keyboard preview selects an exact position and opens a distinct locality dossier", async ({page,request}) => {
    await page.goto("/explore?lat=29.36&lng=-82.19&zoom=12");
    await expect(page.locator(".map-status")).toHaveCount(0);
    await page.getByRole("button",{name:/Mapped positions/}).click();
    const position = page.locator(".atlas-position-list li button").first();
    await position.focus();
    await expect(page.locator(".atlas-focus-preview")).toContainText("evidence records");
    await expect(position).toBeFocused();
    await page.keyboard.press("Enter");
    const selection = page.getByRole("complementary",{name:"Selected published position"});
    await expect(selection).toContainText("Distinct histories");
    await expect(selection.locator("h2")).toBeFocused();
    const localities = selection.locator("li button");
    const selected = new URL(page.url()).searchParams;
    const response = await request.get(`${apiBase}/localities?source=ufvp&at_lon=${selected.get("at_lon")}&at_lat=${selected.get("at_lat")}&limit=6`);
    await expect(localities).toHaveCount((await response.json()).items.length);
    const zoom = new URL(page.url()).searchParams.get("zoom");
    await localities.first().click();
    const dossier = page.getByRole("complementary",{name:"Locality dossier"});
    await expect(dossier.locator("h2")).toContainText("Fictional");
    await expect(dossier).toContainText("Locality association ≠ contemporaneous community");
    expect(new URL(page.url()).searchParams.get("zoom")).toBe(zoom);
    await dossier.getByRole("button",{name:"Time",exact:true}).click();
    await expect(dossier.locator("#locality-time h3")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dossier).toHaveCount(0);
    await expect(page.getByRole("button",{name:/Museum catalog/})).toBeFocused();
  });

  test("Back and Forward restore selected position and source-locality identity", async ({page}) => {
    await page.goto("/explore?lat=29.36&lng=-82.19&zoom=12");
    const canvas = page.locator(".maplibregl-canvas");
    await expect(async()=>{await canvas.click();await expect(page.locator(".atlas-position-selection")).toBeVisible({timeout:500});}).toPass();
    const positionURL = page.url();
    await page.locator(".atlas-position-selection li button").first().click();
    await expect(page.locator(".atlas-locality-dossier .locality-counts")).toBeVisible();
    const id = new URL(page.url()).searchParams.get("locality_id");
    await page.goBack();
    await expect(page.locator(".atlas-position-selection")).toBeVisible();
    expect(new URL(page.url()).searchParams.get("at_lon")).toBe(new URL(positionURL).searchParams.get("at_lon"));
    await page.goForward();
    await expect(page.locator(".atlas-locality-dossier")).toBeVisible();
    expect(new URL(page.url()).searchParams.get("locality_id")).toBe(id);
  });

  for (const width of [1920,1440,1280,1024,768,390]) test(`Atlas and locality sheet retain geography at ${width}px`,async({page,request})=>{
    const response = await request.get(`${apiBase}/localities?at_lon=-82.19&at_lat=29.36&limit=1`);
    const locality = (await response.json()).items[0];
    await page.setViewportSize({width,height:width === 390 ? 844 : 1000});
    await page.goto(`/explore?selected=${locality.id}&selected_kind=locality&locality_id=${locality.id}`);
    const dossier = page.locator(".atlas-locality-dossier");
    await expect(dossier.locator(".locality-counts")).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const map = await page.locator(".map-canvas").boundingBox();
    const panel = await dossier.boundingBox();
    expect(map!.height).toBeGreaterThan(300);
    if(width === 390) {
      expect(panel!.height).toBeLessThan(map!.height * .51);
      expect(panel!.y - map!.y).toBeGreaterThan(map!.height * .35);
    } else expect(map!.width - panel!.width).toBeGreaterThan(width * .25);
    const credits = await page.locator(".maplibregl-ctrl-attrib").boundingBox();
    expect(credits!.y).toBeGreaterThanOrEqual(panel!.y + panel!.height);
    await expect(dossier.getByRole("button",{name:"Close locality dossier"})).toBeVisible();
  });

  test("source and time contexts survive entry, including explicit unmapped PBDB evidence", async ({page}) => {
    await page.goto("/explore?older_ma=2.58&younger_ma=0&source=all");
    await expect(page.locator(".unmapped-evidence")).toContainText("not assigned to this viewport");
    await expect(page.locator(".time-title")).toContainText("2.58\u20130 Ma");
    await page.getByRole("combobox",{name:"Evidence source",exact:true}).selectOption("pbdb");
    await expect(page.locator(".catalog-panel")).toBeVisible();
    expect(new URL(page.url()).searchParams.get("older_ma")).toBe("2.58");
    await page.goBack();
    await expect(page.getByRole("combobox",{name:"Evidence source",exact:true})).toHaveValue("all");
  });

  test("reduced motion disables Atlas entry, drawer and tooltip animations", async ({page}) => {
    await page.emulateMedia({reducedMotion:"reduce"});
    await page.goto("/explore?at_lon=-82.19&at_lat=29.36");
    await expect(page.locator(".atlas-position-selection li").first()).toBeVisible();
    const durations = await page.locator(".map-surface,.atlas-position-selection").evaluateAll(elements=>elements.map(element=>getComputedStyle(element).animationName));
    expect(durations.every(name=>name === "none")).toBe(true);
    await page.getByRole("button",{name:"Clear selected position"}).focus();
    expect(await page.getByRole("button",{name:"Clear selected position"}).evaluate(element=>getComputedStyle(element).outlineStyle)).not.toBe("none");
    await page.keyboard.press("Escape");
    await expect(page.locator(".atlas-position-selection")).toHaveCount(0);
    await expect(page.getByRole("button",{name:/Mapped positions/})).toBeFocused();
  });
});
