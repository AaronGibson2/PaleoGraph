# Canonical and provenance model through Phase 3

Alembic `0002_explore_schema` implements eight entities and four evidence link tables.
`0003_ufvp_specimens` adds narrowly scoped museum material and revision entities;
see [ADR 0010](adr/0010-ufvp-material-and-snapshots.md).

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
    Institution ||--o{ Collection : houses
    Collection o|--o{ Specimen : catalogs
    Specimen o|--o{ Occurrence : material
    SourceRecord }o--o{ Specimen : supports
    SourceRecord ||--o{ SourceRecordRevision : retains
    IngestionRun ||--o{ SourceRecordRevision : observes
```

## Identity and meaning

Entities use application-generated UUIDs and timezone-aware created/updated
timestamps. Fixture UUIDs have fixed v4 bits; ordinary inserts use `uuid4()`.
ORM updates maintain `updated_at`; direct SQL writers must do so too. Public
identity is the UUID. Names and optional future slugs are not permanent identity.

Occurrence links exactly one Taxon to one CollectionEvent. It is an evidence-supported
assertion, not a specimen. CollectionEvent owns source-specific age, stratigraphy,
and context and may reference a Locality. Locality represents a geographic place
and owns coordinates. Taxon names are navigation concepts, not a universal authority;
matching names do not trigger merging.

Specimen represents cataloged physical material, including catalog lots containing
multiple pieces. Institution and Collection describe custody; no global registry
is asserted. Occurrence.specimen_id is nullable to preserve nonmaterial assertions.
Specimen preserves original institution/collection/catalog codes, occurrenceID,
materialEntityID when supplied, other source identifiers, preparations and the
source individualCount string. Catalog triplets are deliberately not unique.
`specimen_evidence` uses real foreign keys and a composite primary key.

The UFVP adapter hashes dataset-scoped source IDs into deterministic UUIDs with v4
layout. These are opaque adapter identities, not random v4 IDs or globally
authoritative specimen identifiers. Catalog edits preserve identity; source core
ID changes create distinct assertions. Taxa group exact source classifications
including qualifiers; localities group exact source geographic metadata including
locationID. No fuzzy or cross-source matching occurs.

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

The seed represents two fixed completed synthetic snapshots. Real UFVP runs also
record accepted counts, importer version, scope and snapshot JSONB (verified metadata,
archive URL, SHA-256, retained path and retrieval time). Archives are content addressed
and retained outside git. SourceRecordRevision stores each distinct row hash/raw JSONB
once with its first observing run. The importer never overwrites a revision; the
database does not install an immutable-row trigger. Reobservations update current
run/last_seen without duplicating material or revisions.

Only a successful complete Florida run deactivates unseen source records. Samples,
partial and failed runs do not; no canonical object is hard deleted. Current evidence
links follow the latest interpretation, while prior values remain in revisions/raw
archives. Detail reports the record's observing run version rather than the dataset's
newer current version. Raw payloads are not exposed by Explore; selected safe source
text fields are exposed separately from canonical interpretation.

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
UFVP supplies geological labels, not numeric Ma. Its era/period/epoch/zone/group/
formation/member strings are retained without conversion; numeric bounds stay NULL.

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
Museum mode excludes synthetic evidence; explicit demo mode uses it. The map joins
the optional specimen to display catalog identifiers. Coordinates normalize only
from accepted WGS84 aliases; unsupported/unknown datums remain unmapped, never guessed.

## Migration and deferred choices

0001 remains unchanged. 0002 creates tables in dependency order and reverses them
on downgrade. Downgrade loses application data; exercise it only on disposable DBs.
PostGIS is intentionally retained. Connections use `search_path=public` to keep
Tiger/topology schemas outside application autogeneration. Alembic ignores the
PostGIS-owned spatial_ref_sys and explicitly renders GeoAlchemy types.

0003 is additive and downgrades museum entities before the older schema. Existing
0001 and 0002 remain unchanged. Downgrades belong only in disposable validation.
EntityIdentifier registries, merge redirects, field-level assertions, canonical
conflict preferences and cross-source reconciliation remain deferred. See
[UFVP ingestion](ufvp-ingestion.md) for normalization and lifecycle rules.
