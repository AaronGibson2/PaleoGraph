import { expect, test } from "@playwright/test";
import { apiBase, openCatalog, stubBasemap } from "./helpers";

test.beforeEach(async ({ page }) => stubBasemap(page));

test("Catalog shell control preserves filters, map camera and history", async ({ page }) => {
  await page.goto("/explore?source=pbdb&older_ma=12&younger_ma=2&lat=29&lng=-82&zoom=8");
  const toggle = page.getByRole("button", { name: "Toggle evidence catalog", exact: true });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
  const opened = page.url();
  const context = new URL(opened).searchParams;
  for (const [key,value] of Object.entries({source:"pbdb", older_ma:"12", younger_ma:"2",lat:"29.00000",lng:"-82.00000",zoom:"8.00"})) expect(context.get(key)).toBe(value);
  await toggle.click();
  await expect(page.locator(".catalog-panel")).toBeHidden();
  await page.goBack();
  await expect(page).toHaveURL(opened);
  await expect(page.locator(".catalog-panel")).toBeVisible();
});

test("clear filters is reversible and retains the selected evidence source", async ({ page }) => {
  await page.goto("/explore?source=pbdb&catalog=open&older_ma=12&younger_ma=2");
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
  await page.getByRole("button", { name: "Clear filters", exact: true }).click();
  await expect(page.getByRole("button", { name: "Clear filters", exact: true })).toHaveCount(0);
  const params = new URL(page.url()).searchParams;
  expect(params.get("source")).toBe("pbdb");
  expect(params.has("older_ma")).toBe(false);
  await page.goBack();
  await expect(page.getByRole("button", { name: "Clear filters", exact: true })).toBeVisible();
  await expect(page.getByLabel("Evidence source", {exact:true})).toHaveValue("pbdb");
});

test("section index moves keyboard focus without changing the browse URL", async ({ page }) => {
  await page.goto("/explore?catalog=open");
  await openCatalog(page);
  await page.locator(".catalog-entry").first().click();
  const index = page.locator(".inspector").getByRole("navigation", { name: "Dossier sections" });
  await expect(index.getByRole("button", {name:"Provenance",exact:true})).toBeVisible();
  const url=page.url();
  const history=await page.evaluate(()=>window.history.length);
  await index.getByRole("button", {name:"Provenance",exact:true}).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#record-provenance h3")).toBeFocused();
  await expect(page).toHaveURL(url);
  expect(await page.evaluate(()=>window.history.length)).toBe(history);
  await page.keyboard.press("Escape");
  await expect(page.locator(".inspector")).toHaveCount(0);
  await expect(page.locator(".catalog-entry[aria-pressed=true]")).toHaveCount(0);
  await expect(page.locator(".catalog-entry").first()).toBeFocused();
});

test("PBDB provenance index opens its disclosure and retains occurrence semantics", async ({ page,request }) => {
  const response=await request.get(`${apiBase}/catalog?source=pbdb&limit=1`);
  expect(response.ok()).toBe(true);
  const item=(await response.json()).items[0];
  await page.goto(`/explore?source=pbdb&selected_kind=occurrence&selected=${item.id}`);
  const index=page.locator(".inspector").getByRole("navigation",{name:"Dossier sections"});
  await index.getByRole("button",{name:"Provenance",exact:true}).click();
  await expect(page.locator("#record-provenance")).toHaveAttribute("open","");
  await expect(page.locator("#record-provenance summary")).toBeFocused();
  await expect(page.locator(".inspector")).toContainText("No canonical PBDB specimen identity is asserted");
  await index.getByRole("button",{name:"References",exact:true}).click();
  await expect(page.locator("#record-references h3")).toBeFocused();
  await expect(page.locator("#record-references").getByRole("button",{name:"Publication evidence"})).toBeVisible();
});

test("Catalog error can be retried without losing browse context",async({page})=>{
  let failed=true;
  await page.route("**/api/v1/catalog?**",route=>failed ? route.fulfill({status:503,json:{error:{message:"Temporary catalog failure"}}}) : route.continue());
  await page.goto("/explore?catalog=open&source=pbdb");
  await expect(page.locator(".continuity-note")).toContainText("Temporary catalog failure");
  failed=false;
  const url=page.url();
  await page.getByRole("button",{name:"Retry catalog",exact:true}).click();
  await expect(page.locator(".catalog-entry").first()).toBeVisible();
  await expect(page).toHaveURL(url);
});

for(const width of [1440,1280,820,390]) {
  test(`dense browsing remains usable at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:width===390?844:900});
    await page.goto("/explore?catalog=open");
    await openCatalog(page);
    const list=await page.locator(".catalog-list").boundingBox();
    expect(list!.height).toBeGreaterThan(125);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.locator(".catalog-entry").first().click();
    await expect(page.locator(".inspector")).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    if(width===390) {
      await expect(page.locator(".catalog-panel")).toBeHidden();
      await page.getByRole("button",{name:"Close occurrence inspection",exact:true}).click();
      await expect(page.locator(".catalog-panel")).toBeVisible();
    }
  });
}
