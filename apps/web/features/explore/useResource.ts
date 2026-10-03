"use client";

import { useEffect, useRef, useState } from "react";

// Retain the last successful snapshot across refreshes and failures; abort and key-check
// prevent an obsolete request from replacing newer intent. Loading is derived, not cleared.
export function useResource<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>, delay = 0) {
  const latest = useRef(load);
  useEffect(() => { latest.current = load; }, [load]);
  const [result, setResult] = useState<{ key: string; data?: T; error?: string }>({ key: "" });
  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      latest.current(controller.signal).then(
        data => { if (!controller.signal.aborted) setResult({ key, data }); },
        error => { if (!controller.signal.aborted) setResult(previous => ({ key, data: previous.data, error: error instanceof Error ? error.message : "Data could not load." })); },
      );
    }, delay);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [key, delay]);
  return { ...result, loading: key !== null && result.key !== key };
}
