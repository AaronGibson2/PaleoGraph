# PaleoGraph

A Florida paleobiology atlas for museum material, published occurrence evidence,
source contexts, geological interpretation and source-supported relationships.
Phase 4E exposes independently retained UFVP and PBDB evidence. It is not a
universal taxonomy or occurrence authority. No public demo mode remains.

The current local import is the **complete Florida scope: 462,280 UFVP v1.182
assertions**, with 254,866 mapped assertions and 445,678 derived age envelopes.
UFVP source data is CC BY-NC 4.0;
geological reference data is ICS v2026/06, CC BY 4.0. Source ages, derived interval
envelopes and research evidence remain visibly separate.

Phase 4A profiles PBDB as a proposed second source without importing it. See the
[official-source profile](docs/pbdb-source-profile.md),
[adapter proposal and approval gates](docs/pbdb-adapter-proposal.md), and
[bounded live profiling evidence](docs/source-data/pbdb-profile-2026-10-05.json).
The [completion report](docs/phase-4a-report.md) summarizes the findings and validation.
Phase 4B's adapter and disposable canary
preceded the [Phase 4C full Florida ingestion](docs/phase-4c-report.md).

[Phase 4E](docs/phase-4e-report.md) adds public multi-source exploration, with
**18,915 PBDB published occurrences, 1,118 retained collections, and zero canonical
PBDB specimens**. Museum material remains the rollout default; the shared evidence
selector enables All evidence or Published occurrences across Atlas, Search,
Localities and Lineage. PBDB coordinates currently have an unverified datum, so
their evidence is discoverable through source contexts rather than fabricated map
positions. Rights remain independent: PBDB CC0 1.0 does not apply to UFVP material.
See [multi-source product semantics](docs/multi-source-product.md).

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

**Preserve the prepared full Florida database. Do not seed it or repeat the UFVP import.**
The prepared database is at `0012_product_browse`, with independently retained
UFVP and PBDB evidence and verified pre/post-4E restore checkpoints. Its migrations
are already applied. Use the [checkpoint and PBDB replay workflow](docs/pbdb-adapter.md#full-florida-acquisition-and-publication-phase-4c)
for deliberate backend validation. No new environment variables are required.

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

If the dev home page works but `/explore` returns 404, follow the
[routing recovery and direct-link regression checks](docs/explore-routing-repair.md).
Recover frontend-generated route state without reimporting or rebuilding museum data.

## Explore

Search catalog numbers, specimen identifiers, source classifications, localities,
collections, institutions and source context. Select a result to inspect its evidence
and pivot the shared context. Individual context assertions can be removed. Selecting
a specimen opens its catalog view; it does not restrict every result to one specimen.

Map circles count mapped evidence records, including client spatial clusters. Exact
coordinate stacks retain all distinct localities and lead to a fully paginated
catalog. Counts are not counts of organisms or an assertion of locality equivalence.
The catalog exposes true totals, source breakdowns and 30-row pages. Published
occurrences are distinct from museum specimens; selecting a PBDB occurrence opens
its source taxonomy, provider age, material labels and optional reference roles.
Generalization halos express
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

TIME-1 audits and hardens the distinction between source geology, numeric source
bounds, interpreted intervals, and observed material envelopes. See
[geological-time semantics](docs/geological-time-semantics.md) and the
[TIME-1 validation report](docs/time-1-validation.md). The pinned timescale remains
ICS v2026/06. Phase 4A profiled PBDB; Phase 4B now provides a source-independent
adapter and validated disposable 208-occurrence canary. See the
[PBDB adapter](docs/pbdb-adapter.md) and [Phase 4B report](docs/phase-4b-report.md).
PBDB occurrences remain source-specific evidence without placeholder Specimens.
The normal database is at `0012_product_browse` with **462,280 UFVP assertions**
and **18,915 independent PBDB occurrences**, across 1,118 PBDB collections.
There are still **462,280 canonical Specimens**; PBDB creates none.
Source-specific rights, age policies and taxonomic identities remain independent.
See the [Phase 4C report](docs/phase-4c-report.md) for checkpoints, full evidence
validation, exact rerun, source-aware internal queries and regression measurements.
Phase 4D adds a reversible internal material reconciliation layer: 326 assessments,
117 candidate edges, and **zero deterministic links** because PBDB's UF labels lack
collection codes. Source records and scientific evidence remain unchanged. See the
[reconciliation policy](docs/cross-source-reconciliation.md) and
[Phase 4D report](docs/phase-4d-report.md) for the complete census, provenance,
replay/rebuild validation and checkpoints.

The import covers Florida rows in pinned UFVP v1.182, not later museum updates or
non-Florida material. Published source taxonomy
is incomplete; no accepted-name reconciliation occurs. Uncertain/mixed geological
labels stay unresolved; NALMA stays regional biochronology without invented numerical
correlation. Source records are evidence, not papers. Chromium checks are not a broad
cross-browser or WCAG certification. Warm local measurements do not establish
production throughput or cold-start behavior. Commercial UFVP use requires compatible permission.
Phase 4E provides shared source-filtered discovery, PBDB occurrence detail and
publication/reference presentation. See the [Phase 4E report](docs/phase-4e-report.md).
PBDB geography remains withheld from Atlas while modern datum is unverified.
Phase 5A profiles global PBDB access, coordinates and disposable scale benchmarks:
the coordinate gate is RED and global ingestion readiness is YELLOW pending
engineering validation. See the [global expansion design](docs/pbdb-global-expansion.md)
and [Phase 5A report](docs/phase-5a-report.md). No global import, new infrastructure
or deployment was performed; Phase 5A stops for review before Phase 5B.

Phase 5B0 measures the storage footprint and compares three disposable designs.
The recommended compact proof/archive design projects **46.04 GiB live PostgreSQL**
plus **3.09 GiB external raw archives**, versus 120.32 GiB for the measured current
layout extrapolation. These are global forecasts; the normal 6.68 GiB database
and scientific records remain unchanged. Storage readiness is **YELLOW** pending
production archive/migration/dirty-query integration; coordinates remain **RED**.
See the [storage architecture](docs/global-storage-architecture.md) and
[Phase 5B0 report](docs/phase-5b0-report.md). No global import or next phase started.

Docker Compose down retains the development volume. Changing credentials does not
rewrite an existing volume. Do not use `down -v` to troubleshoot valuable data.
PostGIS/pg_trgm migrations require extension-capable database credentials. Worker
assets are prepared by `pnpm dev`/`pnpm build`; use those scripts after dependency changes.
