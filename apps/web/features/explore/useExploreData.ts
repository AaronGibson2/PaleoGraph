"use client";

import { useEffect, useReducer, useState } from "react";
import { api } from "../../lib/api/client";
import type { AgeRange, DatasetStatus, OccurrenceDetail, TimeConfiguration, Viewport } from "../../lib/api/types";
import { contextQuery, discovery, type ExplorationContext } from "../../lib/api/discovery";
import type { MapResponse } from "../../lib/api/types";
import { initialWindow, occurrenceWindow } from "./occurrenceWindow";
import { browseCache } from "./browseCache";

type LoadState<T> = { key: string; data?: T; error?: string };
const message = (error: unknown) => error instanceof Error ? error.message : "Data could not be loaded.";

export function useOccurrences(viewport: Viewport, age: AgeRange & ExplorationContext, retry: number) {
  const { west, south, east, north } = viewport;
  const contextKey = JSON.stringify({ older_ma: age.older_ma, younger_ma: age.younger_ma, taxon_id: age.taxon_id, locality_id: age.locality_id, collection_id: age.collection_id, institution_id: age.institution_id, term_id: age.term_id, at_lon: age.at_lon, at_lat: age.at_lat });
  const [state, dispatch] = useReducer(occurrenceWindow, { viewport, age, retry }, initialWindow);
  useEffect(() => {
    dispatch({ type: "intent", intent: { viewport: { west, south, east, north }, age: JSON.parse(contextKey) as AgeRange & ExplorationContext, retry } });
  }, [west, south, east, north, contextKey, retry]);
  useEffect(() => {
    const request = state.request;
    if (!request) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        let bounds = request.bounds;
        let data = await loadPlaces(bounds, request.age, controller.signal);
        // A capped buffer is not complete coverage. Re-query the actual view so
        // offscreen records cannot crowd visible records out of the result cap.
        if (data.truncated && !controller.signal.aborted) {
          bounds = request.viewport;
          data = await loadPlaces(bounds, request.age, controller.signal);
        }
        if (!controller.signal.aborted) dispatch({ type: "success", id: request.id, bounds, data });
      } catch (error) {
        if (!controller.signal.aborted) dispatch({ type: "failure", id: request.id, error: message(error) });
      }
    }, 180);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [state.request]);
  return { data: state.display, mapItems: state.loaded?.data.items, error: state.error, loading: state.request !== null };
}

export function useDatasetStatus(retry: number) {
  const [result, setResult] = useState<LoadState<DatasetStatus>>({ key: "" });
  useEffect(() => {
    const controller = new AbortController();
    let lastChecked=0;
    const check = () => { if(Date.now()-lastChecked<60_000)return; lastChecked=Date.now(); api.datasetStatus(controller.signal).then(
      data => { if (!controller.signal.aborted) { browseCache.observeRevision(JSON.stringify([data.version,data.current_records,data.latest_scope,data.latest_status])); setResult({ key: String(retry), data }); } },
      error => { if (!controller.signal.aborted) setResult(previous=>({ ...previous,key: String(retry), error: message(error) })); },
    ); };
    check();
    const timer=setInterval(check,300_000);
    window.addEventListener("focus",check);
    return () => { clearInterval(timer); window.removeEventListener("focus",check); controller.abort(); };
  }, [retry]);
  return result;
}

export function useOccurrence(id: string | null, retry: number): LoadState<OccurrenceDetail> & { loading: boolean } {
  const key = `${id}:${retry}`;
  const [result, setResult] = useState<LoadState<OccurrenceDetail>>({ key: "" });
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    api.occurrence(id, controller.signal).then(
      data => { if (!controller.signal.aborted) setResult({ key, data }); },
        error => { if (!controller.signal.aborted) setResult(previous => ({ key, data: previous.key.startsWith(`${id}:`) ? previous.data : undefined, error: message(error) })); },
    );
    return () => controller.abort();
  }, [id, key]);
  return result.key === key ? { ...result, loading: false } : { key, data: result.key.startsWith(`${id}:`) ? result.data : undefined, loading: id !== null };
}

export function useTimeConfiguration(retry: number) {
  const [result, setResult] = useState<LoadState<TimeConfiguration>>({ key: "" });
  useEffect(() => {
    const controller = new AbortController();
    api.timeConfiguration(controller.signal).then(
      data => { if (!controller.signal.aborted) setResult({ key: String(retry), data }); },
      error => { if (!controller.signal.aborted) setResult({ key: String(retry), error: message(error) }); },
    );
    return () => controller.abort();
  }, [retry]);
  return result;
}

async function loadPlaces(bounds: Viewport, context: AgeRange & ExplorationContext, signal: AbortSignal): Promise<MapResponse> {
  const params = contextQuery(context, bounds);
  let page = await discovery.places(params.toString(), signal);
  const places = [...page.items];
  while (page.next_cursor && !signal.aborted) {
    params.set("cursor", page.next_cursor);
    page = await discovery.places(params.toString(), signal);
    places.push(...page.items);
  }
  return { items: places.map(place => ({ ...place, scientific_name: `${place.record_count.toLocaleString("en-US")} catalog assertions`, locality_name: `${place.locality_count} published localities`, older_ma: null, younger_ma: null, is_synthetic: false })), returned: places.length, truncated: false, limit: places.length };
}
