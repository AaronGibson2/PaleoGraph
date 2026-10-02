"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import type { MapOccurrence, Viewport } from "../../lib/api/types";
import { TimeControl } from "../timeline/TimeControl";
import { OccurrenceInspector } from "./OccurrenceInspector";
import { OccurrenceList } from "./OccurrenceList";
import { DEFAULT_VIEW, FLORIDA_VIEWPORT, type ExploreState } from "./state";
import { useOccurrence, useOccurrences, useTimeConfiguration } from "./useExploreData";
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
      <div><p className="eyebrow">Field atlas / Florida</p><h1>Life, through time.</h1></div>
      <p className="demo-badge"><span aria-hidden="true">◈</span> Synthetic demo data</p>
    </div>
    <div className="atlas-layout">
      <section className="results-panel" aria-labelledby="results-heading">
        <div className="results-intro"><p className="eyebrow">In this view</p><h2 id="results-heading" tabIndex={-1}>Occurrence records</h2>
          <p className="result-count" role="status" aria-live="polite">{results.loading ? "Updating occurrences…" : results.error ? "Data unavailable" : `${results.data?.returned ?? 0} assertions${results.data?.truncated ? " · results capped" : ""}`}</p>
        </div>
        {results.error && <div className="panel-message" role="alert"><p>{results.error}</p><button className="quiet-button" onClick={retryData}>Retry data</button></div>}
        {!results.loading && !results.error && items.length === 0 && <p className="panel-message">No occurrences in this view and age range. Try another time window or return to Florida.</p>}
        {results.data?.truncated && <p className="panel-message">Showing the first {results.data.limit} records. Zoom in or narrow the age range to see a complete result set.</p>}
        <OccurrenceList items={items} selected={state.selected} onSelect={select} />
        <p className="results-footnote">Invented records for development. Absence of a record is not evidence of fossil absence.</p>
      </section>
      <section className="map-workspace" aria-label="Interactive occurrence map">
        <ExploreMap view={state} items={items} onView={onView} onSelect={select} />
        <div className="map-caption"><span>Florida / present-day geography</span><button onClick={() => { setViewport(FLORIDA_VIEWPORT); update(DEFAULT_VIEW, "push"); }}>Return to Florida</button></div>
        <div className="map-legend"><span><i className="legend-point" />Known age</span><span><i className="legend-point unknown" />Unknown / partial age</span><span><i className="legend-ring" />Generalized location</span></div>
        {state.selected && <OccurrenceInspector selected={state.selected} data={inspection.data} error={inspection.error} outsideResults={!results.loading && !items.some(item => item.id === state.selected)} onClose={close} onRetry={retryData} />}
      </section>
    </div>
    {time.data ? <TimeControl age={state} configuration={time.data} onChange={age => update(age)} /> : <div className="time-unavailable" role="status"><p>{time.error ? "Time controls could not load." : "Loading geological time controls…"}</p>{time.error && <button className="quiet-button" onClick={retryData}>Retry time controls</button>}</div>}
  </div>;
}
