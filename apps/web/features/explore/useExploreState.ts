"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { parseExploreState, serializeExploreState, type ExploreState } from "./state";

export function useExploreState(initial: ExploreState) {
  const [state, setState] = useState(initial);
  const current = useRef(initial);
  useEffect(() => {
    const restore = () => {
      current.current = parseExploreState(new URLSearchParams(window.location.search));
      setState(current.current);
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);
  const update = useCallback((patch: Partial<ExploreState>, history: "push" | "replace" = "replace") => {
    const next = { ...current.current, ...patch };
    const search = serializeExploreState(next, new URLSearchParams(window.location.search));
    const url = `${window.location.pathname}?${search}`;
    if (url !== `${window.location.pathname}${window.location.search}`) {
      if (history === "push") window.history.pushState(null, "", url);
      else window.history.replaceState(null, "", url);
    }
    current.current = next;
    setState(next);
  }, []);
  return { state, update };
}
