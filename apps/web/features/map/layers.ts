import type { GeoJSONSource, GeoJSONSourceDiff, Map as MapLibreMap } from "maplibre-gl";
import type { MapOccurrence } from "../../lib/api/types";

type Feature = NonNullable<GeoJSONSourceDiff["add"]>[number];
const sources = new WeakMap<GeoJSONSource, { items: MapOccurrence[]; features: Map<string, Feature>; selected: string | null; ready: Promise<void> }>();
const feature = (item: MapOccurrence, coLocated: number): Feature => ({
  type: "Feature", id: item.id,
  geometry: { type: "Point", coordinates: [item.longitude, item.latitude] },
  properties: { id: item.id, name: item.scientific_name, catalog: item.catalog_label ?? "", unknown: item.older_ma === null || item.younger_ma === null, generalized: item.location_is_generalized, coLocated, glyph: coLocated > 1 ? "atlas-stack" : item.older_ma === null || item.younger_ma === null ? "atlas-unknown" : "atlas-record" },
});

function featuresFor(items: MapOccurrence[]) {
  const counts = new Map<string, number>();
  for (const item of items) { const key = `${item.longitude}:${item.latitude}`; counts.set(key, (counts.get(key) ?? 0) + 1); }
  return new Map(items.map(item => [item.id, feature(item, counts.get(`${item.longitude}:${item.latitude}`) ?? 1)]));
}

function addNotation(map: MapLibreMap, name: string, color: string, hollow: boolean, stack = false) {
  const canvas = document.createElement("canvas"); canvas.width = canvas.height = 32;
  const context = canvas.getContext("2d");
  if (!context) return;
  context.strokeStyle = color; context.fillStyle = hollow ? "#fbf6e8" : color; context.lineWidth = 2.5;
  if (stack) { context.strokeRect(10, 6, 17, 17); context.fillStyle = "#fbf6e8"; }
  context.beginPath(); context.moveTo(15, 8); context.lineTo(24, 17); context.lineTo(15, 26); context.lineTo(6, 17); context.closePath(); context.fill(); context.stroke();
  const pixels = context.getImageData(0, 0, 32, 32);
  map.addImage(name, { width: 32, height: 32, data: pixels.data }, { pixelRatio: 2 });
}

export function updateOccurrences(map: MapLibreMap, items: MapOccurrence[], selected: string | null) {
  const source = map.getSource<GeoJSONSource>("occurrences");
  if (!source) return;
  let previous = sources.get(source);
  if (!previous) {
    const features = featuresFor(items);
    previous = { items, features, selected: null, ready: source.setData({ type: "FeatureCollection", features: [...features.values()] }) };
    sources.set(source, previous);
  } else if (previous.items !== items) {
    const next = featuresFor(items);
    const diff: GeoJSONSourceDiff = { remove: [], add: [], update: [] };
    for (const id of previous.features.keys()) if (!next.has(id)) diff.remove!.push(id);
    for (const [id, value] of next) {
      const old = previous.features.get(id);
      if (!old) diff.add!.push(value);
      else if (JSON.stringify(old) !== JSON.stringify(value)) diff.update!.push({
        id, newGeometry: value.geometry,
        addOrUpdateProperties: Object.entries(value.properties ?? {}).map(([key, value]) => ({ key, value })),
      });
    }
    if (diff.remove!.length || diff.add!.length || diff.update!.length) {
      previous.ready = previous.ready.then(() => source.updateData(diff));
    }
    previous.items = items;
    previous.features = next;
  }
  // Selecting an assertion never retransmits the occurrence dataset.
  if (previous.selected !== selected) {
    map.setFilter("selected-occurrence", ["==", ["get", "id"], selected ?? ""]);
    previous.selected = selected;
  }
  previous.ready = previous.ready.catch(error => { map.fire("error", { error }); });
}

export function addOccurrenceLayers(map: MapLibreMap) {
  const tokens = getComputedStyle(document.documentElement);
  const color = (name: string) => tokens.getPropertyValue(name).trim();
  addNotation(map, "atlas-record", color("--map-point"), false);
  addNotation(map, "atlas-unknown", color("--map-point"), true);
  addNotation(map, "atlas-stack", color("--map-point"), true, true);
  map.addSource("occurrences", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: "generalized-locations", type: "circle", source: "occurrences",
    filter: ["==", ["get", "generalized"], true],
    paint: { "circle-radius": 15, "circle-color": color("--map-point"), "circle-opacity": 0.12, "circle-stroke-width": 1, "circle-stroke-color": color("--map-point"), "circle-stroke-opacity": 0.5 },
  });
  map.addLayer({
    id: "occurrence-points", type: "symbol", source: "occurrences",
    layout: { "icon-image": ["get", "glyph"], "icon-allow-overlap": true, "icon-ignore-placement": true, "icon-size": ["interpolate", ["linear"], ["zoom"], 4, 0.8, 10, 1.15] },
  });
  map.addLayer({
    id: "selected-occurrence", type: "circle", source: "occurrences",
    filter: ["==", ["get", "id"], ""],
    paint: { "circle-radius": 12, "circle-opacity": 0, "circle-stroke-color": color("--map-selected"), "circle-stroke-width": 3 },
  });
}
