import type { GeoJSONSource, Map } from "maplibre-gl";
import type { MapOccurrence } from "../../lib/api/types";

export function updateOccurrences(map: Map, items: MapOccurrence[], selected: string | null) {
  const source = map.getSource<GeoJSONSource>("occurrences");
  if (!source) return;
  source.setData({
    type: "FeatureCollection",
    features: items.map(item => ({
      type: "Feature", id: item.id,
      geometry: { type: "Point", coordinates: [item.longitude, item.latitude] },
      properties: { id: item.id, name: item.scientific_name, unknown: item.older_ma === null || item.younger_ma === null, generalized: item.location_is_generalized },
    })),
  });
  map.setFilter("selected-occurrence", ["==", ["get", "id"], selected ?? ""]);
}

export function addOccurrenceLayers(map: Map) {
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
      "circle-color": ["case", ["get", "unknown"], color("--map-unknown"), color("--map-point")],
      "circle-stroke-color": color("--surface"), "circle-stroke-width": 2,
    },
  });
  map.addLayer({
    id: "selected-occurrence", type: "circle", source: "occurrences",
    filter: ["==", ["get", "id"], ""],
    paint: { "circle-radius": 12, "circle-color": color("--map-selected"), "circle-stroke-color": color("--surface"), "circle-stroke-width": 3 },
  });
}
