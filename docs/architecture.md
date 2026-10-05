# Architecture through Phase 3.5

One monorepo, Next.js and FastAPI, one PostgreSQL/PostGIS system of record. Scientific
providers are contacted only by explicit ingestion, never Explore. No new services
or dependencies were added for search or graph.

| Area | Responsibility |
| --- | --- |
| apps/web/lib/api | Typed contracts, shared context and sanitized fetch/error boundary |
| features/explore | URL state, search, cursor catalog, entity inspector, graph, continuity |
| features/map | One persistent MapLibre instance/worker, buffered point aggregates and notation |
| features/timeline | Central reference hierarchy, local previews, accessible range commits |
| apps/api/app/explore | Preserved occurrence evidence/detail and dataset status |
| apps/api/app/discovery | Reference policy, transactional projection, SQL context/search/graph routes |
| apps/api/app/ingestion | Official UFVP acquisition, conservative normalization, revision-aware persistence |
| apps/api/app/models.py | Canonical/provenance and typed derived entities |
| apps/api/migrations | Alembic-only schema, PostGIS and pg_trgm |
| apps/api/tests/fixtures | Isolated synthetic fixtures; no public generator |
| scripts/test_db.py, test_browser.py | Separate ephemeral PostGIS projects; browser owns production servers |

Canonical source data and its retained revisions remain the authority. Discovery is
an indexed projection rebuilt in a transaction after ingestion, using an advisory
lock. Readers retain the previous committed projection until the replacement commits.
A revision-hash/current/nonsynthetic evidence guard prevents stale material becoming
current silently. An index failure rolls back the projection savepoint and records a
failed ingestion; an explicit rebuild repairs it without refetching source data.

Geological intervals come from one pinned, attributed artifact. AgeInterpretation
retains source revision hash, policy version, exact assertion/rule/status and reference
bounds. Nothing writes derived ages into CollectionEvent's source numeric fields.
Source classification paths are dataset-scoped, based on explicit published fields.
Context terms have deterministic identities and typed membership links.

PostgreSQL simple full-text and pg_trgm indexes support search; exact accession/name,
prefix and partial matches have explicit ordering. Search spans six entity kinds
through catalog membership rather than interactive raw JSONB scans. Context and
pagination use real foreign keys, bounded limits and filter-fingerprinted cursors.
Geometry stays Point/4326. Exact coordinate equality defines a presentation aggregate,
not a merged locality. Map pages are exhausted before publishing a coherent buffered
window; client clusters sum catalog-assertion counts.

Graph neighborhoods use bounded SQL joins over the same active material context.
Specimen edges describe classification, location, custody and source context.
Aggregate roots explicitly describe shared catalog material. Balanced paging exposes
entity kinds progressively. SVG geometry is deterministic; native node buttons and
an edge list provide keyboard access. Twelve initial neighbors expand to a 24-node
view limit; further paging replaces the displayed neighborhood. No graph database,
physics engine or speculative relationship model exists. No source publication fields
were found, so no Publication table or bibliographic edges were introduced.

Explore owns the viewport. Search and time remain persistent; catalog and inspector
are optional overlays. The map remains mounted while relationships are visible.
Scientific pivots push URL history, map moves and typed query text replace it.
Popstate restores camera/context/time/selection/surface. Dragging previews locally;
release commits once, keyboard settles after 250 ms. Fetches debounce 180 ms, abort
superseded requests and reject stale completions. Prior points, rows, page ordinals
and graph neighborhoods remain while updating or recovering. A 25% geographic buffer
is reused inside its safe margin. Stable source diffs and selection filters avoid
recreating the map. Geography restores with jumpTo, including reduced motion.

FastAPI lifespan owns the engine; synchronous request-scoped SQLAlchemy sessions
use pre-ping and finite connection timeout. Pydantic validates paired bounds and
UUID context. Errors use sanitized envelopes. Source raw payloads are not exposed;
whitelisted source text and suppressed withheld coordinates preserve access boundaries.

Root environment configuration and the existing PostGIS development volume remain
unchanged. NEXT_DIST_DIR isolates validation builds. CI retains its PostGIS service
and migration round trip and adds a disposable production browser job. No deployment
or remote CI success is claimed. Basemap providers are cartographic infrastructure,
not additional scientific collections.

See [data model](data-model.md), [continuity](explore-continuity.md),
[ADR 0011](adr/0011-versioned-age-interpretations.md),
[ADR 0012](adr/0012-source-scoped-discovery.md) and [validation](phase-3.5-validation.md).

## FAST-2 browse execution

Request sessions apply transaction-local JIT-off and custom-plan settings lazily on
first database access. Ingestion sessions and server defaults retain their existing
policy. Catalog selects eligible cursor page identities before expanding age/detail
rows; current-source/hash/public guards remain mandatory before the limit. Two
additive covering indexes support locality paging and current-source checks. No new
projection, endpoint, or scientific model was introduced. Local development uses
an explicit IPv4 database hostname to avoid the measured localhost address fallback.
See [FAST-2 measurements and validation](browsing-performance.md#fast-2-server-and-database-browsing-performance).

## FAST-3 browse projections

Browse projections accelerate reads; they do not define scientific truth.

The existing discovery transaction now also builds disposable locality payloads
and taxon scalar summaries. A shared input revision and explicit derivation version
authorize their reads. Statement-level invalidation tracks canonical/discovery input
changes; atomic replacement publishes both tables together after validation. Failed
builds retain prior rows and use live computation when the input revision is dirty.
Application startup never rebuilds summaries.

Unfiltered locality and Lineage reads use these summaries. Arbitrary locality/time/
custody/text/geographic contexts still compute exact live results; hierarchy,
geography, material pages, and source evidence retain their established authority.
The client includes the projection revision in its existing cache revision observer.
See [derivation, eligibility, setup and failure rules](browse-projections.md) and
[FAST-3 validation](browsing-performance.md#fast-3-read-optimized-browse-projections).
