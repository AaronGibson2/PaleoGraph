# Scientific semantics

PaleoGraph separates retained source assertions, normalization and interpretation. These distinctions apply to contracts, filters, counts, visualizations and tests.

## Material and identity

Occurrence is evidence of a taxonomic assertion in a collecting/time/place context. Specimen is physical museum material and may be a lot of multiple pieces. Occurrence, specimen, piece and organism counts are not interchangeable. PBDB material/measurement assertions do not establish canonical physical-object identity.

Taxonomy remains source-scoped. Original identification, reidentification, accepted name, qualifiers and bibliographic opinions are separate roles. Equal names do not prove equal concepts. Taxonomic classification is not phylogeny.

Reconciliation candidates indicate possible material relationships. Deterministic identity requires the versioned identifier policy and an unambiguous physical target. Identities, conflicting context and exact supporting revisions remain preserved; candidate review does not silently upgrade identity or subtract overlap from counts.

## Geological time

Source geological labels, numeric ages and biochronology remain independent. Collecting dates, source modification, retrieval and interpretation timestamps are not fossil ages. Derived envelopes never overwrite source numeric bounds.

UFVP's conservative exact-label policy (`ufvp-geology-v1`) uses pinned ICS 2026/06 and selects the finest populated age field. Unresolved finer wording cannot fall back to a broader period. Alternatives, uncertain or unsupported labels remain ambiguous/unmapped; missing evidence remains absent. NALMA stays source biochronology and is not converted to Ma without supported evidence. Formations and locality names do not supply inferred ages.

PBDB envelopes retain provider calibration and policy (`pbdb-provider-envelope-v1`), including interval/time-scale identity. Determined date/error/unit/method tuples remain separate; they are not silently converted or relabeled as ICS-derived ages.

Reference uncertainty belongs to calibration, not specimen measurement. The [ICS artifact](source-data/ics-2026-06.json) retains hierarchy, precision, citations and original RDF values alongside two official-PDF-supported corrections: the Miocene/Aquitanian base and Ludlow/Ludfordian top. Attributed [Cenozoic](source-data/ics-2026-06-cenozoic-detail.png) and [Silurian](source-data/ics-2026-06-silurian-detail.png) chart details preserve audit evidence. Eight separately cited subepoch compositions do not invent a formal Middle Pliocene or unsupported numeric biochronology.

Discovery chooses complete source numeric bounds when available, otherwise a supported derived envelope, otherwise no range. Its age basis states the distinction. Bounds are finite/nonnegative, older ≥ younger; zero is present, not unknown. Either source endpoint may be absent without inventing its counterpart.

All active discovery filters use inclusive closed overlap:

```text
record.younger_ma <= selected.older_ma
AND record.older_ma >= selected.younger_ma
```

Both record endpoints must exist; boundary contact counts. All ages includes partial/unresolved evidence; numeric selection excludes it. Legacy `/map/occurrences` filters source bounds only; current Atlas uses effective-age discovery. Aggregate envelopes use complete included ranges: they are not exact locality ages, proof of contemporaneity or continuous presence. Display rounding never changes stored/filter values.

## Atlas and Lineage

Atlas maps accepted public coordinates as longitude/latitude Point/4326. Only supported WGS84 datum aliases normalize. Missing, unknown or withheld positions remain unmapped, never 0,0. Uncertainty/generalization remain explicit. Coordinate stacks and clusters count evidence assertions without merging localities or measuring abundance.

PBDB coordinates remain withheld from Atlas until datum/CRS semantics are sufficiently verified. Modern coordinates and reconstructed paleopositions remain retained and distinct. Unmapped occurrences remain searchable in source contexts and nonspatial catalogs; they are not assigned to the map viewport.

Lineage shows source classification and observed source-supported material/occurrence evidence through time. It does not establish evolutionary origin, divergence timing, extinction timing, uninterrupted presence or complete geographic range. Gaps can reflect collection, publication, preservation and coverage. Filtering selects overlapping evidence without clipping its reported endpoints.

Decorative archetypes indicate reviewed classification membership, not specimen images, reconstructed organisms, phylogeny or morphological evidence. Unknown/ambiguous membership stays neutral.

## Version and provenance

Source assertions are not silently overwritten by interpretations. Policy IDs, source hashes, typed links and full proofs bind displayed interpretations. Scientific policy/reference changes require versioning, projection repair and validation. Obsolete interpretations stay historical, not current deployed results. Source absence never proves biological absence.
