import { expect, type Page } from "@playwright/test";
export const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8001/api/v1";
export const placeEndpoint = "**/api/v1/map/places?**";
export async function stubBasemap(page: Page) {
 await page.route("**/styles/paleograph.json", route => route.fulfill({ json: { version: 8, glyphs: "http://localhost:3001/test-glyphs/{fontstack}/{range}.pbf", sources: { credit: { type:"geojson", data:{type:"FeatureCollection",features:[]}, attribution:"OpenFreeMap / OpenMapTiles / OpenStreetMap contributors" } }, layers:[{id:"background",type:"background",paint:{"background-color":"#86aaa1"}},{id:"credit",type:"circle",source:"credit"}] } }));
 await page.route("**/test-glyphs/**", route => route.fulfill({ body: Buffer.alloc(0), contentType:"application/x-protobuf" }));
}
export async function openCatalog(page: Page) {
 const toggle = page.getByRole("button", {name:"Museum catalog",exact:false}).first();
 if (await toggle.getAttribute("aria-expanded") !== "true") await toggle.click();
 await expect(page.locator(".catalog-entry").first()).toBeVisible();
 await expect(page.locator(".result-count")).not.toContainText("Updating");
}
export async function pan(page: Page, fraction: number) {
 const box = await page.locator(".maplibregl-canvas").boundingBox();
 if (!box) throw new Error("Missing canvas");
 const x = box.x + box.width*.45, y = box.y + box.height*.6;
 await page.mouse.move(x,y); await page.mouse.down();
 await page.mouse.move(x+box.width*fraction,y,{steps:12});
 await page.waitForTimeout(150); await page.mouse.up();
}
