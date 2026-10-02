"use client";

import { useEffect, useState } from "react";
import { api, occurrenceQuery } from "../../lib/api/client";
import type { AgeRange, MapResponse, OccurrenceDetail, TimeConfiguration, Viewport } from "../../lib/api/types";

type LoadState<T> = { key: string; data?: T; error?: string };
const message = (error: unknown) => error instanceof Error ? error.message : "Data could not be loaded.";

export function useOccurrences(viewport: Viewport, age: AgeRange, retry: number): LoadState<MapResponse> & { loading: boolean } {
  const query = occurrenceQuery(viewport, age);
  const key = `${query}:${retry}`;
  const [result, setResult] = useState<LoadState<MapResponse>>({ key: "" });
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.occurrences(query, controller.signal).then(
        data => { if (!controller.signal.aborted) setResult({ key, data }); },
        error => { if (!controller.signal.aborted) setResult({ key, error: message(error) }); },
      );
    }, 180);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, key]);
  // Old viewport/time results are never presented as matching the new query.
  return result.key === key ? { ...result, loading: false } : { key, loading: true };
}

export function useOccurrence(id: string | null, retry: number): LoadState<OccurrenceDetail> & { loading: boolean } {
  const key = `${id}:${retry}`;
  const [result, setResult] = useState<LoadState<OccurrenceDetail>>({ key: "" });
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    api.occurrence(id, controller.signal).then(
      data => { if (!controller.signal.aborted) setResult({ key, data }); },
      error => { if (!controller.signal.aborted) setResult({ key, error: message(error) }); },
    );
    return () => controller.abort();
  }, [id, key]);
  return result.key === key ? { ...result, loading: false } : { key, loading: id !== null };
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
