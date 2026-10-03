import { expect,test } from "@playwright/test";
import { openCatalog, stubBasemap } from "./helpers";
test.beforeEach(async({page})=>stubBasemap(page));

test("global keyboard search pivots source-supported taxonomy and shares its URL",async({page})=>{
 await page.goto("/explore");const input=page.getByRole("combobox");await input.fill("Smilodon");
 await expect(page.locator("#search-results [role=option]").first()).toBeVisible();
 await expect(page.locator(".search-meta")).toContainText("matching entities");await input.press("ArrowDown");await input.press("Home");await input.press("Enter");
 await expect(page.locator(".atlas-context")).toContainText("Smilodon");expect(new URL(page.url()).searchParams.get("taxon_id")).toBeTruthy();
 await page.reload();await expect(page.locator(".atlas-context")).toContainText("Smilodon");
 await page.getByRole("button",{name:"Remove taxon context"}).click();expect(new URL(page.url()).searchParams.has("taxon_id")).toBe(false);
});

test("dense material pagination exposes totals and distinct localities",async({page})=>{
 await page.goto("/explore?at_lon=-82.19&at_lat=29.36");await openCatalog(page);
 await expect(page.locator(".result-count")).toHaveText("73 assertions");const first=await page.locator(".catalog-entry").evaluateAll(rows=>rows.map(row=>row.id));
 await page.getByRole("button",{name:"Next",exact:false}).filter({hasText:/^Next/}).click();
 await expect(page.locator(".catalog-pagination")).toContainText("31\u201360 of 73");
 const second=await page.locator(".catalog-entry").evaluateAll(rows=>rows.map(row=>row.id));expect(second.every(id=>!first.includes(id))).toBe(true);
 await page.locator(".entry-pivots button").filter({hasText:"Locality"}).first().click();
 await expect(page.locator(".atlas-context")).toContainText("Fictional automated test locality");await expect(page.locator(".entity-stat")).toContainText("catalog assertions");
});

test("specimen relationships are bounded, progressive, accessible and coordinated with context",async({page})=>{
 await page.goto("/explore");await openCatalog(page);await page.locator(".catalog-entry").first().click();
 await page.getByRole("button",{name:"Explore relationships",exact:false}).click();
 await expect(page.locator(".graph-root")).toBeVisible();expect(await page.locator(".graph-node").count()).toBeLessThanOrEqual(12);
 const expand=page.getByRole("button",{name:"Expand neighborhood",exact:false});
 if(await expand.isEnabled()) { const count=await page.locator(".graph-node").count();await expand.click();await expect.poll(()=>page.locator(".graph-node").count()).toBeGreaterThan(count);expect(await page.locator(".graph-node").count()).toBeLessThanOrEqual(24); }
 await page.getByText("Accessible relationship list",{exact:true}).click();await expect(page.locator(".graph-accessible li").first()).toBeVisible();
 const oldRoot=await page.locator(".graph-root h3").textContent();await page.locator(".graph-node").first().click();
 await expect.poll(()=>page.locator(".graph-root h3").textContent()).not.toBe(oldRoot);
 expect(new URL(page.url()).searchParams.get("surface")).toBe("relationships");
 await page.reload();await expect(page.locator(".graph-root")).toBeVisible();
});

test("large and laptop canvases use the viewport and expose authoritative time",async({page})=>{
 for(const size of [{width:1800,height:1100},{width:1366,height:900}]){
  await page.setViewportSize(size);await page.goto("/explore");await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  const box=await page.locator(".map-canvas").boundingBox();expect(box!.width).toBe(size.width);expect(box!.height).toBeGreaterThan(size.height*.55);
  await expect(page.getByText("ICS v2026/06",{exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight)).toBe(true);
 }
});

test("search opens a specimen, its geological interpretation filters, and supported higher ranks pivot",async({page})=>{
 await page.goto("/explore");const input=page.getByRole("combobox");await input.fill("TEST-000");
 await expect(page.locator("#search-results [role=option]").first()).toContainText("specimen");await input.press("Enter");
 await expect(page.locator("#inspection-heading")).toContainText("TEST-000");
 await page.locator(".interpretation .scientific-link").click();await expect(page.locator("#time-heading")).toHaveText("11.63\u20135.333 Ma");
 await page.locator(".source-values .scientific-link").filter({hasText:"Mammalia"}).click();
 await expect(page.locator(".atlas-context")).toContainText("Mammalia");await expect(page.locator("#inspection-heading")).toHaveText("Mammalia");
 await page.getByRole("button",{name:"Explore relationships",exact:false}).click();await expect(page.locator(".graph-root")).toContainText("Mammalia");
 expect(new URL(page.url()).searchParams.get("younger_ma")).toBe("5.333");
});

test("mobile keyboard search opens a locality and retains its context across map and graph",async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:"reduce"});await page.goto("/explore");
 const input=page.getByRole("combobox");await input.fill("Fictional automated test locality 0");
 await expect(page.locator("#search-results [role=option]").first()).toContainText("locality");await input.press("Enter");
 await expect(page.locator("#inspection-heading")).toHaveText("Fictional automated test locality 0");
 const id=new URL(page.url()).searchParams.get("locality_id");expect(id).toBeTruthy();
 await page.getByRole("button",{name:"Explore relationships",exact:false}).click();await expect(page.locator(".graph-root")).toContainText("Fictional automated test locality 0");
 await page.getByRole("button",{name:"Map",exact:true}).click();expect(new URL(page.url()).searchParams.get("locality_id")).toBe(id);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
