import { contextQuery, type SourceSelection } from "../../lib/api/discovery.ts";
import type { Viewport } from "../../lib/api/types.ts";
import type { ExploreState } from "./state.ts";

export function explorationSource(state: Pick<ExploreState, "source" | "surface">): SourceSelection {
  return state.source ?? (state.surface === "lineage" ? "all" : "ufvp");
}

// Catalog text is independent of the entity-search combobox. Its spatial scope
// never changes the map camera, exact place, or retained source-context filters.
export function catalogContext(state: ExploreState, viewport?: Viewport): string {
  const source = explorationSource(state);
  const bounded = viewport && state.catalog_scope !== "archive" && source !== "pbdb";
  const params = contextQuery({ ...state, source }, bounded ? viewport : undefined);
  if (state.catalog_q?.trim()) params.set("q", state.catalog_q.trim());
  return params.toString();
}

export function catalogScope(state: ExploreState, mapVisible: boolean): "map" | "archive" {
  return mapVisible && state.source !== "pbdb" && state.catalog_scope !== "archive" ? "map" : "archive";
}
