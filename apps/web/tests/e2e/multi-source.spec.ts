import { expect,test } from "@playwright/test";
import { apiBase,stubBasemap } from "./helpers";

test.beforeEach(async({page})=>stubBasemap(page));

test("source selection restores URL/history and published evidence remains unmapped",async({page})=>{
 await page.goto("/explore");
 const source=page.getByRole("combobox",{name:"Evidence source"});
 await source.selectOption("all");
 await expect(page.locator(".unmapped-evidence")).toContainText("unverified datum");
 await page.getByRole("button",{name:"Browse published occurrences"}).click();
 await expect(page.locator(".result-count")).toHaveText("8 published occurrences");
 expect(new URL(page.url()).searchParams.get("source")).toBe("pbdb");
 await expect(page.locator(".catalog-entry").first()).toContainText("Published occurrence");
 await page.reload();await expect(source).toHaveValue("pbdb");
 await source.selectOption("ufvp");await page.goBack();
 await expect(source).toHaveValue("pbdb");
 await expect(page.locator(".result-count")).toHaveText("8 published occurrences");
});

test("published occurrence inspection loads explicit reference roles on demand",async({page})=>{
 let refs=0;page.on("request",request=>{if(request.url().includes("/references?"))refs++;});
 await page.goto("/explore?source=pbdb");
 const search=page.getByRole("combobox",{name:/Search material/});
 await search.fill("187885");await expect(page.locator("#search-results [role=option]").first()).toContainText("Published occurrence");
 await search.press("Enter");
 await expect(page.locator("#inspection-heading")).toContainText("187885");
 await expect(page.locator(".inspector")).toContainText("Original identification");
 await expect(page.locator(".inspector")).toContainText("datum unverified");
 expect(refs).toBe(0);
 await page.getByRole("button",{name:/Publication evidence/}).click();
 await expect(page.locator(".reference-evidence")).toContainText("identification reference");
 expect(refs).toBe(1);
 await expect(page.locator(".inspector")).not.toContainText("Same specimen");
 await page.getByRole("button",{name:"Inspect reference",exact:false}).first().click();
 await expect(page.locator(".inspector")).toContainText("PBDB reference");
 await expect(page.locator(".entity-stat")).toHaveText("PBDBSource bibliographic record");
 await expect(page.locator(".entity-stat")).not.toContainText("published occurrences");
});

test("PBDB collection context and source-scoped lineage work on mobile",async({page,request})=>{
 const pageData=await (await request.get(`${apiBase}/catalog?source=pbdb&limit=1`)).json();
 const id=pageData.items[0].locality_id;
 await page.setViewportSize({width:390,height:844});
 await page.goto(`/explore?source=pbdb&surface=localities&locality_id=${id}`);
 await expect(page.locator(".locality-counts")).toContainText("Published occurrences");
 await expect(page.locator(".locality-surface")).toContainText("PBDB collection context");
 await expect(page.locator(".locality-surface")).toContainText("datum unverified");
 await expect(page.locator(".locality-counts")).not.toContainText("Distinct specimens");
 await page.getByRole("button",{name:"Locality in Lineage",exact:false}).click();
 await expect(page.locator(".lineage-node").first()).toContainText("published occurrences");
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
