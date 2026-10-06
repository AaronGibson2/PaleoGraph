import test from "node:test";
import assert from "node:assert/strict";
import { datasetRevision } from "./datasetRevision.ts";
import { BrowseCache } from "./browseCache.ts";
import type { DatasetStatus } from "../../lib/api/types.ts";

const metadata: DatasetStatus = { title: "Fixture", dataset_url: "", license: null,
  version: "same-source", current_records: 8, mapped_records: 8, numeric_age_records: 0,
  latest_scope: "fixture", latest_status: "completed", creator: null,
  browse_revision: "1:browse-v1" };

test("a rebuilt projection invalidates cached summaries even when source totals are unchanged", async () => {
  const cache = new BrowseCache();
  cache.observeRevision(datasetRevision(metadata));
  await cache.load("locality", async () => ({ assertion_count: 8 }));
  assert.ok(cache.snapshot("locality"));
  cache.observeRevision(datasetRevision({ ...metadata, browse_revision: "2:browse-v1" }));
  assert.equal(cache.snapshot("locality"), undefined);
});

test("unchanged projection metadata retains snapshots; unbuilt state changes the revision", async () => {
  const cache = new BrowseCache();
  cache.observeRevision(datasetRevision(metadata));
  await cache.load("lineage", async () => ({ assertion_count: 8 }));
  cache.observeRevision(datasetRevision({ ...metadata }));
  assert.ok(cache.snapshot("lineage"));
  assert.notEqual(datasetRevision(metadata), datasetRevision({ ...metadata, browse_revision: "1:live" }));
});

test("scientific policy changes invalidate snapshots even with the same dataset and dirty projection", async () => {
  const cache = new BrowseCache();
  const previous = { ...metadata, browse_revision: "1:live:ufvp-geology-v1:ics-2026-06" };
  cache.observeRevision(datasetRevision(previous));
  await cache.load("lineage", async () => ({ older_ma: 11.63, younger_ma: 5.333 }));
  cache.observeRevision(datasetRevision({ ...previous, browse_revision: "1:live:test-next-policy" }));
  assert.equal(cache.snapshot("lineage"), undefined);
});
