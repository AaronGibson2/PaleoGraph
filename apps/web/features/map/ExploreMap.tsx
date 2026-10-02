"use client";

import { useEffect, useRef, useState } from "react";
import { Map, NavigationControl, Popup, ScaleControl, setWorkerUrl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { MapOccurrence, Viewport } from "../../lib/api/types";
import { normalizeViewport, type ExploreState } from "../explore/state";
import { addOccurrenceLayers, updateOccurrences } from "./layers";

// Both worker modules are copied from the locked dependency before dev/build.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");
const styleUrl = process.env.NEXT_PUBLIC_MAP_STYLE_URL ?? "/styles/paleograph.json";

type Props = {
  view: ExploreState;
  items: MapOccurrence[];
  onView: (view: Pick<ExploreState, "lat" | "lng" | "zoom">, bounds: Viewport) => void;
  onSelect: (id: string) => void;
};

export default function ExploreMap(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<Map | null>(null);
  const latest = useRef(props);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { latest.current = props; }, [props]);

  useEffect(() => {
    if (!container.current) return;
    let map: Map;
    let cancelled = false;
    const hover = new Popup({ closeButton: false, closeOnClick: false, offset: 12 });
    try {
      const view = latest.current.view;
      map = new Map({
        container: container.current,
        style: styleUrl || { version: 8, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#dfe7e3" } }] },
        center: [view.lng, view.lat], zoom: view.zoom, minZoom: 1, maxZoom: 18,
        attributionControl: { compact: true }, dragRotate: false, touchPitch: false,
      });
      instance.current = map;
      map.addControl(new NavigationControl({ showCompass: false }), "top-right");
      map.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
      map.getCanvas().setAttribute("aria-label", "Occurrence map. Use arrow keys to pan and plus or minus to zoom. All records are also in the results list.");
      const publishView = () => {
        const center = map.getCenter();
        const bounds = map.getBounds();
        latest.current.onView(
          { lat: Number(center.lat.toFixed(5)), lng: Number(center.wrap().lng.toFixed(5)), zoom: Number(map.getZoom().toFixed(2)) },
          normalizeViewport(bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()),
        );
      };
      map.on("moveend", publishView);
      map.on("style.load", () => {
        if (cancelled) return;
        addOccurrenceLayers(map);
        updateOccurrences(map, latest.current.items, latest.current.view.selected);
        publishView();
      });
      map.on("error", () => {
        if (!cancelled) setError("Some basemap content could not load. You can still explore the results list.");
      });
      map.on("click", "occurrence-points", event => {
        const features = event.features ?? [];
        if (features.length === 1 && typeof features[0].properties.id === "string") {
          latest.current.onSelect(features[0].properties.id);
          return;
        }
        // Co-located assertions remain individually selectable, without fake point jitter.
        const choices = document.createElement("div");
        const heading = document.createElement("strong");
        heading.textContent = "Loaded assertions at this place";
        choices.append(heading);
        const popup = new Popup({ offset: 14 });
        for (const feature of features) {
          const id: unknown = feature.properties.id;
          if (typeof id !== "string") continue;
          const button = document.createElement("button");
          button.className = "map-choice";
          button.textContent = [feature.properties.catalog, feature.properties.name].filter(Boolean).join(" / ");
          button.onclick = () => { latest.current.onSelect(id); popup.remove(); };
          choices.append(button);
        }
        popup.setLngLat(event.lngLat).setDOMContent(choices).addTo(map);
      });
      map.on("mousemove", "occurrence-points", event => {
        map.getCanvas().style.cursor = "pointer";
        const count = event.features?.length ?? 0;
        const label = count > 1 ? `${count} loaded assertions at this place · click to choose` : `${event.features?.[0]?.properties.name ?? "Occurrence"} · click to inspect`;
        hover.setLngLat(event.lngLat).setText(label).addTo(map);
      });
      map.on("mouseleave", "occurrence-points", () => { map.getCanvas().style.cursor = ""; hover.remove(); });
      const resize = new ResizeObserver(() => map.resize());
      resize.observe(container.current);
      return () => { cancelled = true; resize.disconnect(); hover.remove(); map.remove(); instance.current = null; };
    } catch {
      queueMicrotask(() => { if (!cancelled) setError("The map needs WebGL to render. Use the complete textual results below."); });
      return () => { cancelled = true; instance.current?.remove(); instance.current = null; };
    }
  }, []);

  useEffect(() => {
    const map = instance.current;
    if (!map) return;
    updateOccurrences(map, props.items, props.view.selected);
  }, [props.items, props.view.selected]);

  useEffect(() => {
    const map = instance.current;
    if (!map) return;
    const center = map.getCenter().wrap();
    if (Math.abs(center.lng - props.view.lng) > 0.0001 || Math.abs(center.lat - props.view.lat) > 0.0001 || Math.abs(map.getZoom() - props.view.zoom) > 0.015) {
      map.jumpTo({ center: [props.view.lng, props.view.lat], zoom: props.view.zoom });
    }
  }, [props.view.lat, props.view.lng, props.view.zoom]);

  return <>
    <div className="map-canvas" ref={container} />
    {(error || !styleUrl) && <div className="map-notice" role="status">
      {error ?? "No basemap configured. Occurrence points and the results list remain available."}
    </div>}
  </>;
}
