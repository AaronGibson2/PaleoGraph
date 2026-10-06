"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api } from "../../lib/api/client";
import { contextKeys, contextQuery, discovery, type EntityKind, type PlacePage } from "../../lib/api/discovery";
import type { MapOccurrence, Viewport } from "../../lib/api/types";
import { TimeControl } from "../timeline/TimeControl";
import { Catalog } from "./Catalog";
import { EntityInspector } from "./EntityInspector";
import { Lineage } from "./Lineage";
import { Localities } from "./Localities";
import { Relationships } from "./Relationships";
import { Search } from "./Search";
import { DEFAULT_VIEW, FLORIDA_VIEWPORT, parseExploreState, type ExploreState } from "./state";
import { useDatasetStatus, useOccurrences, useTimeConfiguration } from "./useExploreData";
import { useExploreState } from "./useExploreState";
import { useResource } from "./useResource";
import { browseCache } from "./browseCache";
import { entityKey, occurrenceKey, type BrowseTarget } from "./browseIntent";
import "./explore.css";

const ExploreMap = dynamic(() => import("../map/ExploreMap"), { ssr: false, loading: () => <p className="map-loading" role="status">Preparing the atlas...</p> });
const EMPTY: MapOccurrence[] = [];

function ContextLink({ kind, id, identity, onRemove }: { kind: EntityKind; id: string; identity?: BrowseTarget; onRemove: () => void }) {
  const result = useResource(entityKey({kind,id}), signal => discovery.entity(kind, id, "", signal));
  const known = result.data?.entity.id===id ? result.data.entity : identity?.id===id && identity.kind===kind ? identity : undefined;
  return <span className="context-assertion"><small>{kind}</small><strong>{known?.label ?? "Reading context..."}</strong><button aria-label={`Remove ${kind} context`} onClick={onRemove}>&times;</button></span>;
}

export function ExploreWorkspace({ initial }: { initial: ExploreState }) {
  const { state, update } = useExploreState(initial);
  const [viewport, setViewport] = useState<Viewport>(FLORIDA_VIEWPORT);
  const [retry, setRetry] = useState(0);
  const catalogOpen=state.catalog==="open";
  const inspectionOpen=state.inspect!=="closed";
  const [identity,setIdentity] = useState<BrowseTarget>();
  const [selectedPosition, setSelectedPosition] = useState<{ id: string; longitude: number; latitude: number } | null>(null);
  const onPosition = useCallback((id: string, longitude: number, latitude: number) => setSelectedPosition({ id, longitude, latitude }), []);
  const focusSerial = useRef(0);
  const cameraRequest=useRef<AbortController|undefined>(undefined);
  useEffect(() => {
    const cancel = () => { focusSerial.current++; cameraRequest.current?.abort(); };
    window.addEventListener("popstate",cancel);
    return () => { window.removeEventListener("popstate",cancel); cameraRequest.current?.abort(); };
  },[]);
  const datasetGeneration=useSyncExternalStore(browseCache.subscribe,browseCache.generation,()=>0);
  const results = useOccurrences(viewport, state, retry+datasetGeneration);
  const time = useTimeConfiguration(retry+datasetGeneration);
  const dataset = useDatasetStatus(retry);
  const relationships = state.surface === "relationships";
  const surface = state.surface ?? "map";
  const mapVisible = surface === "map";
  const context = contextQuery(state).toString();
  const catalogQuery = contextQuery(state, mapVisible ? viewport : undefined).toString();
  const place = useResource<PlacePage>(state.at_lon != null ? context : null, signal => discovery.places(context, signal));
  const pointSummary=place.data?.items.find(item=>item.longitude===state.at_lon && item.latitude===state.at_lat);
  const selectedKind = state.selected_kind ?? "specimen";
  const selectedPlace = selectedKind === "specimen" && selectedPosition?.id === state.selected
    ? results.mapItems?.find(item => item.longitude === selectedPosition.longitude && item.latitude === selectedPosition.latitude)?.id
    : undefined;
  const pivot = useCallback((entity: BrowseTarget) => {
    setIdentity(entity);
    cameraRequest.current?.abort();
    const cameraAbort=new AbortController();
    cameraRequest.current=cameraAbort;
    const serial = ++focusSerial.current;
    const patch: Partial<ExploreState> = { selected: entity.id, selected_kind: entity.kind, inspect:state.surface !== "relationships" || entity.kind === "specimen" ? null : "closed" };
    if (entity.kind !== "specimen") Object.assign(patch, { [`${entity.kind}_id`]: entity.id, at_lon: null, at_lat: null });
    update(patch, "push");
    if (entity.kind === "locality" || (entity.kind === "specimen" && !entity.occurrence_id)) {
      browseCache.load(entityKey(entity),signal=>discovery.entity(entity.kind, entity.id,"",signal),cameraAbort.signal).then(async detail => {
        let lon = detail.properties.longitude;
        let lat = detail.properties.latitude;
        if (entity.kind === "specimen" && typeof detail.properties.occurrence_id === "string") {
          const occurrenceId=detail.properties.occurrence_id;
          const occurrence = await browseCache.load(occurrenceKey(occurrenceId),signal=>api.occurrence(occurrenceId,signal),cameraAbort.signal);
          lon = occurrence.longitude; lat = occurrence.latitude;
        }
        const current=parseExploreState(new URLSearchParams(window.location.search));
        if (focusSerial.current === serial && current.selected===entity.id && (current.selected_kind??"specimen")===entity.kind && (current.surface??"map")===(state.surface??"map") && typeof lon === "number" && typeof lat === "number") update({ lng: lon, lat, zoom: 10 });
      }).catch(() => { /* Inspector presents recoverable errors. */ });
    }
  }, [update, state.surface]);
  const selectPlace = useCallback((id: string) => {
    const point = results.mapItems?.find(item => item.id === id);
    if (!point) return;
    update({ at_lon: point.longitude, at_lat: point.latitude, catalog:"open" }, "push");
  }, [results.mapItems, update]);
  const onView = useCallback((view: Pick<ExploreState, "lat" | "lng" | "zoom">, bounds: Viewport) => { setViewport(bounds); update(view); }, [update]);
  const close = () => {
    if (relationships) { update({inspect:"closed"},"push"); return; }
    focusSerial.current++;
    cameraRequest.current?.abort();
    const previous = state.selected;
    update({ selected: null, selected_kind: undefined, inspect:"closed" }, "push");
    requestAnimationFrame(() => (document.getElementById(`result-${previous}`) ?? document.getElementById("catalog-toggle"))?.focus());
  };
  const active = contextKeys.slice(0, 5).filter(key => state[key]);
  const interval = time.data?.units.find(unit => unit.id === state.interval_id);
  const total = dataset.data?.current_records.toLocaleString("en-US");
  return <div className="explore-workspace">
    <header className="atlas-bar"><Link className="atlas-wordmark" href="/">Paleo<span>Graph</span><i aria-hidden="true" /></Link><span className="atlas-index">FLORIDA / 01</span>
      <Search value={state.q ?? ""} context={context} onChange={q => update({ q })} onSelect={pivot} />
      <nav className="surface-tabs" aria-label="Exploration surface"><button aria-pressed={mapVisible} onClick={() => update({ surface: "map",inspect:"closed" }, "push")}>Atlas</button><button aria-pressed={surface === "localities"} onClick={() => update({ surface: "localities",inspect:"closed" }, "push")}>Localities</button><button aria-pressed={surface === "lineage"} onClick={() => update({ surface: "lineage", lineage_focus: state.lineage_focus ?? state.taxon_id ?? null,inspect:"closed" }, "push")}>Lineage</button></nav>
    </header>
    <div className="atlas-context"><span className="context-label">EXPLORING</span>{active.length === 0 && state.older_ma === null && state.at_lon == null && <span>Florida&apos;s vertebrate collections</span>}{active.map(key => <ContextLink key={key} identity={identity} kind={key.replace("_id", "") as EntityKind} id={String(state[key])} onRemove={() => update({ [key]: null }, "push")} />)}{state.at_lon != null && <span className="context-assertion"><small>published position</small><strong>{state.at_lat}&deg;, {state.at_lon}&deg;</strong>{pointSummary && <small>{pointSummary.record_count.toLocaleString("en-US")} assertions / {pointSummary.locality_count} distinct localities / {pointSummary.interpreted_count.toLocaleString("en-US")} with numeric bounds / {(pointSummary.record_count - pointSummary.interpreted_count).toLocaleString("en-US")} unresolved{place.loading ? " / last loaded counts, updating" : place.error ? " / last loaded counts, refresh unavailable" : ""}</small>}<button aria-label="Remove place context" onClick={() => update({ at_lon: null, at_lat: null }, "push")}>&times;</button></span>}{state.older_ma !== null && <span className="context-assertion"><small>time</small><strong>{interval?.name ?? "Custom range"}</strong><button aria-label="Remove time context" onClick={() => update({ older_ma: null, younger_ma: null, interval_id: null }, "push")}>&times;</button></span>}</div>
    <div className="atlas-layout"><section className="map-workspace" aria-label={mapVisible ? "Interactive occurrence map" : surface === "lineage" ? "Interactive source classification" : surface === "localities" ? "Locality associations" : "Source-supported relationships"} data-surface={surface}>
      <div className="map-surface" aria-hidden={!mapVisible} inert={!mapVisible}><ExploreMap view={{ ...state, selected: selectedPlace ?? null }} items={results.mapItems ?? EMPTY} onView={onView} onSelect={selectPlace} /></div>
      {relationships && (state.selected ? <Relationships kind={selectedKind} id={state.selected} context={context} retry={retry} onPivot={pivot} /> : <div className="graph-welcome"><p className="eyebrow">Connections / not conjecture</p><h2>Every record has a context.</h2><p>Select museum material, a taxon or a locality to follow its source-supported relationships.</p><button onClick={() => update({catalog:"open"},"push")}>Open the museum catalog &rarr;</button></div>)}
      {surface === "localities" && <Localities id={state.locality_id} identity={identity} context={context} onClear={() => update({ locality_id: null, selected: null }, "push")} onPivot={entity => {
        setIdentity(entity);
        update({ selected: entity.id, selected_kind: entity.kind, inspect:"closed", [`${entity.kind}_id`]: entity.id, at_lon: null, at_lat: null, ...(entity.kind === "taxon" ? { surface: "lineage", lineage_focus: entity.id } : {}) }, "push");
      }} onAtlas={() => update({ surface: "map" }, "push")} onLineage={() => update({ surface: "lineage", lineage_focus: state.taxon_id ?? null, inspect:"closed" }, "push")} onMaterial={() => update({catalog:"open"},"push")} />}
      {surface === "lineage" && <Lineage focus={state.lineage_focus} activeTaxon={state.taxon_id} context={context} age={state} intervals={time.data?.units ?? []} onFocus={lineage_focus => update({ lineage_focus }, "push")} onSelect={pivot} onAtlas={taxon_id => { setViewport(FLORIDA_VIEWPORT); update({ ...DEFAULT_VIEW, surface: "map", taxon_id, inspect:"closed" }, "push"); }} onLocalities={taxon_id => update({ surface: "localities", taxon_id, inspect:"closed" }, "push")} onMaterial={taxon_id => update({ taxon_id,catalog:"open" },"push")} />}
      <div className="canvas-toolbar"><button id="catalog-toggle" aria-expanded={catalogOpen} onClick={() => update({catalog:catalogOpen?null:"open"},"push")}><span aria-hidden="true">&#8801;</span> Museum catalog</button><button onClick={() => { setViewport(FLORIDA_VIEWPORT); update(DEFAULT_VIEW, "push"); }}>Return to Florida</button></div>
      {mapVisible && <div className="map-legend"><span><i className="legend-stack" />Counts represent catalog assertions</span><span><i className="legend-point unknown" />Age unresolved</span><span><i className="legend-ring" />Generalized location</span></div>}
      <Catalog open={catalogOpen} query={catalogQuery} onSelect={pivot} onClose={() => update({catalog:null},"push")} retry={retry} />
      {relationships && state.selected && !inspectionOpen && <button className="graph-inspect" onClick={() => update({inspect:null},"push")}>Inspect selected {selectedKind} ↗</button>}
      {state.selected && inspectionOpen && <EntityInspector kind={selectedKind} id={state.selected} identity={identity} context={context} viewport={viewport} onPivot={pivot} onClose={close} onPosition={onPosition} onInterval={interval => update({ older_ma: interval.older_ma, younger_ma: interval.younger_ma, interval_id: interval.id, time_focus: interval.parent ?? interval.id }, "push")} onLocality={() => update({ surface: "localities",inspect:"closed" }, "push")} onLineage={() => update({ surface: "lineage", lineage_focus: selectedKind === "taxon" ? state.selected : state.taxon_id ?? null,inspect:"closed" }, "push")} onGraph={() => update({ surface: "relationships",inspect:"closed" }, "push")} retry={retry} />}
      {mapVisible && (results.loading || results.error) && <div className="map-status" role={results.error ? "alert" : "status"}>{results.error ? "Map data unavailable. Last loaded positions retained." : results.data ? "Updating - last loaded positions remain visible" : "Reading local museum material..."}{results.error && <button onClick={() => setRetry(value => value + 1)}>Retry data</button>}</div>}
      <div className="canvas-source"><a href="https://ipt.floridamuseum.ufl.edu/ipt/resource?r=ufvp" target="_blank" rel="noopener noreferrer">{dataset.data?.creator ? `${dataset.data.creator} / ` : ""}Florida Museum / UFVP</a><a href="https://creativecommons.org/licenses/by-nc/4.0/">CC BY-NC 4.0</a><span role={dataset.error ? "status" : undefined}>{total ? `${dataset.error ? "Last loaded import status / refresh unavailable / " : ""}${total} assertions / ${dataset.data?.latest_scope?.startsWith("florida-sample") ? "bounded import" : dataset.data?.latest_status ?? "import status unknown"} / v${dataset.data?.version}` : dataset.error ? "Import status unavailable" : "Local import status pending"}</span></div>
    </section></div>
    {time.data ? <TimeControl age={state} configuration={time.data} focus={state.time_focus} onFocus={time_focus => update({ time_focus }, "push")} onChange={(age, interval_id) => update({ ...age, interval_id: interval_id ?? null }, "push")} /> : <div className="time-unavailable" role="status">{time.error ?? "Reading geological time..."}</div>}
  </div>;
}
