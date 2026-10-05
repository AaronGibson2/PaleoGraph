"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { BROWSE_FRESH_MS, browseCache } from "./browseCache";

// Retain the last successful snapshot across refreshes and failures; abort and key-check
// prevent an obsolete request from replacing newer intent. Loading is derived, not cleared.
export function useResource<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>, delay = 0, retry = 0) {
  const latest = useRef(load);
  useEffect(() => { latest.current = load; }, [load]);
  const generation = useSyncExternalStore(browseCache.subscribe,browseCache.generation,()=>0);
  const [result, setResult] = useState<{ key: string; generation?: number; data?: T; error?: string }>({ key: "" });
  const previousRetry = useRef(retry);
  const cached = key?.startsWith("/") ? browseCache.snapshot<T>(key) : undefined;
  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    const force = previousRetry.current !== retry;
    previousRetry.current = retry;
    let refresh: ReturnType<typeof setTimeout> | undefined;
    const run = (bypass = force) => {
      const pending = key.startsWith("/") ? browseCache.load(key,latest.current,controller.signal,bypass) : latest.current(controller.signal);
      pending.then(
        data => { if (!controller.signal.aborted) { setResult({ key, generation, data }); if(key.startsWith("/"))refresh=setTimeout(()=>run(true),BROWSE_FRESH_MS); } },
        error => { if (!controller.signal.aborted) setResult(previous => ({ key, generation, data: previous.data, error: error instanceof Error ? error.message : "Data could not load." })); },
      );
    };
    // A prepared snapshot is rendered synchronously and does not incur input debounce.
    const timer = setTimeout(run,key.startsWith("/") && browseCache.snapshot(key) ? 0 : delay);
    return () => { clearTimeout(timer); clearTimeout(refresh); controller.abort(); };
  }, [key, delay, retry, generation]);
  return cached ? { key:key!, data:cached.data, error:result.key===key?result.error:undefined, loading:!cached.fresh && (result.key!==key || result.generation!==generation) } : { ...result, loading: key !== null && (result.key !== key || result.generation!==generation) };
}
