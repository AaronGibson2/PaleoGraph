# PaleoGraph

A Florida museum atlas for cataloged fossil material, published localities,
geological interpretation and source-supported relationships. Phase 3.6 uses
one scientific collection: Florida Museum of Natural History UFVP. It is not a
universal taxonomy or occurrence authority. No public demo mode remains.

The current local import is the **complete Florida scope: 462,280 UFVP v1.182
assertions**, with 254,866 mapped assertions and 445,678 derived age envelopes.
Source data is CC BY-NC 4.0;
geological reference data is ICS v2026/06, CC BY 4.0. Source ages, derived interval
envelopes and research evidence remain visibly separate.

[Phase 3.5 completion and validation](docs/phase-3.5-validation.md) records actual
checks, screenshots, measurements, limitations and all 48 requested report items.
Historical reports: [Phase 2](docs/phase-2-validation.md), [Phase 3](docs/phase-3-validation.md).
The [full Florida follow-up](docs/phase-3.5-full-florida-validation.md) records the
SSD backup/restore check, completed import and full-scope measurements separately
from the original 25,000-record validation.

Phase 3.6 adds **Atlas / Localities / Lineage**: dedicated locality associations and
a time-aware source taxonomic hierarchy. Classification branches carry no ancestry
or divergence claims; observed material spans are not biological durations. The
existing Relationships graph remains available through inspection. Original clade
glyphs are distinct from specimen-image placeholders; no unreliable remote preview
is displayed. See [Phase 3.6 validation](docs/phase-3.6-validation.md),
[visual provenance](docs/taxon-visuals.md) and [multimedia audit](docs/ufvp-multimedia-research.md).

**Preserve the prepared full Florida database. Do not rerun its import or seed it.**
For this phase, run only `alembic upgrade head` (additive `0005_classification`).
It populates a small source-membership projection from existing paths without
changing source assertions, specimens, derived ages or ingestion runs. This workspace
has already applied it. No new environment variables are required.

## Local setup

Requirements: Node version in `.node-version`, pnpm 10.34.6, uv/Python 3.12 and
Docker Compose with PostGIS. Run these commands from the repository root.
On PowerShell use `pnpm.cmd` if execution policy blocks the pnpm shim.

```sh
pnpm install --frozen-lockfile
uv sync --project apps/api --locked
```

Copy `.env.example` to `.env` if it does not already exist, then:

```sh
docker compose up -d --wait db
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api python -m app.db
```

Existing Phase 2/3 databases: review the exact legacy demo manifest before applying
its atomic cleanup. No name matching or geographic matching is used; unrelated
foreign-key dependencies abort deletion. The current local database was already
cleaned in Phase 3.5. Repeating these commands is safe for an absent manifest.

```sh
uv run --project apps/api python -m app.discovery.remove_legacy_demo
uv run --project apps/api python -m app.discovery.remove_legacy_demo --apply
uv run --project apps/api python -m app.discovery.index
```

A new database has no museum material. Import a bounded official source snapshot:

```sh
uv run --project apps/api python -m app.ingestion.import_ufvp --version 1.182 --limit 1000
```

Completed/partial imports rebuild discovery automatically. Use `app.discovery.index`
after upgrading an existing imported database, or explicitly to refresh the projection.
The retained source facts and historical revisions are preserved. See
[ingestion and rights](docs/ufvp-ingestion.md). This local database already contains
the complete pinned Florida scope. Its pre-import backup and retained archive are
on the user-authorized E: SSD; the existing Docker volume remains in place.

Run the API and frontend in separate terminals:

```sh
uv run --project apps/api uvicorn app.main:app --reload --reload-dir apps/api/app
pnpm dev
```

Open http://localhost:3000/explore. API documentation: http://localhost:8000/docs.
Health is process liveness; `app.db` actually verifies PostgreSQL/PostGIS.

## Explore

Search catalog numbers, specimen identifiers, source classifications, localities,
collections, institutions and source context. Select a result to inspect its evidence
and pivot the shared context. Individual context assertions can be removed. Selecting
a specimen opens its catalog view; it does not restrict every result to one specimen.

Map circles count catalog assertions, including client spatial clusters. Exact
coordinate stacks retain all distinct localities and lead to a fully paginated
catalog. Counts are not counts of organisms or an assertion of locality equivalence.
The catalog exposes true totals and 30-row pages. Generalization halos express
status, not an uncertainty radius. Missing/withheld positions never become 0,0;
search and nonspatial entity views still expose eligible material.

The geological instrument uses a single highlighted track with two accessible
handles, older to the left and present to the right. Named selections and hierarchy
come from the pinned ICS reference. Drill into periods, epochs and ages; validated
formal subepoch compositions are distinguished in reference metadata. Dragging
creates a custom range. All ages includes unresolved source ages. Arrows adjust
the focused scale; Shift multiplies steps by ten, Page keys step ten percent,
Home/End reach permitted limits. Handle release commits once; keyboard changes
settle after 250 ms. Reference calibration is not a measured specimen age.

Relationships display bounded source-supported neighborhoods. Expand to 24 visible
neighbors, then continue to the next neighborhood. A keyboard-accessible edge list
provides the same relationships. Aggregate edges mean shared catalog material,
not inferred biology. This UFVP archive contains no bibliographic references or
DOIs; no research papers or publication edges are invented.

URL/history restores context, time, camera, selected entity and exploration surface.
Small pans reuse buffered coverage. Pending/error requests retain previously loaded
points and rows with a visible notice. Reduced motion avoids decorative transitions.

## API and schema

| GET endpoint under `/api/v1` | Purpose |
| --- | --- |
| `/catalog` | Cursor-paginated material and true matching total |
| `/search` | Ranked mixed scientific entities, total and cursor |
| `/map/places` | Exact-coordinate aggregation, totals, unmapped count and cursor |
| `/entities/{kind}/{uuid}` | Source-supported entity context and evidence summary |
| `/graph/{kind}/{uuid}` | Bounded progressive relationship neighborhood |
| `/time-intervals` | Versioned attributed ICS hierarchy and calibration |
| `/occurrences/{uuid}` | Preserved detailed source assertion and provenance |
| `/map/occurrences` | Legacy capped individual assertions; source numeric ages only |
| `/datasets/ufvp` | Current import scope/counts/status and source attribution |

Discovery queries share taxon/locality/collection/institution/term UUID filters,
optional exact coordinate pair, optional viewport and paired `older_ma`/`younger_ma`
bounds. Ages overlap inclusively. Active ranges exclude unresolved ages; source
numeric bounds take precedence over derived interval envelopes. Catalog/search/
graph limits default to 30 and max at 100; the graph UI requests 12. Place pages
default to 1,500 and max at 5,000. Context-bound cursors reject changed filters.
The interactive UI uses discovery endpoints, not the legacy occurrence cap.

Migration `0004_discovery` is additive: GeologicalInterval, AgeInterpretation,
TaxonPath, ContextTerm, CatalogEntry and CatalogTerm; source-scoped taxon metadata,
`pg_trgm`, typed foreign keys and PostgreSQL indexes. Prior migrations are unchanged.
Only Alembic owns schema changes. [Data model](docs/data-model.md),
[architecture](docs/architecture.md), [ADRs](docs/adr/) and
[timescale research](docs/geological-timescale-research.md) explain the boundaries.

## Configuration

Root `.env` is read by API/Next/Compose; process environment wins. Keep POSTGRES
settings and DATABASE_URL consistent. URL-encode special password characters.
CORS_ORIGINS is a JSON array of exact origins. No new scientific API keys are needed.

| Setting | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Public API prefix; default localhost:8000/api/v1 |
| `NEXT_PUBLIC_MAP_STYLE_URL` | Owned MapLibre style; default /styles/paleograph.json |
| `TEST_DATABASE_URL` | Explicit opt-in to a migrated disposable test database |
| `NEXT_DIST_DIR` | Optional isolated Next build directory for validation; default .next |
| `E2E_BASE_URL`, `E2E_API_BASE_URL` | Browser validation server URLs; script sets these |

NEXT_PUBLIC values are embedded at build time. Basemap tiles/fonts require network
access. Preserve OpenFreeMap/OpenMapTiles/OpenStreetMap attribution. Blank style
configuration provides a neutral canvas and notice. No deployment is configured.

## Checks

```sh
pnpm lint
pnpm typecheck
pnpm test
pnpm build
uv run --project apps/api ruff check apps/api scripts
uv run --project apps/api ruff format --check apps/api scripts
uv run --project apps/api mypy --config-file apps/api/pyproject.toml apps/api/app
uv run --project apps/api pytest apps/api/tests
uv run --project apps/api python scripts/test_db.py
pnpm --filter @paleograph/web exec playwright install chromium
uv run --project apps/api python scripts/test_browser.py
```

Ordinary pytest skips integration without TEST_DATABASE_URL. `test_db.py` owns an
ephemeral Compose project on 55432, runs migration repeat/downgrade/re-upgrade/drift
checks and integration tests, then removes only that project. `test_browser.py`
owns a second disposable PostGIS database on 56432, API 8001, production Next 3001
and an isolated build. Ensure these ports are free. It creates explicitly fictional
dense **test-only** rows plus eight attributed offline UFVP rows. It never seeds
normal development data. Scientific API/database/MapLibre workers are real; only
basemap traffic is stubbed in regression tests. CI includes both the PostGIS service
migration suite and a separate disposable production browser job; remote CI has not
been executed in this session.

`uv run --project apps/api python scripts/profile_discovery.py` records warm read-only
query timings/plans/table sizes for the currently imported scope in ignored
`data/processed/`. Both the earlier bounded and subsequent full-scope measurements
are documented separately. Unmocked visual captures use
`scripts/capture_phase35.mjs` with separately running real-data servers on 3001/8001.

## Limits

The import covers Florida rows in pinned UFVP v1.182, not later museum updates or
non-Florida material. Published source taxonomy
is incomplete; no accepted-name reconciliation occurs. Uncertain/mixed geological
labels stay unresolved; NALMA stays regional biochronology without invented numerical
correlation. Source records are evidence, not papers. Chromium checks are not a broad
cross-browser or WCAG certification. Warm local measurements do not establish
production throughput or cold-start behavior. Commercial UFVP use requires compatible permission.
No second scientific occurrence source, auth, AI, new search service or deployment
was introduced. Phase 4 has not begun.

Docker Compose down retains the development volume. Changing credentials does not
rewrite an existing volume. Do not use `down -v` to troubleshoot valuable data.
PostGIS/pg_trgm migrations require extension-capable database credentials. Worker
assets are prepared by `pnpm dev`/`pnpm build`; use those scripts after dependency changes.
