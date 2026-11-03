import { contextQuery } from "../../lib/api/discovery.ts";
import type { Viewport } from "../../lib/api/types.ts";
import type { ExploreState } from "./state.ts";

// Catalog text is independent of the entity-search combobox. Its spatial scope
// never changes the map camera, exact place, or retained source-context filters.
export function catalogContext(state: ExploreState, viewport?: Viewport): string {
  const bounded = viewport && state.catalog_scope !== "archive" && state.source !== "pbdb";
  const params = contextQuery(state, bounded ? viewport : undefined);
  if (state.catalog_q?.trim()) params.set("q", state.catalog_q.trim());
  return params.toString();
}

export function catalogScope(state: ExploreState, mapVisible: boolean): "map" | "archive" {
  return mapVisible && state.source !== "pbdb" && state.catalog_scope !== "archive" ? "map" : "archive";
}
