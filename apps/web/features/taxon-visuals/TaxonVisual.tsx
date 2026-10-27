"use client";

import { useSyncExternalStore } from "react";
import { archetypeAssets } from "./assets";
import { generalGlyphs, unassignedGlyph } from "./glyphs";
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

/** Decorative renderer. Scientific rules stay in resolve.ts; one load per static URL. */
export function TaxonVisual({ visual }: { visual: ResolvedTaxonVisual }) {
  const asset = visual.kind === "archetype" ? archetypeAssets[visual.archetype] : undefined;
  const src = asset?.src ?? "";
  const status = useSyncExternalStore(listener => subscribe(src, listener), () => images.get(src)?.status ?? "pending", () => "pending");
  const masked = Boolean(src) && status === "ready";
  const kind = masked ? "archetype" : visual.kind === "generic" ? "generic" : "neutral";
  return <span className={`taxon-icon taxon-visual taxon-icon-${visual.kind === "generic" ? visual.visual : masked && visual.kind === "archetype" ? visual.archetype : "unassigned"}`} aria-hidden="true" data-visual-kind={kind} data-archetype={masked && visual.kind === "archetype" ? visual.archetype : undefined} data-generic={visual.kind === "generic" ? visual.visual : undefined} data-asset-status={src ? status : undefined}>
    {masked ? <span className="taxon-visual-mask" style={{ maskImage: `url("${src}")`, WebkitMaskImage: `url("${src}")` }} /> : <svg viewBox="0 0 128 96" focusable="false"><path d={visual.kind === "generic" ? generalGlyphs[visual.visual] : unassignedGlyph} fill="currentColor" fillRule={visual.kind === "generic" ? "evenodd" : "nonzero"} /></svg>}
  </span>;
}
