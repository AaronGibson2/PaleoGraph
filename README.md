# PaleoGraph

A paleobiology atlas connecting occurrence assertions across time, geography,
taxonomy, and source collections. Phase 2 implements `/explore` end to end:
Next.js → typed API client → FastAPI → SQLAlchemy → PostgreSQL/PostGIS.

**All 40 seeded occurrences are synthetic development examples.** Taxon, age,
and place associations are invented, not scientific evidence. No external
scientific data has been downloaded or integrated.

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
| `NEXT_PUBLIC_MAP_STYLE_URL` | MapLibre style URL; example: `https://tiles.openfreemap.org/styles/positron` |
| `TEST_DATABASE_URL` | Explicit opt-in to tests against a migrated disposable database |

`NEXT_PUBLIC_*` values are public and embedded at build time. Restart development
or rebuild production after changes. Blank style configuration provides a neutral
canvas and notice. Basemap tiles require network access and retain provider
attribution. OpenFreeMap is a development example; choose provider/terms before
public release. No permanent production basemap choice has been made.

## Schema and seed

New migration `0002_explore_schema` adds Source, SourceDataset, IngestionRun,
SourceRecord, Taxon, Locality, CollectionEvent, Occurrence, and four evidence link
tables. Existing `0001_enable_postgis` is unchanged. Only Alembic owns schema
changes. See the [data model](docs/data-model.md) for relationships and constraints.

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

Map queries require `west`, `south`, `east`, `north`. Optional `older_ma` and
`younger_ma` must be supplied together (0–10000 Ma, older ≥ younger). `limit`
defaults to 200, maximum 1000. Example:

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
uv run --project apps/api ruff check apps/api scripts/test_db.py
uv run --project apps/api ruff format --check apps/api scripts/test_db.py
uv run --project apps/api mypy --config-file apps/api/pyproject.toml apps/api/app
uv run --project apps/api pytest apps/api/tests
uv run --project apps/api python scripts/test_db.py
```

Ordinary pytest uses an unreachable database URL; 23 integration cases skip unless
`TEST_DATABASE_URL` is supplied. **Prefer `make test-db`** (last command above): a
separate `paleograph-test` Compose project on port 55432 uses ephemeral storage,
runs upgrade/repeat/downgrade/re-upgrade/drift checks and integration tests, then
removes that project. It never uses the normal development database. Do not point
manual integration runs at valuable data.

For browser checks, migrate/seed and run both servers first:

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
`dev-api`, `dev-web`, `test`, `test-db`, `lint`, `typecheck`, `build`.

## Boundaries and next work

Occurrences are assertions, not physical specimens. Localities and collection
contexts are separate. PaleoGraph is not a universal taxonomic authority. No
specimen/identifier registry, real ingestion, reconciliation, field-level evidence,
search, graph, accounts, AI, or deployment is included.

Explore caps results without pagination/server clustering. Controls default to 0–12 Ma
and extend for larger URL age ranges. Generalization rings indicate status, not a
measured uncertainty radius. Missing locations can be inspected by UUID but are
absent from the spatial list. Production scale, a formal timescale, and broad
cross-browser/accessibility audits remain future work. On WebGL failure the default
Florida list remains available.

Recommended Phase 3: choose one bounded Florida vertebrate source dataset and
agree on licensing, identifiers, sensitivity, snapshot lifecycle, and conflict
rules; implement one auditable raw → normalized → canonical adapter. No human
decision blocks this synthetic slice. Stop here until that phase is authorized.
