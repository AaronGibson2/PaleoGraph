"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import type { MapOccurrence, Viewport } from "../../lib/api/types";
import { TimeControl } from "../timeline/TimeControl";
import { OccurrenceInspector } from "./OccurrenceInspector";
import { OccurrenceList } from "./OccurrenceList";
import { DEFAULT_VIEW, FLORIDA_VIEWPORT, type ExploreState } from "./state";
import { useDatasetStatus, useOccurrence, useOccurrences, useTimeConfiguration } from "./useExploreData";
import { useExploreState } from "./useExploreState";
import "./explore.css";

const ExploreMap = dynamic(() => import("../map/ExploreMap"), { ssr: false, loading: () => <p className="map-loading" role="status">Preparing the atlas…</p> });
const EMPTY: MapOccurrence[] = [];

export function ExploreWorkspace({ initial }: { initial: ExploreState }) {
  const { state, update } = useExploreState(initial);
  const [viewport, setViewport] = useState<Viewport>(FLORIDA_VIEWPORT);
  const [retry, setRetry] = useState(0);
  const results = useOccurrences(viewport, state, retry);
  const inspection = useOccurrence(state.selected, retry);
  const time = useTimeConfiguration(retry);
  const dataset = useDatasetStatus(retry);
  const demo = state.data_mode === "demo";
  const items = results.data?.items ?? EMPTY;
  const select = useCallback((id: string) => update({ selected: id }, "push"), [update]);
  const onView = useCallback((view: Pick<ExploreState, "lat" | "lng" | "zoom">, bounds: Viewport) => {
    setViewport(bounds);
    update(view);
  }, [update]);
  const close = () => {
    const previous = state.selected;
    update({ selected: null }, "push");
    requestAnimationFrame(() => (document.getElementById(`result-${previous}`) ?? document.getElementById("results-heading"))?.focus());
  };
  const retryData = () => setRetry(value => value + 1);
  return <div className="explore-workspace">
    <div className="explore-heading">
      <div><p className="eyebrow">PaleoGraph atlas · Florida / 01</p><h1>The vertebrate record.</h1></div>
      <div className="atlas-edition"><p className="demo-badge">{demo ? "Synthetic demo data" : "Florida Museum · UFVP"}</p><a href={demo ? "/explore" : "/explore?data_mode=demo"}>{demo ? "Explore museum records" : "Open synthetic demo"}</a></div>
    </div>
    <div className="source-strip">{demo ? <p>Invented development records · separate from museum data</p> : <><p><a href="https://ipt.floridamuseum.ufl.edu/ipt/resource?r=ufvp" target="_blank" rel="noopener noreferrer">Florida Museum of Natural History</a> / Vertebrate Paleontology{dataset.data?.creator && ` / ${dataset.data.creator}`}</p><p>{dataset.data ? `${dataset.data.current_records.toLocaleString("en-US")} catalog assertions · ${dataset.data.mapped_records.toLocaleString("en-US")} with usable coordinates · ${dataset.data.latest_scope?.startsWith("florida-sample") ? `bounded import / ${dataset.data.latest_status}` : dataset.data.latest_status ?? "not imported"} · v${dataset.data.version ?? "unknown"}` : dataset.error ? "Import status unavailable" : "Reading local collection status…"}</p><a href="https://creativecommons.org/licenses/by-nc/4.0/" target="_blank" rel="noopener noreferrer">CC BY-NC 4.0</a></>}</div>
    <div className="atlas-layout">
      <section className="results-panel" aria-labelledby="results-heading">
        <div className="results-intro"><p className="eyebrow">In this view</p><h2 id="results-heading" tabIndex={-1}>Occurrence records</h2>
          <p className="result-count" role="status" aria-live="polite">{results.data ? `${results.data.returned} assertions${results.data.truncated ? " · results capped" : ""}${results.loading ? " · Updating…" : results.error ? " · last loaded" : ""}` : results.loading ? "Loading occurrences…" : "Data unavailable"}</p>
          <p className="continuity-note">{(results.loading || results.error) && results.data ? "Showing last loaded results." : "\u00a0"}</p>
        </div>
        {results.error && <div className="panel-message" role="alert"><p>{results.error}</p><button className="quiet-button" onClick={retryData}>Retry data</button></div>}
        {!results.loading && !results.error && items.length === 0 && <p className="panel-message">No occurrences in this view and age range. Try another time window or return to Florida.</p>}
        {results.data?.truncated && <p className="panel-message">Showing the first {results.data.limit} loaded assertions. Zoom in to refine the view; co-located catalog records may still exceed this limit.</p>}
        <OccurrenceList items={items} selected={state.selected} onSelect={select} />
        <p className="results-footnote">{demo ? "Invented records for development. " : "Catalog entries can contain multiple pieces. "}Absence of a record is not evidence of fossil absence.</p>
      </section>
      <section className="map-workspace" aria-label="Interactive occurrence map">
        <ExploreMap view={state} items={results.mapItems ?? EMPTY} onView={onView} onSelect={select} />
        <div className="map-caption"><span>Florida / present-day geography</span><button onClick={() => { setViewport(FLORIDA_VIEWPORT); update(DEFAULT_VIEW, "push"); }}>Return to Florida</button></div>
        <div className="map-legend"><span><i className="legend-point" />Numeric age</span><span><i className="legend-point unknown" />Numeric age unknown</span><span><i className="legend-stack" />Co-located records</span><span><i className="legend-ring" />Generalized location</span></div>
        {state.selected && <OccurrenceInspector selected={state.selected} data={inspection.data} error={inspection.error} outsideResults={!results.loading && !results.error && !items.some(item => item.id === state.selected)} onClose={close} onRetry={retryData} />}
      </section>
    </div>
    {time.data ? <TimeControl age={state} configuration={time.data} onChange={age => update(age, "push")} /> : <div className="time-unavailable" role="status"><p>{time.error ? "Time controls could not load." : "Loading geological time controls…"}</p>{time.error && <button className="quiet-button" onClick={retryData}>Retry time controls</button>}</div>}
    {!demo && <p className="source-age-note">UFVP supplies geological names, not numeric Ma bounds. All ages includes these records; a numeric range excludes them. Source labels remain in the catalog inspector. Positions are published museum coordinates, with source uncertainty where supplied.</p>}
  </div>;
}
