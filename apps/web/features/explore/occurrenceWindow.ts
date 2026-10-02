import type { AgeRange, MapResponse, Viewport } from "../../lib/api/types.ts";
import { normalizeViewport } from "./state.ts";

const span = (box: Viewport) => box.east >= box.west ? box.east - box.west : 360 + box.east - box.west;
const offset = (from: number, to: number) => ((to - from) % 360 + 360) % 360;
export const sameViewport = (a: Viewport, b: Viewport) => a.west === b.west && a.east === b.east && a.south === b.south && a.north === b.north;
const sameAge = (a: AgeRange, b: AgeRange) => a.older_ma === b.older_ma && a.younger_ma === b.younger_ma;

export function bufferedViewport(view: Viewport): Viewport {
  // 25% per edge: at most 1.5× the width/height, capped at the world bounds.
  const width = span(view);
  const padding = (view.north - view.south) * 0.25;
  return normalizeViewport(view.west - width * 0.25, view.south - padding, view.west + width * 1.25, view.north + padding);
}

export function containsViewport(outer: Viewport, inner: Viewport, margin = 0): boolean {
  const width = span(outer);
  const height = outer.north - outer.south;
  const x = offset(outer.west, inner.west);
  return (width >= 360 || (x >= width * margin - 1e-8 && x + span(inner) <= width * (1 - margin) + 1e-8))
    && inner.south >= (outer.south <= -90 ? -90 : outer.south + height * margin) - 1e-8
    && inner.north <= (outer.north >= 90 ? 90 : outer.north - height * margin) + 1e-8;
}

function visible(data: MapResponse, view: Viewport): MapResponse {
  const items = data.items.filter(item => item.latitude >= view.south && item.latitude <= view.north
    && (span(view) >= 360 || offset(view.west, item.longitude) <= span(view) + 1e-8));
  return { ...data, items, returned: items.length };
}

export type Intent = { viewport: Viewport; age: AgeRange; retry: number };
export type WindowRequest = Intent & { id: number; bounds: Viewport };
type Loaded = { bounds: Viewport; data: MapResponse; age: AgeRange; retry: number };
export type WindowState = {
  intent: Intent; serial: number; request: WindowRequest | null;
  loaded?: Loaded; display?: MapResponse; error?: string;
};
type Action = { type: "intent"; intent: Intent }
  | { type: "success"; id: number; bounds: Viewport; data: MapResponse }
  | { type: "failure"; id: number; error: string };

function reusable(loaded: Loaded, intent: Intent, margin: number): boolean {
  return loaded.retry === intent.retry && sameAge(loaded.age, intent.age)
    && (loaded.data.truncated ? sameViewport(loaded.bounds, intent.viewport) : containsViewport(loaded.bounds, intent.viewport, margin));
}

function plan(state: WindowState, intent: Intent, margin = 0.05): WindowState {
  if (state.loaded && reusable(state.loaded, intent, margin)) {
    return { ...state, intent, request: null, error: undefined, display: visible(state.loaded.data, intent.viewport) };
  }
  if (state.loaded && state.request && state.request.retry === intent.retry && sameAge(state.request.age, intent.age)
    && containsViewport(state.request.bounds, intent.viewport, margin)) {
    return { ...state, intent }; // Let this already useful request finish; project to the newest viewport.
  }
  const serial = state.serial + 1;
  return { ...state, intent, serial, error: undefined, request: { ...intent, id: serial, bounds: bufferedViewport(intent.viewport) } };
}

export function initialWindow(intent: Intent): WindowState {
  return plan({ intent, serial: 0, request: null }, intent);
}

export function occurrenceWindow(state: WindowState, action: Action): WindowState {
  if (action.type === "intent") {
    const next = action.intent;
    if (next.retry === state.intent.retry && sameAge(next.age, state.intent.age) && sameViewport(next.viewport, state.intent.viewport)) return state;
    return plan(state, next);
  }
  if (action.id !== state.request?.id) return state; // Even a transport ignoring abort cannot win a race.
  if (action.type === "failure") return { ...state, request: null, error: action.error };
  const loaded = { bounds: action.bounds, data: action.data, age: state.request.age, retry: state.request.retry };
  if (!reusable(loaded, state.intent, 0)) return plan({ ...state, request: null }, state.intent);
  return plan({ ...state, request: null, loaded }, state.intent, 0);
}
