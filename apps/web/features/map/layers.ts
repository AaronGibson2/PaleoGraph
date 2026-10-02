import type { GeoJSONSource, GeoJSONSourceDiff, Map as MapLibreMap } from "maplibre-gl";
import type { MapOccurrence } from "../../lib/api/types";

type Feature = NonNullable<GeoJSONSourceDiff["add"]>[number];
const sources = new WeakMap<GeoJSONSource, { items: MapOccurrence[]; features: Map<string, Feature>; selected: string | null; ready: Promise<void> }>();
const feature = (item: MapOccurrence): Feature => ({
  type: "Feature", id: item.id,
  geometry: { type: "Point", coordinates: [item.longitude, item.latitude] },
  properties: { id: item.id, name: item.scientific_name, unknown: item.older_ma === null || item.younger_ma === null, generalized: item.location_is_generalized },
});

export function updateOccurrences(map: MapLibreMap, items: MapOccurrence[], selected: string | null) {
  const source = map.getSource<GeoJSONSource>("occurrences");
  if (!source) return;
  let previous = sources.get(source);
  if (!previous) {
    const features = new Map(items.map(item => [item.id, feature(item)]));
    previous = { items, features, selected: null, ready: source.setData({ type: "FeatureCollection", features: [...features.values()] }) };
    sources.set(source, previous);
  } else if (previous.items !== items) {
    const next = new Map(items.map(item => [item.id, feature(item)]));
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
  map.addSource("occurrences", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: "generalized-locations", type: "circle", source: "occurrences",
    filter: ["==", ["get", "generalized"], true],
    paint: { "circle-radius": 15, "circle-color": color("--map-point"), "circle-opacity": 0.12, "circle-stroke-width": 1, "circle-stroke-color": color("--map-point"), "circle-stroke-opacity": 0.5 },
  });
  map.addLayer({
    id: "occurrence-points", type: "circle", source: "occurrences",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 5, 10, 8],
      "circle-color": ["case", ["get", "unknown"], color("--surface-raised"), color("--map-point")],
      "circle-stroke-color": ["case", ["get", "unknown"], color("--map-unknown"), color("--surface-raised")], "circle-stroke-width": 2,
    },
  });
  map.addLayer({
    id: "selected-occurrence", type: "circle", source: "occurrences",
    filter: ["==", ["get", "id"], ""],
    paint: { "circle-radius": 12, "circle-opacity": 0, "circle-stroke-color": color("--map-selected"), "circle-stroke-width": 3 },
  });
}
