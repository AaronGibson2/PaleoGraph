# Phase 2 canonical and provenance model

Alembic `0002_explore_schema` implements eight entities and four evidence link tables.

```mermaid
erDiagram
    Source ||--o{ SourceDataset : publishes
    SourceDataset ||--o{ IngestionRun : tracks
    SourceDataset ||--o{ SourceRecord : namespaces
    IngestionRun ||--o{ SourceRecord : records
    SourceRecord }o--o{ Taxon : supports
    SourceRecord }o--o{ Locality : supports
    SourceRecord }o--o{ CollectionEvent : supports
    SourceRecord }o--o{ Occurrence : supports
    Locality o|--o{ CollectionEvent : locates
    CollectionEvent ||--o{ Occurrence : contextualizes
    Taxon ||--o{ Occurrence : identifies
```

## Identity and meaning

Entities use application-generated UUIDv4 IDs and timezone-aware created/updated
timestamps. Fixture UUIDs have fixed v4 bits; ordinary inserts use `uuid4()`.
ORM updates maintain `updated_at`; direct SQL writers must do so too. Public
identity is the UUID. Names and optional future slugs are not permanent identity.

Occurrence links exactly one Taxon to one CollectionEvent. It is an evidence-supported
assertion, not a specimen. CollectionEvent owns source-specific age, stratigraphy,
and context and may reference a Locality. Locality represents a geographic place
and owns coordinates. Taxon names are navigation concepts, not a universal authority;
matching names do not trigger merging.

`taxon_evidence`, `locality_evidence`, `collection_event_evidence`, and
`occurrence_evidence` provide many-to-many mappings with composite primary keys and
real foreign keys. There is no unchecked polymorphic entity ID. The map requires
current occurrence evidence; detail also displays historical evidence. No general
write API exists. See [ADR 0009](adr/0009-occurrence-context-and-evidence.md).

## Provenance

Source identifies a provider (unique name). SourceDataset carries an external ID
scoped to its Source, title, publisher, URL, citation, DOI, license, rights holder,
version, publication/retrieval dates, and synthetic flag. NULL external dataset
IDs are permitted without claiming the datasets are identical.

IngestionRun records status, timestamps, nonnegative counts, source version, and
error summary. SourceRecord identity is scoped by
`(source_dataset_id, record_type, source_record_id)`. It retains raw JSONB, hash,
source URL/modification time, basis of record, license/rights/access metadata,
withholding/generalization notes, ingestion time, first/last seen, and current flag.
A composite foreign key prevents linking a record to another dataset's run.

The seed represents two fixed completed synthetic snapshots. Actual import lifecycle,
revision history, snapshot completeness, and reconciliation are not implemented.
Before real imports, define immutable raw retention and source-record revision/run
relationships. Failed or partial runs must never deactivate unseen records. Missing
licenses remain missing, never inferred. Explore does not expose raw payloads.

## Geological age

Only CollectionEvent owns normalized `older_ma` and `younger_ma`; occurrences inherit
them. PostgreSQL NUMERIC has no fixed scale. Original early/late interval names remain
separate. Known bounds must be finite/nonnegative and older ≥ younger. Either may
be NULL; 0 is present, never unknown. JSON numbers are a presentation convenience,
not a precision claim.

`app/explore/queries.py:age_overlap` implements the central closed-interval rule:

```text
record.younger_ma <= selected.older_ma
AND record.older_ma >= selected.younger_ma
```

Both record bounds must be known. Endpoint contact counts. Without a filter,
unknown/partial intervals remain eligible; active filters exclude them rather
than guessing. API ranges require both finite ordered bounds within 0–10000 Ma
(an API guard, not a database definition). The frontend sends bounds and displays
backend results without independent age filtering.

`/api/v1/time-intervals` serves `demo-windows-v1`: four numeric windows from 12–0 Ma.
These are explicitly not named formal periods. A versioned authoritative timescale
can replace the configuration later without scattering definitions through the UI.

## Geography and queries

Locality.geom is the normalized authority: nullable `geometry(Point,4326)` with
GiST index. X is longitude (−180..180), Y latitude (−90..90); empty/invalid points
are rejected. Original coordinate strings, datum, nonnegative finite uncertainty
and precision, generalization, and withholding are separate metadata. Withheld
implies NULL geom. Unknown never becomes 0,0. API coordinates derive from geometry;
detail additionally suppresses withheld coordinates defensively.

Explore uses inclusive `ST_Intersects` with SRID-4326 envelopes. West > east splits
into west..180 OR −180..east. South ≤ north. World-spanning client views normalize
to −180..180. A zero-width envelope is a boundary query, not the whole world.
Generalized points remain selectable and visibly marked. No distance query exists.

The map query joins occurrence/event/locality/taxon in one statement and uses EXISTS
for evidence state. Stable UUID ordering and limit+1 detect truncation without a
full count. B-tree indexes on event.locality_id and occurrence.collection_event_id
support spatial joins; primary/unique indexes cover identity/evidence access.
Detail eager loading takes two statements, not one query per evidence record.
Measure scale before adding age indexes, server clustering, or pagination.

## Migration and deferred choices

0001 remains unchanged. 0002 creates tables in dependency order and reverses them
on downgrade. Downgrade loses application data; exercise it only on disposable DBs.
PostGIS is intentionally retained. Connections use `search_path=public` to keep
Tiger/topology schemas outside application autogeneration. Alembic ignores the
PostGIS-owned spatial_ref_sys and explicitly renders GeoAlchemy types.

EntityIdentifier, Specimen, merge redirects, field-level assertions, canonical
conflict preferences, source-specific quarantine, and real ingestion are deferred.
Before Phase 3 select the Florida dataset, rights/sensitivity policy, source identity,
complete-snapshot semantics, and evidence-based reversible reconciliation rules.
