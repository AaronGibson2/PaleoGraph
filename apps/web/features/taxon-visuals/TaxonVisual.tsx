"use client";

import { useSyncExternalStore } from "react";
import { archetypeAssets } from "./assets";
import type { ResolvedTaxonVisual } from "./types";

type Status = "pending" | "ready" | "failed";
const images = new Map<string, { status: Status; listeners: Set<() => void>; image: HTMLImageElement }>();
function subscribe(src: string, listener: () => void) {
  if (!src) return () => {};
  let entry = images.get(src);
  if (!entry) {
    const image = new Image();
    entry = { status: "pending", listeners: new Set(), image };
    images.set(src, entry);
    const settle = (status: Status) => {
      entry!.status = status;
      for (const notify of entry!.listeners) notify();
    };
    image.onload = () => settle("ready");
    image.onerror = () => settle("failed");
    image.src = src;
  }
  entry.listeners.add(listener);
  return () => { entry.listeners.delete(listener); };
}
const mammal = "M8 31 Q18 12 41 18 L49 10 53 19 63 24 61 31 50 30 46 44 41 44 42 31 26 32 22 44 17 44 18 30 11 34 3 23 7 21Z";
const neutral = "M32 10 54 28 32 46 10 28Z M32 20 42 28 32 36 22 28Z";

/** Decorative renderer. Scientific rules stay in resolve.ts; one load per static URL. */
export function TaxonVisual({ visual }: { visual: ResolvedTaxonVisual }) {
  const asset = visual.kind === "archetype" ? archetypeAssets[visual.archetype] : undefined;
  const src = asset?.src ?? "";
  const status = useSyncExternalStore(listener => subscribe(src, listener), () => images.get(src)?.status ?? "pending", () => "pending");
  const masked = Boolean(src) && status === "ready";
  const kind = masked ? "archetype" : visual.kind === "generic" ? "generic" : "neutral";
  return <span className={`taxon-icon taxon-visual taxon-icon-${kind === "generic" ? "mammal" : kind === "neutral" ? "unassigned" : visual.kind === "archetype" ? visual.archetype : "unassigned"}`} aria-hidden="true" data-visual-kind={kind} data-archetype={masked && visual.kind === "archetype" ? visual.archetype : undefined} data-asset-status={src ? status : undefined}>
    {masked ? <span className="taxon-visual-mask" style={{ maskImage: `url("${src}")`, WebkitMaskImage: `url("${src}")` }} /> : <svg viewBox="0 0 68 56" focusable="false"><path d={kind === "generic" ? mammal : neutral} fill="currentColor" fillRule="evenodd" /></svg>}
  </span>;
}
