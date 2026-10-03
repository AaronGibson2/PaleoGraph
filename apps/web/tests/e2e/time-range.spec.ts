import { expect, test } from "@playwright/test";
import { stubBasemap } from "./helpers";
test.beforeEach(async({page})=>stubBasemap(page));

test("shared track preserves precise official selections and older-left keyboard behavior",async({page})=>{
 await page.goto("/explore?time_focus=ics:2026-06:Miocene");
 await page.getByRole("button",{name:"Late Miocene",exact:false}).filter({has:page.locator("strong")}).click();
 await expect(page.locator("#time-heading")).toHaveText("11.63\u20135.333 Ma");
 const older=page.getByRole("slider",{name:"Older age bound"}), younger=page.getByRole("slider",{name:"Younger age bound"});
 expect((await older.boundingBox())!.x).toBeLessThan((await younger.boundingBox())!.x);
 await older.focus();await page.keyboard.press("ArrowRight");await expect(older).toHaveAttribute("aria-valuenow","11.62");
 await expect.poll(()=>new URL(page.url()).searchParams.get("interval_id")).toBeNull();
 await page.getByRole("button",{name:"All ages",exact:true}).click();expect(new URL(page.url()).searchParams.has("older_ma")).toBe(false);
});

test("pointer boundaries create a custom range and do not cross",async({page})=>{
 await page.goto("/explore?older_ma=12&younger_ma=2");
 const older=page.getByRole("slider",{name:"Older age bound"}), younger=page.getByRole("slider",{name:"Younger age bound"});
 const box=await older.boundingBox(), track=await page.locator(".time-track").boundingBox();if(!box||!track)throw new Error("Missing timeline");
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+track.width/66*2,box.y+box.height/2);await page.mouse.up();
 await expect(older).toHaveAttribute("aria-valuenow","10");await younger.focus();await page.keyboard.press("End");await expect(younger).toHaveAttribute("aria-valuenow","10");
 expect(Number(new URL(page.url()).searchParams.get("older_ma"))).toBeGreaterThanOrEqual(Number(new URL(page.url()).searchParams.get("younger_ma")));
});

test("formal hierarchy semantic zoom and reduced motion work on mobile",async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:"reduce"});await page.goto("/explore");
 await page.getByRole("button",{name:"Explore subdivisions of Neogene"}).click();await expect(page.locator(".time-windows")).toContainText("Miocene");
 await page.getByRole("button",{name:"Explore subdivisions of Miocene"}).click();await expect(page.locator(".time-windows")).toContainText("Aquitanian");
 await page.reload();await expect(page.locator(".time-windows")).toContainText("Aquitanian");
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await expect(page.getByText("ICS v2026/06",{exact:true})).toBeVisible();
});
