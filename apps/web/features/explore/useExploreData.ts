"use client";

import { useEffect, useReducer, useState } from "react";
import { api, occurrenceQuery } from "../../lib/api/client";
import type { AgeRange, DatasetStatus, OccurrenceDetail, TimeConfiguration, Viewport } from "../../lib/api/types";
import { initialWindow, occurrenceWindow } from "./occurrenceWindow";

type LoadState<T> = { key: string; data?: T; error?: string };
const message = (error: unknown) => error instanceof Error ? error.message : "Data could not be loaded.";

export function useOccurrences(viewport: Viewport, age: AgeRange, retry: number) {
  const { west, south, east, north } = viewport;
  const { older_ma, younger_ma, data_mode } = age;
  const [state, dispatch] = useReducer(occurrenceWindow, { viewport, age, retry }, initialWindow);
  useEffect(() => {
    dispatch({ type: "intent", intent: { viewport: { west, south, east, north }, age: { older_ma, younger_ma, data_mode }, retry } });
  }, [west, south, east, north, older_ma, younger_ma, data_mode, retry]);
  useEffect(() => {
    const request = state.request;
    if (!request) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        let bounds = request.bounds;
        let data = await api.occurrences(occurrenceQuery(bounds, request.age), controller.signal);
        // A capped buffer is not complete coverage. Re-query the actual view so
        // offscreen records cannot crowd visible records out of the result cap.
        if (data.truncated && !controller.signal.aborted) {
          bounds = request.viewport;
          data = await api.occurrences(occurrenceQuery(bounds, request.age), controller.signal);
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
    api.datasetStatus(controller.signal).then(
      data => { if (!controller.signal.aborted) setResult({ key: String(retry), data }); },
      error => { if (!controller.signal.aborted) setResult({ key: String(retry), error: message(error) }); },
    );
    return () => controller.abort();
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
