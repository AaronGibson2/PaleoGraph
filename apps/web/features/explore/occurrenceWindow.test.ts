import assert from "node:assert/strict";
import test from "node:test";
import { bufferedViewport, containsViewport, initialWindow, occurrenceWindow, type Intent } from "./occurrenceWindow.ts";
import type { MapResponse } from "../../lib/api/types.ts";

const intent: Intent = { viewport: { west: 170, east: -170, south: -10, north: 10 }, age: { older_ma: null, younger_ma: null }, retry: 0 };
const data: MapResponse = { items: [], limit: 200, returned: 0, truncated: false };

test("initial buffering uses real map bounds rather than keeping fallback coverage", () => {
  const start = initialWindow(intent);
  const actual = { ...intent, viewport: { ...intent.viewport, west: 168, east: -168 } };
  const next = occurrenceWindow(start, { type: "intent", intent: actual });
  assert.deepEqual(next.request?.bounds, bufferedViewport(actual.viewport));
  assert.notEqual(next.request?.id, start.request?.id);
});

test("buffers cover dateline pans, cap world bounds, and reject uncovered geography", () => {
  const bounds = bufferedViewport(intent.viewport);
  assert.deepEqual(bounds, { west: 165, east: -165, south: -15, north: 15 });
  assert(containsViewport(bounds, { ...intent.viewport, west: 171, east: -169 }, 0.05));
  assert(!containsViewport(bounds, { ...intent.viewport, west: -160, east: -140 }));
  assert(!containsViewport(bounds, { ...intent.viewport, west: -175, east: 175 }));
  assert.deepEqual(bufferedViewport({ west: -170, east: 170, south: -80, north: 80 }), { west: -180, east: 180, south: -90, north: 90 });
});

test("small pans reuse coverage; large pans retain results and ignore obsolete completions", () => {
  const start = initialWindow(intent);
  const loaded = occurrenceWindow(start, { type: "success", id: start.request!.id, bounds: start.request!.bounds, data });
  const nearby = occurrenceWindow(loaded, { type: "intent", intent: { ...intent, viewport: { ...intent.viewport, west: 171, east: -169 } } });
  assert.equal(nearby.request, null);
  const far = occurrenceWindow(nearby, { type: "intent", intent: { ...intent, viewport: { west: 0, east: 20, south: -10, north: 10 } } });
  assert(far.request);
  assert.equal(far.display, nearby.display);
  const newest = occurrenceWindow(far, { type: "intent", intent: { ...intent, age: { older_ma: 2, younger_ma: 1 } } });
  assert.equal(occurrenceWindow(newest, { type: "success", id: far.request.id, bounds: far.request.bounds, data }), newest);
  assert.equal(occurrenceWindow(newest, { type: "failure", id: far.request.id, error: "obsolete" }), newest);
});

test("truncated results never claim a complete reusable buffer", () => {
  const start = initialWindow(intent);
  const loaded = occurrenceWindow(start, { type: "success", id: start.request!.id, bounds: intent.viewport, data: { ...data, truncated: true } });
  assert.equal(loaded.request, null);
  const moved = occurrenceWindow(loaded, { type: "intent", intent: { ...intent, viewport: { ...intent.viewport, west: 170.1 } } });
  assert(moved.request);
  assert.equal(moved.display, loaded.display);
});

test("an error retains successful data and an explicit retry creates a new request", () => {
  const start = initialWindow(intent);
  const loaded = occurrenceWindow(start, { type: "success", id: start.request!.id, bounds: start.request!.bounds, data });
  const change = occurrenceWindow(loaded, { type: "intent", intent: { ...intent, age: { older_ma: 2, younger_ma: 1 } } });
  const failed = occurrenceWindow(change, { type: "failure", id: change.request!.id, error: "offline" });
  assert.equal(failed.display, loaded.display);
  assert.equal(failed.loaded, loaded.loaded);
  const retry = occurrenceWindow(failed, { type: "intent", intent: { ...change.intent, retry: 1 } });
  assert(retry.request);
  assert.equal(retry.error, undefined);
});


test("museum/demo switches never retain or reuse another dataset window", () => {
  const intent = { viewport: {west:-88,south:24,east:-79,north:32}, age: {older_ma:null,younger_ma:null}, retry:0 };
  const first = initialWindow(intent);
  const loaded = occurrenceWindow(first, {type:"success",id:first.request!.id,bounds:first.request!.bounds,data:{items:[],returned:0,truncated:false,limit:200}});
  const changed = occurrenceWindow(loaded, {type:"intent",intent:{...intent,age:{...intent.age,data_mode:"demo"}}});
  assert.equal(changed.loaded, undefined);
  assert.equal(changed.display, undefined);
  assert.ok(changed.request);
});
