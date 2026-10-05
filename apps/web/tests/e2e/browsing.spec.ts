import { expect, test } from "@playwright/test";
import { apiBase, openCatalog, stubBasemap } from "./helpers";

test.beforeEach(async({page})=>stubBasemap(page));

test("hover and keyboard focus prepare only the intended branch without changing URL or shell",async({page,request})=>{
  const root=(await (await request.get(`${apiBase}/lineage?limit=12`)).json()).items.find((item:{label:string})=>item.label==='Animalia');
  await page.goto('/explore?surface=lineage');
  const button=page.getByRole('button',{name:'Expand Animalia',exact:true});await expect(button).toBeEnabled();
  await expect.poll(()=>new URL(page.url()).searchParams.has('zoom')).toBe(true);
  const shell=await page.locator('.atlas-bar').elementHandle();
  const url=page.url();const historyLength=await page.evaluate(()=>window.history.length);
  let prepared=0;
  page.on('request',r=>{const u=new URL(r.url());if(u.pathname.endsWith('/lineage')&&u.searchParams.get('focus')===root.id)prepared++;});
  const response=page.waitForResponse(r=>{const u=new URL(r.url());return u.pathname.endsWith('/lineage')&&u.searchParams.get('focus')===root.id;});
  await button.hover();await response;
  expect(page.url()).toBe(url);expect(await page.evaluate(()=>window.history.length)).toBe(historyLength);expect(prepared).toBe(1);
  await button.focus();await button.press('Enter');await expect(page.locator('.surface-introduction h2')).toHaveText('Animalia');
  expect(prepared).toBe(1);expect(await shell?.evaluate(node=>node.isConnected)).toBe(true);
  await page.goBack();await expect(page.locator('.surface-introduction h2')).toHaveText('The source taxonomic hierarchy');
  const row=page.getByRole('treeitem').filter({hasText:'Animalia'});await row.focus();
  await row.press('ArrowRight');await expect(page.locator('.surface-introduction h2')).toHaveText('Animalia');expect(prepared).toBe(1);
});

test("focused material prepares detail and evidence; inspection and history preserve camera and rows",async({page})=>{
  await page.goto('/explore?lat=29.36&lng=-82.19&zoom=12');await openCatalog(page);
  const first=page.locator('.catalog-entry').first();const url=page.url();const rowIds=await page.locator('.catalog-entry').evaluateAll(rows=>rows.map(row=>row.id));
  const selection=await first.getAttribute('id');const camera=new URL(url).searchParams;
  const inspected:string[]=[];page.on('request',r=>{if(/\/entities\/specimen\/|\/occurrences\/[^?]+$/.test(r.url()))inspected.push(r.url());});
  const detail=page.waitForResponse(r=>r.url().includes('/entities/specimen/'));
  const evidence=page.waitForResponse(r=>/\/occurrences\/[^?]+$/.test(r.url()));
  await first.focus();await Promise.all([detail,evidence]);expect(page.url()).toBe(url);expect(inspected).toHaveLength(2);
  await first.press('Enter');await expect(page.locator('.provenance')).toBeVisible();
  expect(new URL(page.url()).searchParams.get('selected')).toBe(selection?.replace('result-',''));
  for(const key of ['lat','lng','zoom'])expect(new URL(page.url()).searchParams.get(key)).toBe(camera.get(key));
  await page.goBack();await expect(page.locator('.inspector')).toHaveCount(0);
  expect(await page.locator('.catalog-entry').evaluateAll(rows=>rows.map(row=>row.id))).toEqual(rowIds);
  await page.goForward();await expect(page.locator('.provenance')).toBeVisible();expect(inspected).toHaveLength(2);
  await page.reload();await expect(page.locator('.provenance')).toBeVisible();await expect(page.locator('.catalog-panel')).toBeVisible();
  for(const key of ['lat','lng','zoom'])expect(new URL(page.url()).searchParams.get(key)).toBe(camera.get(key));
});

test("keyboard search intent prepares its target without re-querying the closed search",async({page})=>{
  let searches=0;page.on('request',r=>{if(r.url().includes('/search?'))searches++;});
  await page.goto('/explore?surface=lineage');await expect(page.getByRole('treeitem').first()).toBeVisible();
  const input=page.getByRole('combobox');await input.fill('Smilodon');await expect(page.locator('#search-results [role=option]').first()).toBeVisible();
  await expect.poll(()=>new URL(page.url()).searchParams.has('zoom')).toBe(true);
  const url=page.url();const evidence=page.waitForResponse(r=>r.url().includes('/entities/'));
  await input.press('Home');await evidence;expect(page.url()).toBe(url);expect(searches).toBe(1);
  await page.clock.install();await input.press('Enter');await page.clock.fastForward(500);
  await expect(page.locator('.entity-stat')).toBeVisible();expect(searches).toBe(1);await expect(input).toHaveAttribute('aria-expanded','false');
});

test("late detail from A never replaces B or puts A evidence under B identity",async({page})=>{
  await page.goto('/explore?lat=29.36&lng=-82.19&zoom=12');await openCatalog(page);
  const rows=page.locator('.catalog-entry');const a=(await rows.nth(0).getAttribute('id'))!.replace('result-','');const b=(await rows.nth(1).getAttribute('id'))!.replace('result-','');
  const label=await rows.nth(1).locator('.catalog-label').textContent();
  let release!:()=>void;const gate=new Promise<void>(done=>{release=done;});let intercepted!:()=>void;const seen=new Promise<void>(done=>{intercepted=done;});
  await page.route(`**/api/v1/entities/specimen/${a}`,async route=>{const response=await route.fetch();intercepted();await gate;await route.fulfill({response}).catch(()=>{});});
  await rows.nth(0).click();await seen;
  // The inspector overlaps the list; the visible row is still the actual navigation target.
  await page.getByRole('button',{name:'Close occurrence inspection'}).click();await rows.nth(1).click();
  await expect(page.locator('#inspection-heading')).toHaveText(label!);await expect(page.locator('.specimen-identifiers')).toContainText(b);
  release();await expect(page.locator('.specimen-identifiers')).not.toContainText(a);await expect(page.locator('#inspection-heading')).toHaveText(label!);
});

test("cached classification survives a failed stale refresh, and explicit retry recovers",async({page})=>{
  await page.addInitScript(()=>{const original=Date.now();Object.assign(window,{cacheTestTime:original});Date.now=()=>Reflect.get(window,'cacheTestTime');});
  await page.goto('/explore?surface=lineage');await expect(page.getByRole('treeitem').first()).toBeVisible();
  const labels=await page.getByRole('treeitem').allTextContents();
  await page.getByRole('button',{name:'Localities',exact:true}).click();await expect(page.locator('.association-rows li').first()).toBeVisible();
  await page.evaluate(()=>Reflect.set(window,'cacheTestTime',Reflect.get(window,'cacheTestTime')+61000));
  await page.route('**/api/v1/lineage?**',route=>route.fulfill({status:503,json:{error:{message:'Refresh temporarily unavailable'}}}));
  await page.getByRole('button',{name:'Lineage',exact:true}).click();
  await expect(page.locator('.snapshot-status')).toContainText('Refresh temporarily unavailable');expect(await page.getByRole('treeitem').allTextContents()).toEqual(labels);
  await page.unroute('**/api/v1/lineage?**');await page.getByRole('button',{name:'Retry lineage',exact:true}).click();await expect(page.locator('.snapshot-status')).toHaveCount(0);
});

test("closing and reopening material preserves pagination without another request",async({page})=>{
  await page.goto('/explore');await openCatalog(page);await page.getByRole('button',{name:'Next →',exact:true}).click();
  await expect(page.locator('.catalog-list')).toHaveAttribute('start','31');
  const rows=await page.locator('.catalog-entry').evaluateAll(items=>items.map(item=>item.id));let requests=0;
  await page.locator('.catalog-list').evaluate(element=>{element.scrollTop=80;});const scroll=await page.locator('.catalog-list').evaluate(element=>element.scrollTop);
  page.on('request',r=>{if(r.url().includes('/catalog?'))requests++;});
  await page.getByRole('button',{name:'Close catalog',exact:true}).click();await expect(page.locator('.catalog-panel')).toBeHidden();
  await page.locator('#catalog-toggle').click();await expect(page.locator('.catalog-panel')).toBeVisible();await expect(page.locator('.catalog-list')).toHaveAttribute('start','31');
  expect(await page.locator('.catalog-entry').evaluateAll(items=>items.map(item=>item.id))).toEqual(rows);expect(requests).toBe(0);
  expect(await page.locator('.catalog-list').evaluate(element=>element.scrollTop)).toBe(scroll);
});

test("failed import metadata refresh keeps the count and labels its last loaded status",async({page})=>{
  await page.addInitScript(()=>{Object.assign(window,{metadataTestTime:Date.now()});Date.now=()=>Reflect.get(window,'metadataTestTime');});
  await page.goto('/explore');const status=page.locator('.canvas-source > span');await expect(status).toContainText('81 assertions');
  await page.route('**/api/v1/datasets/ufvp',route=>route.fulfill({status:503,json:{error:{message:'Status temporarily unavailable'}}}));
  await page.evaluate(()=>{Reflect.set(window,'metadataTestTime',Reflect.get(window,'metadataTestTime')+61000);window.dispatchEvent(new Event('focus'));});
  await expect(status).toContainText('Last loaded import status / refresh unavailable');await expect(status).toContainText('81 assertions');
});
