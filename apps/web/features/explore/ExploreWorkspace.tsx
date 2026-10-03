"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import { api } from "../../lib/api/client";
import { contextKeys, contextQuery, discovery, type EntityKind, type EntityRef, type PlacePage } from "../../lib/api/discovery";
import type { MapOccurrence, Viewport } from "../../lib/api/types";
import { TimeControl } from "../timeline/TimeControl";
import { Catalog } from "./Catalog";
import { EntityInspector } from "./EntityInspector";
import { Relationships } from "./Relationships";
import { Search } from "./Search";
import { DEFAULT_VIEW, FLORIDA_VIEWPORT, type ExploreState } from "./state";
import { useDatasetStatus, useOccurrences, useTimeConfiguration } from "./useExploreData";
import { useExploreState } from "./useExploreState";
import { useResource } from "./useResource";
import "./explore.css";

const ExploreMap = dynamic(() => import("../map/ExploreMap"), { ssr: false, loading: () => <p className="map-loading" role="status">Preparing the atlas...</p> });
const EMPTY: MapOccurrence[] = [];

function ContextLink({ kind, id, onRemove }: { kind: EntityKind; id: string; onRemove: () => void }) {
  const result = useResource(`${kind}:${id}`, signal => discovery.entity(kind, id, "", signal));
  return <span className="context-assertion"><small>{kind}</small><strong>{result.data?.entity.label ?? "Reading context..."}</strong><button aria-label={`Remove ${kind} context`} onClick={onRemove}>&times;</button></span>;
}

export function ExploreWorkspace({ initial }: { initial: ExploreState }) {
  const { state, update } = useExploreState(initial);
  const [viewport, setViewport] = useState<Viewport>(FLORIDA_VIEWPORT);
  const [retry, setRetry] = useState(0);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [inspectionOpen, setInspectionOpen] = useState(true);
  const [selectedPosition, setSelectedPosition] = useState<{ id: string; longitude: number; latitude: number } | null>(null);
  const onPosition = useCallback((id: string, longitude: number, latitude: number) => setSelectedPosition({ id, longitude, latitude }), []);
  const focusSerial = useRef(0);
  const results = useOccurrences(viewport, state, retry);
  const time = useTimeConfiguration(retry);
  const dataset = useDatasetStatus(retry);
  const relationships = state.surface === "relationships";
  const context = contextQuery(state).toString();
  const catalogQuery = contextQuery(state, viewport).toString();
  const place = useResource<PlacePage>(state.at_lon != null ? context : null, signal => discovery.places(context, signal));
  const selectedKind = state.selected_kind ?? "specimen";
  const selectedPlace = selectedKind === "specimen" && selectedPosition?.id === state.selected
    ? results.mapItems?.find(item => item.longitude === selectedPosition.longitude && item.latitude === selectedPosition.latitude)?.id
    : undefined;
  const pivot = useCallback((entity: EntityRef) => {
    setInspectionOpen(state.surface !== "relationships" || entity.kind === "specimen");
    const serial = ++focusSerial.current;
    const patch: Partial<ExploreState> = { selected: entity.id, selected_kind: entity.kind };
    if (entity.kind !== "specimen") Object.assign(patch, { [`${entity.kind}_id`]: entity.id, at_lon: null, at_lat: null });
    update(patch, "push");
    if (entity.kind === "locality" || entity.kind === "specimen") {
      discovery.entity(entity.kind, entity.id).then(async detail => {
        let lon = detail.properties.longitude;
        let lat = detail.properties.latitude;
        if (entity.kind === "specimen" && typeof detail.properties.occurrence_id === "string") {
          const occurrence = await api.occurrence(detail.properties.occurrence_id);
          lon = occurrence.longitude; lat = occurrence.latitude;
        }
        if (focusSerial.current === serial && typeof lon === "number" && typeof lat === "number") update({ lng: lon, lat, zoom: 10 });
      }).catch(() => { /* Inspector presents recoverable errors. */ });
    }
  }, [update, state.surface]);
  const selectPlace = useCallback((id: string) => {
    const point = results.mapItems?.find(item => item.id === id);
    if (!point) return;
    update({ at_lon: point.longitude, at_lat: point.latitude }, "push");
    setCatalogOpen(true);
  }, [results.mapItems, update]);
  const onView = useCallback((view: Pick<ExploreState, "lat" | "lng" | "zoom">, bounds: Viewport) => { setViewport(bounds); update(view); }, [update]);
  const close = () => {
    if (relationships) { setInspectionOpen(false); return; }
    focusSerial.current++;
    const previous = state.selected;
    update({ selected: null, selected_kind: undefined }, "push");
    requestAnimationFrame(() => (document.getElementById(`result-${previous}`) ?? document.getElementById("catalog-toggle"))?.focus());
  };
  const active = contextKeys.slice(0, 5).filter(key => state[key]);
  const interval = time.data?.units.find(unit => unit.id === state.interval_id);
  const total = dataset.data?.current_records.toLocaleString("en-US");
  return <div className="explore-workspace">
    <header className="atlas-bar"><Link className="atlas-wordmark" href="/">Paleo<span>Graph</span><i aria-hidden="true" /></Link><span className="atlas-index">FLORIDA / 01</span>
      <Search value={state.q ?? ""} context={context} onChange={q => update({ q })} onSelect={pivot} />
      <nav className="surface-tabs" aria-label="Exploration surface"><button aria-pressed={!relationships} onClick={() => update({ surface: "map" }, "push")}>Map</button><button aria-pressed={relationships} onClick={() => update({ surface: "relationships" }, "push")}>Relationships</button></nav>
    </header>
    <div className="atlas-context"><span className="context-label">EXPLORING</span>{active.length === 0 && state.older_ma === null && state.at_lon == null && <span>Florida&apos;s vertebrate collections</span>}{active.map(key => <ContextLink key={key} kind={key.replace("_id", "") as EntityKind} id={String(state[key])} onRemove={() => update({ [key]: null }, "push")} />)}{state.at_lon != null && <span className="context-assertion"><small>published position</small><strong>{state.at_lat}&deg;, {state.at_lon}&deg;</strong>{place.data?.items[0] && <small>{place.data.items[0].record_count.toLocaleString("en-US")} assertions / {place.data.items[0].locality_count} distinct localities</small>}<button aria-label="Remove place context" onClick={() => update({ at_lon: null, at_lat: null }, "push")}>&times;</button></span>}{state.older_ma !== null && <span className="context-assertion"><small>time</small><strong>{interval?.name ?? "Custom range"}</strong><button aria-label="Remove time context" onClick={() => update({ older_ma: null, younger_ma: null, interval_id: null }, "push")}>&times;</button></span>}</div>
    <div className="atlas-layout"><section className="map-workspace" aria-label="Interactive occurrence map" data-surface={relationships ? "relationships" : "map"}>
      <div className="map-surface" aria-hidden={relationships} inert={relationships}><ExploreMap view={{ ...state, selected: selectedPlace ?? null }} items={results.mapItems ?? EMPTY} onView={onView} onSelect={selectPlace} /></div>
      {relationships && (state.selected ? <Relationships kind={selectedKind} id={state.selected} context={context} retry={retry} onPivot={pivot} /> : <div className="graph-welcome"><p className="eyebrow">Connections / not conjecture</p><h2>Every record has a context.</h2><p>Select museum material, a taxon or a locality to follow its source-supported relationships.</p><button onClick={() => setCatalogOpen(true)}>Open the museum catalog &rarr;</button></div>)}
      <div className="canvas-toolbar"><button id="catalog-toggle" aria-expanded={catalogOpen} onClick={() => setCatalogOpen(value => !value)}><span aria-hidden="true">&#8801;</span> Museum catalog</button><button onClick={() => { setViewport(FLORIDA_VIEWPORT); update(DEFAULT_VIEW, "push"); }}>Return to Florida</button></div>
      {!relationships && <div className="map-legend"><span><i className="legend-stack" />Counts represent catalog assertions</span><span><i className="legend-point unknown" />Age unresolved</span><span><i className="legend-ring" />Generalized location</span></div>}
      {catalogOpen && <Catalog query={catalogQuery} onSelect={pivot} onClose={() => setCatalogOpen(false)} retry={retry} />}
      {relationships && state.selected && !inspectionOpen && <button className="graph-inspect" onClick={() => setInspectionOpen(true)}>Inspect selected {selectedKind} ↗</button>}
      {state.selected && inspectionOpen && <EntityInspector kind={selectedKind} id={state.selected} context={context} viewport={viewport} onPivot={pivot} onClose={close} onPosition={onPosition} onInterval={interval => update({ older_ma: interval.older_ma, younger_ma: interval.younger_ma, interval_id: interval.id, time_focus: interval.parent ?? interval.id }, "push")} onGraph={() => { setInspectionOpen(false); update({ surface: "relationships" }, "push"); }} retry={retry} />}
      {(results.loading || results.error) && <div className="map-status" role={results.error ? "alert" : "status"}>{results.error ? "Map data unavailable. Last loaded positions retained." : results.data ? "Updating - last loaded positions remain visible" : "Reading local museum material..."}{results.error && <button onClick={() => setRetry(value => value + 1)}>Retry data</button>}</div>}
      <div className="canvas-source"><a href="https://ipt.floridamuseum.ufl.edu/ipt/resource?r=ufvp" target="_blank" rel="noopener noreferrer">{dataset.data?.creator ? `${dataset.data.creator} / ` : ""}Florida Museum / UFVP</a><a href="https://creativecommons.org/licenses/by-nc/4.0/">CC BY-NC 4.0</a><span>{total ? `${total} assertions / ${dataset.data?.latest_scope?.startsWith("florida-sample") ? "bounded import" : dataset.data?.latest_status ?? "import status unknown"} / v${dataset.data?.version}` : "Local import status pending"}</span></div>
    </section></div>
    {time.data ? <TimeControl age={state} configuration={time.data} focus={state.time_focus} onFocus={time_focus => update({ time_focus }, "push")} onChange={(age, interval_id) => update({ ...age, interval_id: interval_id ?? null }, "push")} /> : <div className="time-unavailable" role="status">{time.error ?? "Reading geological time..."}</div>}
  </div>;
}
