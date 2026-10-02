# PaleoGraph

A paleobiology atlas connecting occurrence assertions across time, geography,
taxonomy, and source collections. Phase 3 implements `/explore` end to end:
Next.js → typed API client → FastAPI → SQLAlchemy → PostgreSQL/PostGIS.

Explore defaults to **real Florida Museum UFVP catalog assertions**, imported into
local PostgreSQL/PostGIS. The source is **CC BY-NC 4.0**; retain creator, museum,
dataset/version and license attribution. This phase is for noncommercial use.
See [source verification](docs/ufvp-source-research.md) and
[ingestion rules](docs/ufvp-ingestion.md).

The 40 seeded examples remain separate at `/explore?data_mode=demo`. Their taxon,
age and place associations are invented, visibly labeled synthetic, and never
included in the default museum view.

## Local setup

Prerequisites: Node 24 (see `.node-version`), pnpm 10.34.6, uv 0.12.21 or compatible
newer uv, Docker with Compose v2 and Linux containers. uv installs Python 3.12.
GNU Make is optional. Run commands from this repository root. In PowerShell use
`pnpm.cmd` / `npm.cmd` if execution policy blocks their `.ps1` wrappers.

For a new checkout, copy `.env.example` to `.env` (`Copy-Item .env.example .env`
in PowerShell). For an existing checkout, retain credentials and add the two
`NEXT_PUBLIC_*` settings below. Do not overwrite an existing `.env`.

```sh
pnpm install --frozen-lockfile
uv sync --project apps/api --locked
docker compose up -d --wait db
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api python -m app.db
uv run --project apps/api python -m app.seed_demo
uv run --project apps/api python -m app.ingestion.import_ufvp --limit 1000
```

Start each application in its own terminal:

```sh
uv run --project apps/api uvicorn app.main:app --reload --reload-dir apps/api/app
```

```sh
pnpm dev
```

Open http://localhost:3000/explore. Pan/zoom, choose a time window or adjust age
bounds, and select a map point or result row. Co-located assertions have a choice
popup. Inspection includes collection context and source evidence. The URL retains
center, zoom, ages, and selected UUID; browser back/forward restores selection.
The textual results support keyboard access; Escape closes inspection and restores
focus. The homepage and `/api/v1/health` remain available.

**UFVP does not supply numeric Ma bounds.** Its geological text is retained;
numeric ages remain NULL. Use **All ages** for museum records. A numeric range
currently excludes them rather than inventing dates. This is an explicit source
limitation, not a formal geological timescale conversion.

For an offline, eight-record museum fixture, run:

```sh
uv run --project apps/api python scripts/prepare_ufvp_fixture.py
uv run --project apps/api python -m app.ingestion.import_ufvp --archive data/raw/ufvp-offline-fixture.zip --limit 8
```

For the complete Florida scope, run the following against the **complete official
archive**, never a subset fixture. Only a successful full import marks unseen
source records inactive; it never hard deletes canonical objects.

```sh
uv run --project apps/api python -m app.ingestion.import_ufvp --full-florida
```

Equivalent Make targets: `ingest-ufvp-fixture`, `ingest-ufvp-sample`, and
`ingest-ufvp-florida`. `--version 1.182` pins the verified snapshot;
`--archive PATH --limit N` reuses retained bytes without networking. Samples select
the first accepted Florida records in archive order and are not statistically
representative. Current imports are visible in the source strip.

The time control uses one linear track, older on the left and present on the right.
Drag either handle to set a custom range, or choose a numeric demo preset below it.
The highlighted band and adjacent handle labels show the selected interval. Tab
between handles; Left/Up adds 0.01 Ma and Right/Down subtracts 0.01 Ma. Hold Shift
for 0.1 Ma steps; Page Up/Down changes by 1 Ma. Home/End moves to the permitted
minimum/maximum. Handles cannot cross. All ages clears the filter, including for
unknown ages. Demo presets are not a formal geological timescale.

Handle movement previews immediately; release commits one shareable range. Keyboard
changes commit after a short pause or when focus leaves the handle. Small map pans
reuse a buffered geographic window. While a new query loads, existing points and
rows remain visible with a restrained last-loaded/updating indicator. Back/Forward
restores committed time ranges and selection. See [continuity notes](docs/explore-continuity.md).

API documentation: http://localhost:8000/docs. Health is process liveness; the
`app.db` command above actually connects to PostGIS.

## Configuration

Settings read the root `.env`; process environment wins. Keep `DATABASE_URL` in
sync with `POSTGRES_*`; URL-encode special password characters. `CORS_ORIGINS` is a
JSON array of exact origins (default `["http://localhost:3000"]`).

| Setting | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Browser API prefix; default `http://localhost:8000/api/v1` |
| `NEXT_PUBLIC_MAP_STYLE_URL` | MapLibre style URL; default `/styles/paleograph.json` |
| `TEST_DATABASE_URL` | Explicit opt-in to tests against a migrated disposable database |

`NEXT_PUBLIC_*` values are public and embedded at build time. Restart development
or rebuild production after changes. Blank style configuration provides a neutral
canvas and notice. Basemap tiles require network access and retain provider
attribution. The project-owned style uses OpenFreeMap/OpenMapTiles/OSM cartography.
See [visual identity and provider terms](docs/visual-identity.md). Provider continuity
and production suitability remain a release decision; no deployment is configured.

## Schema and seed

New migration `0002_explore_schema` adds Source, SourceDataset, IngestionRun,
SourceRecord, Taxon, Locality, CollectionEvent, Occurrence, and four evidence link
tables. Existing `0001_enable_postgis` is unchanged. Only Alembic owns schema
changes. See the [data model](docs/data-model.md) for relationships and constraints.

Phase 3 adds `0003_ufvp_specimens`: Institution, Collection, Specimen, typed specimen
evidence, retained source-record revisions, and ingestion scope/snapshot metadata.
Run `upgrade head` before importing. Existing migrations and demo IDs are preserved.

`make seed-demo` (or the seed command above) creates two synthetic sources/datasets,
two fixed ingestion snapshots, six taxa, 20 localities, 40 contexts, 40 assertions,
and their source records. Fixed UUIDv4 fixture identities make reruns idempotent.
36 assertions have coordinates; four exercise missing/withheld locations. The
initial viewport shows a subset. Ages include unknown/partial cases; some points
are generalized. Genus names may be real, but their associations are invented.

Replace only the reserved demo fixtures atomically:

```sh
uv run --project apps/api python -m app.seed_demo --reset
```

Equivalent: `make reset-demo`. This does not clear the database. Unrelated entities
remain; foreign-key dependencies from non-demo data abort reset. Repeated seeds do
not overwrite fixture edits; use reset intentionally to restore original examples.

## Explore API

| Endpoint | Response |
| --- | --- |
| `GET /api/v1/map/occurrences` | Minimal items plus `returned`, `limit`, `truncated` |
| `GET /api/v1/occurrences/{uuid}` | Scientific/contextual detail and source/dataset evidence |
| `GET /api/v1/time-intervals` | Versioned numeric demo windows, not a formal timescale |
| `GET /api/v1/datasets/ufvp` | Local current/mapped/numeric-age counts, latest scope/status and source credit |

Map queries require `west`, `south`, `east`, `north`. Optional `older_ma` and
`younger_ma` must be supplied together (0–10000 Ma, older ≥ younger). `limit`
defaults to 200, maximum 1000. Example:

`data_mode` defaults to `museum` and excludes synthetic evidence. Use `demo`
explicitly for development examples. Capped responses state `truncated: true`;
co-located assertions can remain capped even after zooming. No aggregate count or
server cluster is inferred from loaded records.

```text
http://localhost:8000/api/v1/map/occurrences?west=-88&south=24&east=-79&north=32&older_ma=2&younger_ma=0.1
```

Spatial boundaries are inclusive; west > east crosses the antimeridian. Missing
and withheld coordinates are absent from spatial results. Map assertions require
current source evidence. Active age filters match fully known closed intervals by
inclusive overlap; unknown/partial ages are excluded. Without an age filter they
remain eligible. Only the backend performs filtering. Errors use
`{ "error": { "code": "…", "message": "…", "details": [] } }`.

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
```

Ordinary pytest uses an unreachable database URL; integration cases are deselected unless
`TEST_DATABASE_URL` is supplied. **Prefer `make test-db`** (last command above): a
separate `paleograph-test` Compose project on port 55432 uses ephemeral storage,
runs upgrade/repeat/downgrade/re-upgrade/drift checks and integration tests, then
removes that project. It never uses the normal development database. Do not point
manual integration runs at valuable data.

For browser checks, migrate, seed demo, import the eight-record offline museum
fixture above, and run both servers first:

```sh
pnpm --filter @paleograph/web exec playwright install chromium
pnpm --filter @paleograph/web test:e2e
```

These use the real local API/database and MapLibre worker, with an intercepted
minimal basemap so external tile availability cannot determine test results.
Browser tests currently run locally. CI runs frontend checks/state tests and backend
tests against its disposable PostGIS service with a migration round trip.
Remote CI execution is not claimed.

Make shortcuts: `db-up`, `db-down`, `migrate`, `verify-db`, `seed-demo`, `reset-demo`,
`ingest-ufvp-fixture`, `ingest-ufvp-sample`, `ingest-ufvp-florida`, `dev-api`,
`dev-web`, `test`, `test-db`, `lint`, `typecheck`, `build`.

## Boundaries and next work

Occurrences are assertions and link separately to cataloged physical material.
A UFVP catalog entry can contain several pieces; Specimen does not assert exactly
one organism. Localities and collection contexts remain separate. PaleoGraph is
not a universal taxonomic or specimen authority. Cross-source reconciliation,
field-level conflict resolution, search infrastructure, graph, accounts, AI and
deployment remain outside this phase.

Explore caps results without pagination/server clustering. Controls default to 0–12 Ma
and extend for larger URL age ranges. Generalization rings indicate status, not a
measured uncertainty radius. Missing locations can be inspected by UUID but are
absent from the spatial list. Production scale, a formal timescale, and broad
cross-browser/accessibility audits remain future work. On WebGL failure the default
Florida list remains available.

Recommended Phase 4: improve discovery and completeness for co-located museum
assertions, with measured full-Florida performance and accessible pagination.
Any geological text-to-age mapping requires a separately approved, authoritative,
versioned policy. Commercial use requires compatible permission from the rights
holder. No decision blocks this noncommercial Phase 3 slice.
