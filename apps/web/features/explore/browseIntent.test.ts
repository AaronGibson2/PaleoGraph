import assert from "node:assert/strict";
import test from "node:test";
import type { EntityDetail } from "../../lib/api/discovery.ts";
import { inspectionAssertion } from "./browseIntent.ts";

test("a visible assertion is only a loading hint; inspected specimen evidence remains authoritative",()=>{
  const hint={kind:'specimen' as const,id:'specimen',label:'accession',subtitle:null,occurrence_id:'visible-assertion'};
  assert.equal(inspectionAssertion('specimen','specimen',undefined,hint),'visible-assertion');
  const detail:EntityDetail={entity:hint,properties:{occurrence_id:'entity-evidence'},material_count:2,mapped_count:2,related:[],related_has_more:false,research_note:''};
  assert.equal(inspectionAssertion('specimen','specimen',detail,hint),'entity-evidence');
  assert.equal(inspectionAssertion('specimen','other',detail,hint),undefined);
  assert.equal(inspectionAssertion('taxon','specimen',undefined,hint),undefined);
  assert.equal(inspectionAssertion('specimen','specimen',{...detail,properties:{}},hint),undefined);
});
