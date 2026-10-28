# PaleoGraph cartography

The Atlas is present-day geographic context for source evidence, not a reconstruction of ancient Florida. Its **Botanical field atlas** combines warm mineral land, deep botanical water, quiet natural features and an editorial evidence system. No relief, terrain or bathymetry is implied by the paint.

## Style and renderer

`apps/web/public/styles/paleograph.json` is original, project-owned MapLibre style JSON. It expands PaleoGraph's previous 12-layer Limestone atlas into 26 geographic layers. It is not a copied commercial or provider presentation. Direct MapLibre GL JS loads it through `NEXT_PUBLIC_MAP_STYLE_URL`, defaulting to `/styles/paleograph.json`.

The vector source remains [OpenFreeMap](https://openfreemap.org/quick_start/), using the [OpenMapTiles schema](https://openmaptiles.org/schema/). No account, API key, paid dependency, raster artwork, sprite or DEM was added. Deployment operators must comply with the provider's [current service terms](https://openfreemap.org/tos/). The style can be hosted separately or retargeted to compatible OpenMapTiles infrastructure.

| Layer family | Purpose and scale |
| --- | --- |
| Mineral background and water | Clear peninsula silhouette at statewide scale |
| Wood, grass, wetland and sand | Restrained, real land-cover variation, increasing with zoom |
| Settlement and protected land | Orientation without bright recreational colors |
| Coast and waterways | Crisp water edges and finer regional drainage |
| Administrative boundaries | Subtle country/state lines; county-level detail from zoom 8 |
| Roads and buildings | Major routes from zoom 7; local routes from 11; buildings from 14 |
| Geographic labels | State/country hierarchy, cities, then towns, water, islands, natural areas and road names |

Names prefer the source's English label and fall back to its supplied name. Verified provider glyph stacks are **Noto Sans Regular** and **Noto Sans Italic**; there are no locally bundled font assets. The UI retains PaleoGraph's existing scientific/editorial typography. Geographic labels yield to the evidence layer and do not invent names absent from the tiles.

## Evidence is a separate layer

`features/map/layers.ts` owns the GeoJSON evidence overlay. Diamond/ring/stack notation communicates evidence and precision, not a reconstructed animal community. Cluster rings show the **sum of evidence `record_count`**, not MapLibre's count of features. Clustering ends after zoom 10. Exact published positions remain unchanged; no jitter, heatmap, inferred coordinates or animal markers are used.

Selection and focus update layer filters. They do not replace the occurrence source or rebuild the basemap. Dataset changes retain the existing identity-aware `updateData` path. One map instance survives source, time and exploration-surface changes.

The bounded **Mapped positions** index supplies keyboard/touch equivalents to point previews and selection. A position can contain several distinct source localities. The position drawer keeps those identities separate. The map-edge locality dossier reuses the existing source geology, time envelope, associated taxa, custody and scientific caveats, adding references/provenance navigation. A locality association is not a contemporaneous community.

PBDB coordinates remain unassigned to the map while coordinate semantics await separate verification. Published occurrences remain searchable in Catalog, source contexts and Lineage. This phase adds no PBDB geometry or ingestion work.

## Attribution and licenses

The vector source preserves linked **OpenFreeMap**, **OpenMapTiles** and **OpenStreetMap contributors** attribution. MapLibre's attribution control remains visible and usable at all reviewed sizes and below the mobile drawer. Preserve these credits in screenshots and any future hosted deployment. See [OpenFreeMap attribution guidance](https://openfreemap.org/quick_start/) and [OpenStreetMap copyright and database licensing](https://www.openstreetmap.org/copyright).

Museum/PBDB evidence and ICS timescale credits remain separate from cartographic credits. The repository's AGPL-3.0-only license and upstream data licenses are unchanged.

## Editing and validation

Edit the dedicated JSON, keeping source-layer names compatible with the upstream schema. Use zoom expressions and modest opacity rather than large textures. Test the style with the locked MapLibre style-spec validator, then inspect real tiles: the ordinary fixture suite deliberately replaces remote transport and cannot establish geographic visual quality.

`atlasCartography.test.ts` validates the actual style, source/credit contracts, supported fonts, geographic hierarchy and exact evidence coordinates/counts. `atlas-cartography.spec.ts` renders the production layer graph with deterministic external transport and exercises previews, locality identity/history, six responsive widths and reduced motion. Live geographic screenshots and timing measurements are complementary local review evidence.

The 560 ms finite Atlas entrance uses opacity. Drawers use 320 ms and previews 140 ms; reduced motion removes these transitions. Native map pan/zoom remain intact. Selection only pans when a selected point is covered by the drawer or when an explicit source pivot targets offscreen evidence; it preserves the user's zoom.

## Design references

Three rendered directions were compared before choosing: botanical/mineral, light field-note and darker neutral editorial. Botanical water gave Florida the strongest silhouette and the clearest relationship to PaleoGraph Home. Regional natural-area labels and land-cover strength were reduced after comparison to preserve evidence hierarchy.

The existing Khalili Collections, Telefónica 100, AI in Design Report, Elektra and Possibles research informed archival hierarchy, persistent context, aligned typography and restrained previews. Additional Awwwards MCP references included [AP Transit](https://aptransit.co) (one uninterrupted geographic field) and [Walkable Atlas](https://ishikawa.co/en/) (revisitable context). These principles do not require adopting their 3D effects or animation stacks. [Historic England's Aerial Photo Explorer](https://historicengland.org.uk/images-books/archive/collections/aerial-photos/) provided an additional heritage-map reference for linking geography to source records.
