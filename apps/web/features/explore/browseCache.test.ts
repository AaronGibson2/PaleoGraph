import assert from "node:assert/strict";
import test from "node:test";
import { BrowseCache, browseKey } from "./browseCache.ts";

function deferred<T>() { let resolve!: (value: T) => void; const promise=new Promise<T>(done=>{resolve=done;}); return {promise,resolve}; }
test("exact keys canonicalize parameter order while separating all scientific contexts and cursors",()=>{
  assert.equal(browseKey('/catalog','taxon_id=a&limit=30'),browseKey('/catalog','limit=30&taxon_id=a'));
  const keys=['taxon_id=a','taxon_id=b','locality_id=a','older_ma=12&younger_ma=2','older_ma=12&younger_ma=3','cursor=a','cursor=b','at_lon=1&at_lat=2','west=1&east=2'].map(q=>browseKey('/catalog',q));
  assert.equal(new Set(keys).size,keys.length);
  assert.notEqual(browseKey('/localities/a/taxa'),browseKey('/localities/b/taxa'));
});
test("miss then hit reuses a snapshot without loading again",async()=>{
  const cache=new BrowseCache(); let calls=0; const load=async()=>({count:++calls});
  assert.deepEqual(await cache.load('a',load),{count:1});assert.deepEqual(await cache.load('a',load),{count:1});
  assert.equal(calls,1);assert.equal(cache.metrics.hits,1);assert.equal(cache.metrics.misses,1);
});
test("identical flights deduplicate; aborting one consumer does not cancel another",async()=>{
  const cache=new BrowseCache(); const held=deferred<string>();let calls=0;let shared:AbortSignal|undefined;
  const load=(signal:AbortSignal)=>{calls++;shared=signal;return held.promise;};
  const cancel=new AbortController();const first=cache.load('a',load,cancel.signal);const rejected=assert.rejects(first,{name:'AbortError'});
  const second=cache.load('a',load);await Promise.resolve();cancel.abort();await rejected;
  assert.equal(shared?.aborted,false);held.resolve('right');assert.equal(await second,'right');assert.equal(calls,1);assert.equal(cache.metrics.deduplicated,1);
});
test("abandoned A cannot publish into A or B even when its loader ignores cancellation",async()=>{
  const cache=new BrowseCache();const held=deferred<string>();const abort=new AbortController();
  const obsolete=cache.load('a',()=>held.promise,abort.signal);const rejection=assert.rejects(obsolete,{name:'AbortError'});await Promise.resolve();abort.abort();
  assert.equal(await cache.load('b',async()=>'B'),'B');held.resolve('A');await rejection;await Promise.resolve();await Promise.resolve();
  assert.equal(cache.snapshot('a'),undefined);assert.equal(cache.snapshot<string>('b')?.data,'B');
});
test("stale snapshot survives failed refresh and expires at maximum age",async()=>{
  let now=0;const cache=new BrowseCache({now:()=>now,fresh:10,maxAge:100});await cache.load('a',async()=>'valid');now=11;
  assert.equal(cache.snapshot('a')?.fresh,false);await assert.rejects(cache.load('a',async()=>{throw Error('outage');}),/outage/);
  assert.equal(cache.snapshot<string>('a')?.data,'valid');await cache.load('a',async()=>'refreshed');assert.equal(cache.snapshot('a')?.fresh,true);
  now=111;assert.equal(cache.snapshot('a'),undefined);
});
test("LRU entry and payload bounds evict old results and reject oversized snapshots",async()=>{
  const cache=new BrowseCache({entries:2,bytes:20});await cache.load('a',async()=>'a');await cache.load('b',async()=>'b');await cache.load('a',async()=>'unused');await cache.load('c',async()=>'c');
  assert.equal(cache.snapshot('b'),undefined);assert.ok(cache.snapshot('a'));assert.ok(cache.snapshot('c'));
  await cache.load('huge',async()=>'x'.repeat(30));assert.equal(cache.snapshot('huge'),undefined);assert.ok(cache.inspect().bytes<=20);assert.ok(cache.inspect().entries<=2);
});
test("prefetch is bounded to two flights and reused by foreground consumers",async()=>{
  const cache=new BrowseCache();const a=deferred<string>(),b=deferred<string>();let extra=false;
  cache.prefetch('a',()=>a.promise);cache.prefetch('b',()=>b.promise);cache.prefetch('c',async()=>{extra=true;return 'c';});await Promise.resolve();
  assert.equal(cache.inspect().speculative,2);assert.equal(extra,false);a.resolve('A');b.resolve('B');await cache.load('a',async()=>'wrong');await cache.load('b',async()=>'wrong');
  assert.equal(await cache.load('a',async()=>'wrong'),'A');assert.ok(cache.metrics.prefetchHits>0);
});
test("revision change invalidates snapshots and late flights; unchanged metadata reuses results",async()=>{
  const cache=new BrowseCache();cache.observeRevision('v1');await cache.load('a',async()=>'old');cache.observeRevision('v1');assert.ok(cache.snapshot('a'));
  const held=deferred<string>();const pending=cache.load('b',()=>held.promise);const rejected=assert.rejects(pending,{name:'AbortError'});await Promise.resolve();cache.observeRevision('v2');held.resolve('obsolete');await rejected;
  assert.equal(cache.snapshot('a'),undefined);assert.equal(cache.snapshot('b'),undefined);assert.equal(cache.generation(),1);
});
test("explicit retry bypasses a fresh snapshot without discarding it on failure",async()=>{
  const cache=new BrowseCache();await cache.load('a',async()=>'valid');await assert.rejects(cache.load('a',async()=>{throw Error('failed');},undefined,true));assert.equal(cache.snapshot<string>('a')?.data,'valid');
  assert.equal(await cache.load('a',async()=>'new',undefined,true),'new');
});
