"use client";

import { useEffect, useRef } from "react";
import type { DatasetStatus } from "../../lib/api/types";
import "./atlas-sources.css";

export function AtlasSources({ dataset, error }: { dataset?: DatasetStatus; error?: string }) {
  const disclosure = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const close = () => {
    if (disclosure.current) disclosure.current.open = false;
    summary.current?.focus();
  };
  useEffect(() => {
    const dismiss = (event: PointerEvent) => {
      const element = disclosure.current;
      if (element?.open && event.target instanceof Node && !element.contains(event.target)) element.open = false;
    };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, []);
  const total = dataset?.current_records.toLocaleString("en-US");
  return <details className="atlas-source-information" ref={disclosure} onKeyDown={event => {
    if (event.key === "Escape" && disclosure.current?.open) { event.stopPropagation(); close(); }
  }}>
    <summary ref={summary}><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7.5" /><path d="M10 9v5m0-8v1" /></svg>Sources &amp; data</summary>
    <section className="atlas-source-sheet" aria-labelledby="atlas-sources-heading">
      <header><div><p className="eyebrow">Behind the evidence</p><h2 id="atlas-sources-heading">Sources &amp; data</h2></div><button type="button" aria-label="Close sources and data" onClick={close}>&times;</button></header>
      <p className="atlas-source-intro">Museum material and published occurrences retain their own sources, rights, and uncertainty.</p>
      <section aria-labelledby="atlas-ufvp-heading"><h3 id="atlas-ufvp-heading">Florida Museum / UFVP</h3><p>{dataset?.creator ?? "University of Florida Vertebrate Paleontology"}</p><div className="atlas-source-links"><a href="https://ipt.floridamuseum.ufl.edu/ipt/resource?r=ufvp" target="_blank" rel="noopener noreferrer">Source dataset ↗</a><a href="https://creativecommons.org/licenses/by-nc/4.0/" target="_blank" rel="noopener noreferrer">CC BY-NC 4.0 ↗</a></div><p>Attribution and noncommercial use. A museum assertion may describe multiple pieces.</p></section>
      <section aria-labelledby="atlas-pbdb-heading"><h3 id="atlas-pbdb-heading">Paleobiology Database</h3><div className="atlas-source-links"><a href="https://paleobiodb.org/" target="_blank" rel="noopener noreferrer">PBDB ↗</a><a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener noreferrer">CC0 1.0 ↗</a></div><p>Published occurrence evidence. Source references remain available in each record’s dossier.</p></section>
      <section aria-labelledby="atlas-dataset-heading"><h3 id="atlas-dataset-heading">Retained dataset</h3><dl><div><dt>Museum assertions</dt><dd>{total ?? "Not available"}</dd></div><div><dt>UFVP version</dt><dd>{dataset?.version ?? "Not available"}</dd></div><div><dt>Published occurrences</dt><dd>{dataset?.published_occurrences?.toLocaleString("en-US") ?? "Not available"}</dd></div></dl><p className="source-import-status" role={error ? "status" : undefined}>{total ? `${error ? "Last loaded import status / refresh unavailable / " : ""}${total} assertions / ${dataset?.latest_scope?.startsWith("florida-sample") ? "bounded import" : dataset?.latest_status ?? "import status unknown"} / v${dataset?.version ?? "unknown"}` : error ? "Import status unavailable" : "Local import status pending"}</p></section>
      <p className="atlas-source-map-note">Geographic map credits are available in the map’s attribution control. Geological reference credits remain with the timeline.</p>
    </section>
  </details>;
}
