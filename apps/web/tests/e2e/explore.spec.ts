import { expect, test } from "@playwright/test";
import { apiBase, openCatalog, placeEndpoint, stubBasemap } from "./helpers";
test.beforeEach(async ({page}) => stubBasemap(page));

test("database material, inspection, geological filtering and URL restoration", async ({page}) => {
 const errors: string[]=[]; page.on("pageerror",error=>errors.push(error.message));
 await page.goto("/explore"); await openCatalog(page);
 await expect(page.locator(".maplibregl-canvas")).toBeVisible();
 expect(await page.locator(".map-canvas").evaluate(e=>e.getBoundingClientRect().height)).toBeGreaterThan(400);
 await page.locator(".catalog-entry").first().click();
 await expect(page.getByRole("heading",{name:"Sources & evidence"})).toBeVisible();
 await expect(page.locator(".interpretation")).toContainText("not a measured specimen age");
 const selected=new URL(page.url()).searchParams.get("selected");
 await page.locator(".time-window").filter({hasText:"Quaternary"}).click();
 expect(new URL(page.url()).searchParams.get("older_ma")).toBe("2.58");
 await page.reload();
 await expect(page.locator(".inspector")).toBeVisible();
 await expect(page.locator(".time-window[aria-pressed=true]")).toContainText("Quaternary");
 expect(new URL(page.url()).searchParams.get("selected")).toBe(selected);
 expect(errors).toEqual([]);
});

test("empty view and recoverable API failure", async ({page}) => {
 await page.goto("/explore?lat=0&lng=0&zoom=7");
 await page.getByRole("button",{name:"Museum catalog",exact:false}).first().click();
 await expect(page.getByText("No material matches this view and context.",{exact:false})).toBeVisible();
 await page.route(placeEndpoint,route=>route.fulfill({status:503,json:{error:{message:"Temporary outage"}}}));
 await page.getByRole("button",{name:"Return to Florida"}).click();
 await expect(page.getByRole("button",{name:"Retry data"})).toBeVisible();
 await page.unroute(placeEndpoint); await page.getByRole("button",{name:"Retry data"}).click();
 await expect(page.getByRole("button",{name:"Retry data"})).toHaveCount(0);
 await expect(page.locator(".catalog-entry").first()).toBeVisible();
});

test("mobile keyboard inspection and focus restoration", async ({page}) => {
 await page.setViewportSize({width:390,height:844}); await page.goto("/explore"); await openCatalog(page);
 const first=page.locator(".catalog-entry").first(); await first.focus(); await page.keyboard.press("Enter");
 await expect(page.locator("#inspection-heading")).toBeFocused(); await page.keyboard.press("Escape");
 await expect(page.locator(".inspector")).toHaveCount(0); await expect(first).toBeFocused();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("rendered dense marker opens every co-located record and history restores context", async ({page,request}) => {
 const response=await request.get(`${apiBase}/map/places?at_lon=-82.19&at_lat=29.36`);
 expect(response.ok()).toBe(true); expect((await response.json()).items[0].record_count).toBe(73);
 await page.goto("/explore?lat=29.36&lng=-82.19&zoom=12");
 const canvas=page.locator(".maplibregl-canvas");
 await expect(async()=>{await canvas.click();await expect(page.locator(".catalog-panel")).toBeVisible({timeout:500});}).toPass();
 await expect(page.locator(".result-count")).toHaveText("73 assertions");
 expect(new URL(page.url()).searchParams.get("at_lon")).toBe("-82.19");
 await page.locator(".catalog-entry").first().click(); await expect(page.locator(".provenance")).toBeVisible();
 const selected=new URL(page.url()).searchParams.get("selected");
 await page.goBack(); await expect(page.locator(".inspector")).toHaveCount(0);
 await page.goForward(); await expect(page.locator(".provenance")).toBeVisible();
 expect(new URL(page.url()).searchParams.get("selected")).toBe(selected);
});
