# Architecture through Phase 3

One monorepo, two applications, one PostgreSQL/PostGIS system of record. The browser
calls a versioned FastAPI API through one typed client. Occurrences come from the
database; React contains no occurrence fixtures.

| Area | Responsibility |
| --- | --- |
| apps/web/lib/api | Typed contracts, query construction, fetch/error boundary |
| features/explore | Workspace, URL state, data hooks, results, inspection |
| features/map | Client-only MapLibre lifecycle, viewport, GeoJSON layers |
| features/timeline | Accessible controls driven by API time configuration |
| apps/api/app/explore | Pydantic contracts, SQL queries, versioned routes |
| apps/api/app/models.py | Canonical/provenance entities and evidence links |
| apps/api/app/seed_demo.py | Transactional deterministic synthetic fixtures |
| apps/api/app/ingestion | Explicit official UFVP acquisition, normalization and batched persistence |
| apps/api/migrations | Alembic-owned extension and scientific schema |
| scripts/test_db.py | Disposable Compose migration/integration workflow |

The homepage/layout and health route remain intact. Explore parses its initial URL
on the server, then mounts the workspace. MapLibre loads without server rendering.
One GeoJSON source feeds symbol/halo layers; there is no DOM marker per assertion.
Co-located points offer assertion choices without falsifying positions. Selected
records remain inspectable outside filters with an explicit notice.

Settled map movements replace URL history; committed time ranges and selection/
close/reset push entries. Popstate restores state. Timeline handles preview locally,
committing on release or after a 250ms keyboard pause (also on blur). Intermediate
drag positions do not write URLs or request data.

Move-end publishes the actual viewport. The occurrence-window reducer requests a
25% buffer on each edge, limited to world bounds, and reuses complete coverage until
the visible view enters its outer 5% margin. Longitude containment supports wrapped
antimeridian windows. Buffered points stay in the map source; the results list is
projected to the actual viewport. A truncated buffer triggers an exact-viewport
request so offscreen records cannot crowd out visible records at the API cap.

Requests debounce 180ms. Abort cleanup and monotonically increasing request IDs
prevent obsolete responses from replacing newer intent. Successful markers and list
rows remain during loading/errors, with an explicit last-loaded indicator. The
inspector stays open. GeoJSON updates add/remove/change only differing feature IDs;
selection changes only the selection layer filter. No geographic movement is animated.

The semantic results list supports keyboard selection. Inspection takes focus;
Escape closes it and restores the result/heading. Mobile rearranges the workspace.
CSS tokens, editorial typography, and reduced-motion rules support the atlas visual
direction without a component framework.

Next loads the root .env, matching API/Compose. Only NEXT_PUBLIC settings are exposed
to the browser. The configurable default is project-owned `/styles/paleograph.json`,
using OpenFreeMap/OpenMapTiles/OSM with required attribution. Blank style uses a neutral
canvas. Errors preserve textual access. [Visual identity](visual-identity.md) records
tokens, marker meanings and provider terms.
The installed MapLibre worker AND shared module are copied into ignored public
assets before dev/build. This follows [MapLibre's Next.js guidance](https://maplibre.org/maplibre-gl-js/docs/)
and prevents a missing relative worker import in Turbopack output.

FastAPI lifespan owns an engine; requests own short-lived Sessions. Health does
not connect to the database. Synchronous SQLAlchemy/psycopg use pre-ping, five-second
connect timeout, and public search path. Routes expose Pydantic models. Validation,
not-found, and database errors use sanitized envelopes. No generic service/repository
framework or write API was added.

Development Compose and its volume are unchanged. A separate test project uses
port 55432 and ephemeral storage. Ordinary pytest cannot use development credentials.
CI retains its PostGIS service and migration checks, adding frontend state tests.
Playwright checks currently run locally. Lockfiles pin resolved dependencies.
No deployment is configured.

Explore never contacts a scientific provider. Explicit ingestion acquires one official
UFVP archive after metadata/license verification, pins its version, retains hashed raw
bytes, streams a normalized boundary and upserts canonical/evidence batches. The CLI
holds a PostgreSQL advisory lock on a dedicated connection across batch commits.
Runs retain failures and scope; only completed full Florida snapshots deactivate unseen
records. Source-record revisions retain previous raw values. No queues or new services
were needed. Tests use eight attributed offline source rows.

Explore defaults to museum mode, with an explicit synthetic demo switch. Changing mode
clears the previous mode's display; other time/viewport changes retain the approved
continuity behavior. UFVP text ages remain unknown numerically. Basemap traffic is
cartographic infrastructure, not a second scientific source. Formal timescales,
reconciliation, graph/search, accounts and deployment remain outside this phase.

References: [OpenFreeMap](https://openfreemap.org/quick_start/),
[GeoAlchemy migrations](https://geoalchemy-2.readthedocs.io/en/stable/alembic.html),
[PostGIS image](https://github.com/postgis/docker-postgis).
