# Data model

PaleoGraph models evidence and identity separately. Application UUIDs supply stable navigation identities; source IDs remain scoped to their provider and dataset. Equal labels do not collapse records across sources. Reconciliation adds inspectable relationships rather than replacing source identities.

## Sources and revisions

| Term | Meaning |
| --- | --- |
| Source | Dataset provider, such as UFVP or PBDB |
| SourceDataset | Provider-scoped identity, version, retrieval, citation and rights |
| IngestionRun | Snapshot, scope, adapter version, status and counts |
| SourceRecord | Identity scoped by dataset, record type and original source ID; currentness and latest observed hash |
| SourceRecordRevision | Distinct retained raw content revision keyed by source record and content hash |
| NormalizedSourceRevision | Typed adapter output and version/proof frame, distinct from raw wording |
| SourceNormalizationCurrent | Pointer to the current normalized revision |
| SourceRecordDependency | Exact supporting revision membership, including transitive dependencies |
| SourceArchive | Verified content-addressed cold evidence and manifest metadata |

Raw revisions may be inline or archive-backed without changing identity or meaning. A missing archive is unavailable evidence, never permission to substitute a newer response. Versioned normalization and interpretation explain how displayed assertions were derived.

## Material, occurrence, place and taxonomy

**Specimen** represents cataloged physical museum material, including lots with multiple pieces. Institution and Collection describe custody. Original catalog codes, identifiers, preparation and source count strings remain evidence. A catalog number alone is not globally unique.

**Occurrence** links a source-supported taxonomic assertion to a CollectionEvent. Its Specimen link is optional. PBDB occurrences do not automatically create physical Specimens; explicit material and measurements remain independent evidence roles.

**CollectionEvent** holds collecting/occurrence context, source geology and numeric bounds. A PBDB fossil collection is a provider spatiotemporal grouping, not a museum Collection. **Locality** is a geographic place with nullable accepted Point/4326 geometry, original coordinates, uncertainty, generalization and withholding. Equal coordinates aggregate presentation counts without merging identity.

**Taxon** is a source-scoped navigation concept. UFVP classifications and PBDB entered/accepted concepts retain distinct identities. ClassificationLink and TaxonPath describe source membership, not phylogenetic ancestry. IdentificationEvidence retains original, later, accepted and qualified roles and explicit supporting revisions/references.

## Time and references

ProviderAgeEvidence retains PBDB calibrated envelopes independently of determined date/error/unit/method tuples. CollectionEvent bounds describe source-normalized evidence. GeologicalInterval is a pinned reference concept; AgeInterpretation records the selected UFVP label, raw revision hash, policy, rule/status and reference interval. Derived envelopes never overwrite source numeric fields. [Scientific semantics](scientific-semantics.md) defines filtering.

ResearchReference stores explicit bibliography. Identification, collection, material and opinion reference roles remain distinct. A dataset citation is not a specimen-to-paper relationship; metadata grants no rights to full text.

## Reconciliation and provenance

ReconciliationGeneration pins policy and the complete source frame. ReconciliationAssessment retains each material assertion's raw/normalized revision and identifier decision. ReconciliationEdge records typed target material, supporting revision, status, reference and context diagnostics. ReconciliationReview is separate; accepting a candidate does not establish deterministic identity.

Current `material-id-v1` requires explicit institution, collection and catalog identifiers and exactly one physical target at that full key. Missing collection, ambiguous syntax, multiple targets or unsupported identifiers remain candidates or unresolved. Context disagreement stays inspectable. No fuzzy matching or inferred museum namespace silently creates identity.

Typed foreign keys connect occurrences, taxa, localities, events, specimens and source evidence. Complete dependency proofs remain recoverable while indexed authority accelerates currentness checks. Historical and current evidence are distinct; revisions and interpretations survive repairs.

## Discovery projections

CatalogEntry and CatalogTerm provide searchable membership, explicit material/occurrence kind, age basis and indexed context. ContextTerm separates source geology, stratigraphy, NALMA and other biochronology. Locality/taxon summaries, classification membership and browse authority are rebuildable projections, not new assertions.

Discovery checks nonsynthetic membership, active policy, current revision and dependency eligibility. Dirty generations fall back to guarded live reads. Failed/partial imports never deactivate unseen records; only a successful complete source scope can do so. Canonical objects are not hard-deleted merely because a later snapshot omits them.
