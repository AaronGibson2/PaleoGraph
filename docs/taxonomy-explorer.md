# Florida taxonomy explorer

The Lineage navigation opens Florida Taxonomy at `/lineage` or `/explore?surface=lineage`. Expand source-supported ranks, search for a group, or select a node for evidence and provenance. Classification is not phylogeny.

## Browse placement

The explorer is a provider-neutral, reversible projection over retained eligible Florida evidence. It never replaces source Taxon identities or reconciles physical material. Names use Unicode NFKC, case folding and whitespace normalization; authorship and qualifiers are not stripped, and no fuzzy equivalence is inferred.

The `unified-v2` projection aligns compatible source concepts onto a compact ranked directory, using UFVP's retained hierarchy as the display spine where both providers overlap. Matching names need a unique compatible rank and parent context, not identical intermediate levels. Extra ranks and explicitly nested source clades do not create parallel copies of ordinary groups. Equal ranks, clade/ranked representations, and order/suborder representations can align; other incompatible ranks remain separate. Overlapping nearest ranked parents must agree or be explicitly nested in one retained path, and shared anchors must occur in the same order. A shared family within compatible class context can bridge a higher-order disagreement; the dossier explicitly reports it. Different explicit families or genera remain isolating. A shared kingdom inherits its unique retained upper context, so Animalia occurs beneath Life rather than beside it.

Every source UUID and provider concept key remains associated with the resulting node, with complete original supplied paths and archived proofs. This is display placement, not canonical identity or a replacement provider assertion. UFVP identification hashes are not canonical provider identifiers. Ambiguous same-provider canonical IDs, qualified identifications, incompatible parent families, missing ranks and ambiguous target contexts remain distinct; an ambiguous parent also isolates descendants. No fuzzy spelling/synonym equivalence is inferred. Additional provider levels remain in source details, and source-only branches with represented evidence remain browsable.

Missing source relationships are never added to source evidence. The initial path-completion pass uses two supplied rank/name anchors and a unique retained upper prefix. The subsequent unified display alignment can use a unique compatible ranked group and shared parent context; adjusted memberships are marked `browse_path_adjusted`, with complete supplied paths preserved. Partial and unresolved classifications retain labeled browse containers whenever no unique safe placement exists. Additional source ranks remain inspectable in details even when the default display route is shorter.

Stable UUIDv5 source-path node identities use `taxonomy-browse-v1`; the projection version additionally includes `unified-v2`, the UFVP time policy and the PBDB age policy. Retained spine IDs stay stable as displayed paths change. Migration `0017_taxonomy_browse_alias` preserves merged display-node URLs through explicit unique source-concept membership redirects, including across repeated rebuilds. Source-taxon URLs continue to resolve through retained memberships. Ambiguous mappings never redirect arbitrarily. A changed input revision or projection version makes the snapshot stale until rebuilt.

## PBDB source hierarchy

PBDB occurrence exports supply selected conventional ranks, not a complete parent graph. Florida enrichment starts from unique typed `identified_no` and `accepted_no` selectors, preserves exact spelling variants, and follows provider parent identities. It uses PBDB Data Service 1.2 [`taxa/list`](https://paleobiodb.org/data1.2/taxa/list_doc.html) with comma-separated `taxon_id`, `rel=exact`, and `show=immparent,attr,ref,crmod`. Actual containment uses nonzero `immpar_no` when supplied, otherwise `parent_no`. Accepted-name edges remain separate. `orig_no`, `taxon_no`, name, rank, status/difference, timestamps, references, and both parent fields remain inspectable.

Every supplied intermediate level is retained in source paths and proofs, including repeated ranks and unranked clades. A PBDB path can begin Life ? Eucarya ? Opisthokonta ? Animalia; the unified display shares this upper context while using a shorter ranked route below it. Source-only intermediate levels need not appear as a second route to the same shared group. Equal labels with incompatible containing contexts remain separate. A broad unranked terminal clade with an omitted parent is treated as a source graph boundary only after an archived `rel=immpar` query returns no containing concept. Parentless lower taxa, missing targets and cycles remain partial. This completeness describes the available provider graph, not a claim of taxonomic consensus.

Entered occurrence names remain visible. A supported recombination or synonym does not discard the higher path: for example, Lutra canadensis retains its variant identity and accepted Lontra canadensis link beneath PBDB's Lontra classification. Velates floridanus retains its distinct synonym concept and accepted Velates perversus link. PBDB's [structured serializer](https://github.com/paleobiodb/data_service/blob/fc3f9a38102d789f0739ff7de3dc0944fbe1d2ed/lib/PB2/OccurrenceData.pm#L252) deduplicates an `identified_no` equal to `accepted_no`, including in verbose JSON. An explicit accepted assignment with identical unqualified name/rank and no reported difference retains that supported identity. Missing `identified_no` alone therefore does not mean unresolved classification.

When an entered name has no numbered identity and differs from its accepted assignment, its verbatim identification is displayed in the explicit accepted assignment's context with **unresolved identity**; the final display link is labeled as identification context, not an asserted taxonomic child. Bufo woodhousei fowleri is such a case: PBDB supplies the accepted species Bufo woodhousei, without a distinct identifier for the entered subspecies. No subspecies identity is fabricated.

[`taxa/opinions`](https://paleobiodb.org/data1.2/taxa/opinions_doc.html), `op_type=class`, retains selected classification opinions, their parent/status, basis and references. A name-authority reference is not presented as the parent-edge citation. The original occurrence snapshot, identification history, source ages and coordinates are never rewritten by taxonomy enrichment.

Acquisition uses sequential batches of 100 unique selectors, bounded responses and retries, and cached immutable responses. These are client safeguards; the reviewed official documentation supplies no numeric rate quota or maximum comma-ID batch. Paging follows actual record arrays until a short/empty page and rejects repeated pages. PBDB count metadata can be inconsistent at nonzero offsets. Exact selector resolution is retained when PBDB returns a variant with a different `orig_no`; typed IDs are not silently interchanged. Rejected selectors retain explicit diagnostics and any witnessed retained alias routing.

Four additive tables retain immutable snapshot metadata, selector-to-concept records, parent/accepted dependencies, and the active Florida snapshot. Raw responses and retained source revisions use the existing content-addressed archive store, verified hashes and READY-last publication. Offline replay verifies graph fields and opinions against their raw proof rows before atomically publishing the active graph and rebuilding the browse projection. Existing scientific tables remain unchanged. Detail exposes snapshot/revision hashes and source relationships without revealing archive filesystem locations.

## Evidence and time

Rows show inclusive **evidence records**, not organisms or individual specimens. Details distinguish UFVP material-associated assertions from PBDB published occurrences and expose both direct and descendant-inclusive counts. Each source assertion belongs to one leaf and is counted once in each displayed ancestor. Reconciliation candidates do not subtract potential overlap. Source filters change represented evidence, while provenance remains inspectable across both providers.

Temporal detail preserves source numeric bounds, interpreted reference envelopes and unknown/partial ages. Envelopes describe represented evidence, not evolutionary origin, extinction or continuous biological duration. Existing inclusive-overlap time filters remain conjunctive with locality and source-taxon context. PBDB coordinates remain withheld from Atlas.

## Interaction

Roots and immediate children load lazily, with at most 100 children per page. Expanded branches retain cached pages; deliberate hover/focus can prepare one intended branch. Large visible trees are windowed to a bounded number of rows. Search returns up to 20 contextual matches, disambiguated by rank, source and parent path. Exact normalized names precede prefix matches, followed by other substring matches, so searching Smilodon does not put Rhizosmilodon first. Selecting a result loads its ancestors and a bounded batch of their first child pages, expands the path, and scrolls/focuses the selected row. Each batch covers at most 64 ancestor groups using fixed-count SQL queries, avoiding one HTTP request per ancestor on deep PBDB paths. Manual expansion still loads one immediate branch. A focused node beyond the first sibling page remains reachable without downloading every sibling.

Deep paths retain distinct parent/child indentation relative to the visible portion of the tree; full depth remains in accessibility levels and the selected breadcrumb. Scroll anchoring is disabled inside the virtual tree so browser repositioning cannot unmount the restored focused row during Back/Forward navigation.

`taxonomy_focus=<browse UUID>` restores selection through reload and browser Back/Forward. Expanded-state lists are not encoded in URLs. Legacy `lineage_focus=<source Taxon UUID>` links resolve through explicit projection associations and are canonicalized. Requests are cached by context, coalesced, canceled and guarded against stale results; a failed new selection cannot display the previous node's evidence under the requested identity.

The tree exposes tree/treeitem semantics, rank depth and expansion state. Up/Down and Home/End move focus; Right expands or moves to a child; Left collapses or moves to the parent; Enter/Space selects. Search supports Up/Down, Enter and Escape. Source concept selection for linked views remains explicit; an existing source-taxon filter remains conjunctive.

## Read API

All paths are below `/api/v1/taxonomy` and accept the existing context filters plus `source=all|ufvp|pbdb`, bounded `limit` and `offset`.

| Endpoint | Contract |
| --- | --- |
| `/roots` | Top-level nodes with source-aware summaries |
| `/nodes/{id}/children` | Immediate children, total and next offset |
| `/nodes/{id}/ancestors` | Root-to-parent path; no evidence preview work |
| `/nodes/{id}/branch-children` | First child pages for at most 64 ancestors, with parent-batch pagination; same source/context filters |
| `/search?q=...` | Bounded contextual matches with rank and path |
| `/nodes/{id}` | Node, ancestors, first 30 source concepts and up to 12 evidence/locality previews |
| `/nodes/{id}/concepts` | Complete source-concept memberships through pagination; provenance includes both sources |

Nodes expose `id`, `parent_id`, `name`, optional `rank`, placement status, path, source presence and typed counts. Counts are selected-context values; source presence describes the underlying snapshot. Detail previews retain original specimen/occurrence IDs and never include accepted PBDB coordinates. Open represented evidence for identification history and explicit references. Unknown IDs return 404; stale/unbuilt projections return a recoverable 503. Empty contexts remain empty rather than falling back to unfiltered counts.

## Projection lifecycle and limits

Migration `0015_taxonomy_browse` adds five rebuildable PostgreSQL tables; `0016_pbdb_taxonomy_hierarchy` adds the four source-graph tables; `0017_taxonomy_browse_alias` adds derived display redirects. Build with `python -m app.taxonomy.build` after upgrading an existing populated database. `python -m app.taxonomy.acquire --help` describes bounded Florida ancestry acquisition and verified offline replay; choose an external archive/checkpoint location with adequate storage. Acquisition alone does not publish database changes. Subsequent successful imports refresh the browse projection within the existing transaction; advisory locks and input-revision checks prevent overlapping publication. The normal explorer reads indexed projections and never traverses source proofs interactively.

This release uses retained Florida evidence only. Completeness follows provider snapshots: unsupported relationships stay absent, and unresolved identity can leave separate branches. The evidence preview is capped at 12; complete concept membership is paginated. Additional ranks appear when supplied in the retained source graph or identifications; unsupported intermediate ancestry is not inferred. A focused node filtered to zero evidence retains its stable identity and explicitly reports the empty context. Global taxonomy readiness requires separate scope, acquisition and restore validation; this feature performs no global ingestion.
