import type { AgeRange, Viewport } from "../../lib/api/types.ts";

export type ExploreState = AgeRange & { lat: number; lng: number; zoom: number; selected: string | null };
export const DEFAULT_VIEW = { lat: 28.4, lng: -83.0, zoom: 6.2 };
export const FLORIDA_VIEWPORT: Viewport = { west: -88, south: 24, east: -79, north: 32 };

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
  return {
    lat: numeric(params, "lat", DEFAULT_VIEW.lat, -85, 85),
    lng: numeric(params, "lng", DEFAULT_VIEW.lng, -180, 180),
    zoom: numeric(params, "zoom", DEFAULT_VIEW.zoom, 1, 18),
    older_ma: hasAge ? older : null,
    younger_ma: hasAge ? younger : null,
    selected: selected && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(selected) ? selected : null,
  };
}

export function serializeExploreState(state: ExploreState, current = new URLSearchParams()): string {
  const params = new URLSearchParams(current);
  params.set("lat", state.lat.toFixed(5));
  params.set("lng", state.lng.toFixed(5));
  params.set("zoom", state.zoom.toFixed(2));
  for (const key of ["older_ma", "younger_ma", "selected"] as const) {
    if (state[key] === null) params.delete(key);
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

export function ageLabel(age: AgeRange): string {
  if (age.older_ma === null && age.younger_ma === null) return "Age unknown";
  if (age.older_ma === null || age.younger_ma === null) return "Age partly known";
  return `${age.older_ma.toLocaleString("en-US")}–${age.younger_ma.toLocaleString("en-US")} Ma`;
}
