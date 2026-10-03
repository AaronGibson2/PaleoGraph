import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import { openCatalog, placeEndpoint, stubBasemap, pan } from "./helpers";
test.beforeEach(async({page})=>stubBasemap(page));

test("small pans reuse map coverage and rapid larger pans reject late data",async({page})=>{
 const requests:string[]=[]; page.on("request",r=>{if(r.url().includes("/map/places?"))requests.push(r.url());});
 await page.goto("/explore"); await openCatalog(page); await page.waitForTimeout(400);
 const before=requests.length; await pan(page,-.02); await page.waitForTimeout(700); expect(requests.length).toBe(before);
 const held:{release:()=>void;done:Promise<void>}[]=[];
 await page.route(placeEndpoint,async route=>{
  const response=await route.fetch(); let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  const done=gate.then(async()=>{await route.fulfill({response}).catch(()=>{});}); held.push({release,done}); await done;
 });
 const canvas=await page.locator(".maplibregl-canvas").elementHandle();
 await pan(page,.4); await expect.poll(()=>held.length).toBe(1);
 await expect(page.locator(".map-status")).toContainText("last loaded");
 expect(await canvas?.evaluate(e=>e.isConnected)).toBe(true);
 await pan(page,.4); await expect.poll(()=>held.length).toBe(2);
 held[1].release(); await held[1].done; await expect(page.locator(".map-status")).toHaveCount(0);
 const image=createHash("sha256").update(await page.screenshot({clip:{x:650,y:375,width:140,height:140}})).digest("hex"); held[0].release(); await held[0].done;
 await page.waitForTimeout(300); expect(createHash("sha256").update(await page.screenshot({clip:{x:650,y:375,width:140,height:140}})).digest("hex")).toEqual(image);
});

test("long timeline drag previews, commits once and retains rows and map until completion",async({page})=>{
 const requests:string[]=[]; page.on("request",r=>{if(r.url().includes("/map/places?"))requests.push(r.url());});
 await page.goto("/explore?older_ma=12&younger_ma=2&lat=29.36&lng=-82.19&zoom=12"); await openCatalog(page); await page.waitForTimeout(350);
 const oldRows=await page.locator(".catalog-entry").evaluateAll(rows=>rows.map(e=>e.id));
 const image=createHash("sha256").update(await page.screenshot({clip:{x:650,y:375,width:140,height:140}})).digest("hex");
 let release!:()=>void; const gate=new Promise<void>(resolve=>{release=resolve;});
 await page.route(placeEndpoint,async route=>{const response=await route.fetch();await gate;await route.fulfill({response});});
 await page.route("**/api/v1/catalog?**",async route=>{const response=await route.fetch();await gate;await route.fulfill({response});});
 const count=requests.length, url=page.url(), history=await page.evaluate(()=>window.history.length);
 const handle=page.getByRole("slider",{name:"Older age bound"}); const box=await handle.boundingBox(); const track=await page.locator(".time-track").boundingBox();
 if(!box||!track)throw new Error("Missing timeline");
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
 await page.mouse.move(box.x+box.width/2+track.width/66,box.y+box.height/2,{steps:5});await page.waitForTimeout(550);
 await expect(handle).toHaveAttribute("aria-valuenow","11"); expect(page.url()).toBe(url);expect(requests.length).toBe(count);
 await expect(page.locator(".time-explanation")).toContainText("Previewing");await page.mouse.up();
 await expect.poll(()=>requests.length).toBe(count+1); expect(await page.evaluate(()=>window.history.length)).toBe(history+1);
 await expect(page.locator(".result-count")).toContainText("Updating");
 expect(await page.locator(".catalog-entry").evaluateAll(rows=>rows.map(e=>e.id))).toEqual(oldRows);
 expect(createHash("sha256").update(await page.screenshot({clip:{x:650,y:375,width:140,height:140}})).digest("hex")).toEqual(image);release();
 await expect(page.locator(".result-count")).not.toContainText("Updating");
 await page.goBack();await expect(handle).toHaveAttribute("aria-valuenow","12");await page.goForward();await expect(handle).toHaveAttribute("aria-valuenow","11");
});

test("failed background queries retain data and rapid keyboard changes settle once",async({page})=>{
 await page.goto("/explore?older_ma=12&younger_ma=2&lat=29.36&lng=-82.19&zoom=12");await openCatalog(page);
 const ids=await page.locator(".catalog-entry").evaluateAll(rows=>rows.map(e=>e.id));let queries=0;
 await page.route("**/api/v1/catalog?**",route=>route.fulfill({status:503,json:{error:{message:"Temporary outage"}}}));
 await page.route(placeEndpoint,route=>{queries++;return route.fulfill({status:503,json:{error:{message:"Temporary outage"}}});});
 const handle=page.getByRole("slider",{name:"Older age bound"});await handle.focus();for(let i=0;i<8;i++)await page.keyboard.press("ArrowRight");
 await expect(handle).toHaveAttribute("aria-valuenow","11.92");await expect(page.getByRole("button",{name:"Retry data"})).toBeVisible();expect(queries).toBe(1);
 expect(await page.locator(".catalog-entry").evaluateAll(rows=>rows.map(e=>e.id))).toEqual(ids);
 expect(await page.locator(".maplibregl-canvas").count()).toBe(1);expect(ids.length).toBeGreaterThan(0);
 await page.unroute(placeEndpoint);await page.getByRole("button",{name:"Retry data"}).click();await expect(page.getByRole("button",{name:"Retry data"})).toHaveCount(0);
});
