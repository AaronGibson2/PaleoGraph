import type { AgeRange, Viewport } from "../../lib/api/types.ts";
import { contextKeys, type EntityKind, type ExplorationContext } from "../../lib/api/discovery.ts";

export type ExploreState = AgeRange & ExplorationContext & { lat: number; lng: number; zoom: number; selected: string | null; selected_kind?: EntityKind; surface?: "map" | "relationships" | "localities" | "lineage"; lineage_focus?: string | null; time_focus?: string; interval_id?: string | null; catalog?: "open" | null; inspect?: "closed" | null };
export const DEFAULT_VIEW = { lat: 28.4, lng: -83.0, zoom: 6.2 };
export const FLORIDA_VIEWPORT: Viewport = { west: -88, south: 24, east: -79, north: 32 };

export function lineageContext(active: string | null | undefined, focus: string | null | undefined, path: readonly { id: string }[]): string | null {
  // A focus can narrow its ancestor. A descendant already selected remains conjunctive.
  if (active && !path.some(item => item.id === active)) return active;
  return focus ?? active ?? null;
}

function numeric(params: URLSearchParams, key: string, fallback: number, min: number, max: number): number {
  const raw = params.get(key);
  const value = raw === null || raw.trim() === "" ? NaN : Number(raw);
  return Number.isFinite(value) && value >= min && value <= max ? value : fallback;
}

export function parseExploreState(params: URLSearchParams): ExploreState {
  const older = numeric(params, "older_ma", NaN, 0, 10000);
  const younger = numeric(params, "younger_ma", NaN, 0, 10000);
  const hasAge = Number.isFinite(older) && Number.isFinite(younger) && older >= younger;
  const selected = params.get("selected");
  const context: ExplorationContext = {};
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  for (const key of contextKeys.slice(0, 5) as ("taxon_id" | "locality_id" | "collection_id" | "institution_id" | "term_id")[]) {
    const value = params.get(key);
    if (value && uuid.test(value)) context[key] = value;
  }
  const lon = numeric(params, "at_lon", NaN, -180, 180);
  const lat = numeric(params, "at_lat", NaN, -90, 90);
  if (Number.isFinite(lon) && Number.isFinite(lat)) { context.at_lon = lon; context.at_lat = lat; }
  const kind = params.get("selected_kind");
  const kinds = ["occurrence", "reference", "specimen", "taxon", "locality", "collection", "institution", "term"];
  return {
    ...context,
    ...(["ufvp","pbdb","all"].includes(params.get("source") ?? "") ? {source: params.get("source") as ExplorationContext["source"]} : {}),
    ...(uuid.test(params.get("reference_id") ?? "") ? {reference_id:params.get("reference_id")!} : {}),
    lat: numeric(params, "lat", DEFAULT_VIEW.lat, -85, 85),
    lng: numeric(params, "lng", DEFAULT_VIEW.lng, -180, 180),
    zoom: numeric(params, "zoom", DEFAULT_VIEW.zoom, 1, 18),
    older_ma: hasAge ? older : null,
    younger_ma: hasAge ? younger : null,
    selected: selected && uuid.test(selected) ? selected : null,
    ...(kind && kinds.includes(kind) ? { selected_kind: kind as EntityKind } : {}),
    ...(["relationships", "localities", "lineage"].includes(params.get("surface") ?? "") ? { surface: params.get("surface") as ExploreState["surface"] } : {}),
    ...(uuid.test(params.get("lineage_focus") ?? "") ? { lineage_focus: params.get("lineage_focus")! } : {}),
    ...(params.get("q") ? { q: params.get("q")!.slice(0, 160) } : {}),
    ...(params.get("catalog")==="open" ? {catalog:"open" as const} : {}),
    ...(params.get("inspect")==="closed" ? {inspect:"closed" as const} : {}),
    ...(params.get("time_focus")?.startsWith("ics:2026-06:") ? { time_focus: params.get("time_focus")! } : {}),
    ...(hasAge && params.get("interval_id")?.startsWith("ics:2026-06:") ? { interval_id: params.get("interval_id")! } : {}),
  };
}

export function serializeExploreState(state: ExploreState, current = new URLSearchParams()): string {
  const params = new URLSearchParams(current);
  params.set("lat", state.lat.toFixed(5));
  params.set("lng", state.lng.toFixed(5));
  params.set("zoom", state.zoom.toFixed(2));
  params.delete("data_mode"); // Retired public mode is never restored or written.
  for (const key of ["older_ma", "younger_ma", "selected", "selected_kind", "surface", "lineage_focus", "q", "time_focus", "interval_id", "catalog", "inspect", ...contextKeys] as const) {
    if (state[key] === null || state[key] === undefined || state[key] === "" || state[key] === "map") params.delete(key);
    else params.set(key, String(state[key]));
  }
  return params.toString();
}

export function normalizeViewport(west: number, south: number, east: number, north: number): Viewport {
  const wrap = (longitude: number) => ((longitude + 180) % 360 + 360) % 360 - 180;
  return {
    west: east - west >= 360 ? -180 : wrap(west),
    east: east - west >= 360 ? 180 : wrap(east),
    south: Math.max(-90, south), north: Math.min(90, north),
  };
}

export function formatMa(value: number): string {
  // Reference calibration/filter precision, never a specimen measurement or midpoint.
  // The pinned chart needs at most four decimals; do not round nonzero ages to present.
  if (value > 0 && value < 0.0001) return Number(value.toPrecision(4)).toExponential();
  return value.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

export function ageLabel(age: AgeRange): string {
  if (age.older_ma === null && age.younger_ma === null) return "No numeric envelope";
  if (age.older_ma === null || age.younger_ma === null) return "Partial numeric bounds";
  return `${formatMa(age.older_ma)}–${formatMa(age.younger_ma)} Ma`;
}
