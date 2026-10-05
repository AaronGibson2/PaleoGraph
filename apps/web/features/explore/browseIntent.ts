import { api } from "../../lib/api/client.ts";
import { discovery, type EntityDetail, type EntityKind, type EntityRef } from "../../lib/api/discovery.ts";
import { browseCache, browseKey } from "./browseCache.ts";

// These hints come from the actual visible catalog assertion, never guessed identity.
export type BrowseTarget = EntityRef & { occurrence_id?: string };
export const entityKey = (entity: Pick<EntityRef,"kind"|"id">) => browseKey(`/entities/${entity.kind}/${encodeURIComponent(entity.id)}`);
export const occurrenceKey = (id: string) => browseKey(`/occurrences/${encodeURIComponent(id)}`);
export function inspectionAssertion(kind: EntityKind, id: string, detail?: EntityDetail, hint?: BrowseTarget): string | undefined {
  // The existing entity endpoint chooses its evidence-bearing assertion. A visible
  // row is an early loading hint, not permission to mix assertions for one specimen.
  if(detail?.entity.id===id && detail.entity.kind===kind)return typeof detail.properties.occurrence_id==="string" ? detail.properties.occurrence_id : undefined;
  return kind==="specimen" && hint?.id===id && hint.kind===kind ? hint.occurrence_id : undefined;
}
export function prefetchEntity(entity: BrowseTarget) {
  browseCache.prefetch(entityKey(entity),signal=>discovery.entity(entity.kind,entity.id,"",signal));
  if(entity.occurrence_id)browseCache.prefetch(occurrenceKey(entity.occurrence_id),signal=>api.occurrence(entity.occurrence_id!,signal));
}
export function prefetchLineage(context: string, focus?: string | null) {
  const query=`${context}&limit=12${focus?`&focus=${encodeURIComponent(focus)}`:""}`;
  browseCache.prefetch(browseKey("/lineage",query),signal=>discovery.lineage(query,signal));
}
export function pivotContext(context: string, entity: EntityRef) {
  const params=new URLSearchParams(context);
  params.delete("at_lon");params.delete("at_lat");
  if(entity.kind!=="specimen")params.set(`${entity.kind}_id`,entity.id);
  return params.toString();
}
export function prefetchLocality(context: string, entity: EntityRef) {
  const query=pivotContext(context,entity);
  browseCache.prefetch(browseKey(`/localities/${entity.id}`,query),signal=>discovery.locality(entity.id,query,signal));
  const fauna=`${query}&q=&order=count&limit=20`;
  browseCache.prefetch(browseKey(`/localities/${entity.id}/taxa`,fauna),signal=>discovery.fauna(entity.id,fauna,signal));
}
export function prefetchMaterial(query: string) {
  const page=`${query}&limit=30`;
  browseCache.prefetch(browseKey("/catalog",page),async signal=>({...await discovery.catalog(page,signal),offset:0}));
}
export function prefetchLocalities(context: string, taxon: string | null) {
  const params=new URLSearchParams(context);
  if(taxon)params.set("taxon_id",taxon);else params.delete("taxon_id");
  const query=`${params}&q=&order=count&limit=20`;
  browseCache.prefetch(browseKey("/localities",query),signal=>discovery.localities(query,signal));
}
