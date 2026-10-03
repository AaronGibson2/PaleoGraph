import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { apiBase, openCatalog, stubBasemap } from "./helpers";
const fixture=JSON.parse(readFileSync(new URL("../../../api/tests/fixtures/ufvp/records.json",import.meta.url),"utf8"))[0];
function stable(kind:string){const b=createHash("sha256").update(`ufvp:2fba9985-ac30-46cb-99bf-91ccde0d8d2f:${kind}:${fixture.id}`).digest().subarray(0,16);b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;const h=b.toString("hex");return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;}
test.beforeEach(async({page})=>stubBasemap(page));

test("UFVP inspector separates source geology, derived interpretation, identifiers, rights and research",async({page,request})=>{
 const response=await request.get(`${apiBase}/map/occurrences?west=-88&south=24&east=-79&north=32`);expect(response.ok()).toBe(true);expect((await response.json()).items.every((item:{is_synthetic:boolean})=>!item.is_synthetic)).toBe(true);
 await page.goto(`/explore?selected_kind=specimen&selected=${stable("specimen")}`);
 await expect(page.locator("#inspection-heading")).toContainText(fixture.catalogNumber);
 await expect(page.locator(".inspector-subtitle")).toHaveText(fixture.scientificName);
 await expect(page.locator(".source-values")).toContainText(fixture.earliestEpochOrLowestSeries);
 await expect(page.locator(".interpretation")).toContainText("0.129\u20130.0117 Ma");
 await expect(page.locator(".specimen-identifiers")).toContainText(fixture.occurrenceID);
 await expect(page.locator(".provenance")).toContainText("by-nc/4.0");
 await expect(page.locator(".research-evidence")).toContainText("No bibliographic references");
 await expect(page.getByText("Synthetic demo data")).toHaveCount(0);
});

test("museum marker and catalog inspector fit a 390px viewport with visible attribution",async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:"reduce"});await page.goto(`/explore?lat=${fixture.decimalLatitude}&lng=${fixture.decimalLongitude}&zoom=12`);
 const canvas=page.locator(".maplibregl-canvas");await expect(async()=>{await canvas.click();await expect(page.locator(".catalog-panel")).toBeVisible({timeout:500});}).toPass();
 await openCatalog(page);await page.locator(".catalog-entry").first().click();await expect(page.locator("#inspection-heading")).toBeFocused();
 await expect(page.locator(".maplibregl-ctrl-attrib")).toBeVisible();
 expect(await page.evaluate(()=>document.querySelector(".maplibregl-ctrl-attrib")!.getBoundingClientRect().top>=document.querySelector(".inspector")!.getBoundingClientRect().bottom)).toBe(true);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
