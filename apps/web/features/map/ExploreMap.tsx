"use client";

import { useEffect, useRef, useState } from "react";
import { Map, NavigationControl, Popup, ScaleControl, setWorkerUrl, type GeoJSONSource } from "maplibre-gl";
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
  preview: string | null;
  reset: number;
  onPreview: (id: string | null) => void;
  onView: (view: Pick<ExploreState, "lat" | "lng" | "zoom">, bounds: Viewport) => void;
  onSelect: (id: string) => void;
};

function frameFlorida(map: Map) {
  const narrow = map.getContainer().clientWidth < 768;
  map.fitBounds([[-87.7, 24.4], [-79.8, 31.05]], { padding: narrow ? {top:110,bottom:110,left:24,right:24} : {top:32,bottom:64,left:330,right:76}, duration: 0 });
}

export default function ExploreMap(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<Map | null>(null);
  const previewPopup = useRef<Popup | null>(null);
  const latest = useRef(props);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { latest.current = props; }, [props]);

  useEffect(() => {
    if (!container.current) return;
    let map: Map;
    let cancelled = false;
    const hover = new Popup({ closeButton: false, closeOnClick: false, offset: 18, className: "atlas-hover-preview", maxWidth: "260px" });
    previewPopup.current = hover;
    try {
      const view = latest.current.view;
      let frameOnLoad = !["lat", "lng", "zoom"].some(key => new URLSearchParams(window.location.search).has(key));
      map = new Map({
        container: container.current,
        style: styleUrl || { version: 8, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#dfe7e3" } }] },
        center: [view.lng, view.lat], zoom: view.zoom, minZoom: 1, maxZoom: 18,
        attributionControl: { compact: true }, dragRotate: false, touchPitch: false,
      });
      instance.current = map;
      map.addControl(new NavigationControl({ showCompass: false }), "top-right");
      map.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
      map.getCanvas().setAttribute("aria-label", "Occurrence map. Use arrow keys to pan and plus or minus to zoom. Use Mapped positions for keyboard-accessible previews and selection, or open the evidence catalog.");
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
        if (frameOnLoad) { frameOnLoad = false; frameFlorida(map); }
        addOccurrenceLayers(map);
        container.current?.setAttribute("data-map-stage", "style");
        performance.mark("paleograph-atlas-style");
        updateOccurrences(map, latest.current.items, latest.current.view.selected);
        publishView();
      });
      map.once("idle", () => { container.current?.setAttribute("data-map-stage", "ready"); performance.mark("paleograph-atlas-ready"); });
      map.on("error", () => {
        if (!cancelled) setError("Some basemap content could not load. You can still explore the results list.");
      });
      map.on("click", "occurrence-points", event => {
        hover.remove();
        latest.current.onPreview(null);
        const features = event.features ?? [];
        if (features.length === 1 && typeof features[0].properties.id === "string") {
          latest.current.onSelect(features[0].properties.id);
          return;
        }
        // Co-located assertions remain individually selectable, without fake point jitter.
        const choices = document.createElement("div");
        const heading = document.createElement("strong");
        heading.textContent = "Loaded evidence at this place";
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
      map.on("click", "place-clusters", event => {
        const point = event.features?.[0];
        if (!point || point.geometry.type !== "Point") return;
        const center = point.geometry.coordinates as [number, number];
        map.getSource<GeoJSONSource>("occurrences")?.getClusterExpansionZoom(Number(point.properties.cluster_id)).then(zoom => {
          if (!cancelled) map.jumpTo({ center, zoom });
        }).catch(() => { /* A new dataset may have invalidated this transient cluster. */ });
      });
      map.on("mousemove", "occurrence-points", event => {
        map.getCanvas().style.cursor = "pointer";
        const id: unknown = event.features?.[0]?.properties.id;
        if (typeof id === "string") latest.current.onPreview(id);
      });
      map.on("mouseleave", "occurrence-points", () => { map.getCanvas().style.cursor = ""; latest.current.onPreview(null); hover.remove(); });
      map.on("mouseenter", "place-clusters", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "place-clusters", () => { map.getCanvas().style.cursor = ""; });
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
    const popup = previewPopup.current;
    if (!map || !popup || !map.getLayer("focused-occurrence")) return;
    map.setFilter("focused-occurrence", ["==", ["get", "id"], props.preview ?? ""]);
    // The open keyboard index already supplies the same preview in readable text.
    if (map.getContainer().closest(".map-workspace")?.querySelector(".atlas-position-list")) { popup.remove(); return; }
    const item = props.items.find(item => item.id === props.preview);
    if (!item) { popup.remove(); return; }
    const content = document.createElement("div");
    for (const [tag, text] of [
      ["small", "UFVP / PUBLISHED POSITION"],
      ["strong", `${(item.record_count ?? 1).toLocaleString("en-US")} evidence records`],
      ["span", item.locality_name],
      ["small", item.interpreted_count == null ? "Age bounds not supplied" : `${item.interpreted_count.toLocaleString("en-US")} with numeric age bounds · ${((item.record_count ?? 1) - item.interpreted_count).toLocaleString("en-US")} unresolved`],
      ["small", item.location_is_generalized ? "Generalized source position" : "Select to explore source localities"],
    ]) { const node = document.createElement(tag); node.textContent = text; content.append(node); }
    popup.setLngLat([item.longitude, item.latitude]).setDOMContent(content).addTo(map);
  }, [props.preview, props.items]);

  useEffect(() => {
    const map = instance.current;
    if (!map) return;
    const center = map.getCenter().wrap();
    if (Math.abs(center.lng - props.view.lng) > 0.0001 || Math.abs(center.lat - props.view.lat) > 0.0001 || Math.abs(map.getZoom() - props.view.zoom) > 0.015) {
      map.jumpTo({ center: [props.view.lng, props.view.lat], zoom: props.view.zoom });
    }
  }, [props.view.lat, props.view.lng, props.view.zoom]);

  useEffect(() => { if (props.reset && instance.current) frameFlorida(instance.current); }, [props.reset]);

  useEffect(() => {
    const map = instance.current;
    const item = props.items.find(item => item.id === props.view.selected);
    if (!map || !item) return;
    const frame = requestAnimationFrame(() => {
      const bounds = map.getContainer().getBoundingClientRect();
      const drawer = map.getContainer().closest(".map-workspace")?.querySelector(".atlas-position-selection,.atlas-locality-dossier");
      if (!drawer) return;
      const panel = drawer.getBoundingClientRect();
      const point = map.project([item.longitude,item.latitude]);
      const x = bounds.left + point.x, y = bounds.top + point.y;
      if (x < panel.left - 24 || x > panel.right + 24 || y < panel.top - 24 || y > panel.bottom + 24) return;
      const phone = bounds.width < 768;
      map.panBy(phone ? [0,y - panel.top + 36] : [x - panel.left + 36,0], { duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 220 });
    });
    return () => cancelAnimationFrame(frame);
  }, [props.view.selected, props.items]);

  return <>
    <div className="map-canvas" ref={container} />
    {(error || !styleUrl) && <div className="map-notice" role="status">
      {error ?? "No basemap configured. Occurrence points and the results list remain available."}
    </div>}
  </>;
}
