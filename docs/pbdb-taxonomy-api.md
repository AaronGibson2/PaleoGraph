# PBDB taxonomy API: hierarchy acquisition

Verified against official documentation, official service source, and bounded live GETs on **2026-10-20**. This note concerns the canonical checkout only. The observed official `paleobiodb/data_service` master commit was `2401eafe079202cc4ac5607c64216f192556f451` ([commit](https://github.com/paleobiodb/data_service/commit/2401eafe079202cc4ac5607c64216f192556f451)). The public service can change independently of that source revision; archive responses rather than treating current answers as immutable.

## Endpoints and request shape

| Purpose | Structured endpoint and parameters |
| --- | --- |
| Resolve a bounded set of supplied identities | `/data1.2/taxa/list.json?taxon_id=txn:…,var:…&rel=exact&show=immparent,attr,ref,crmod&vocab=pbdb&extids=yes` |
| Check actual containing identity | `/data1.2/taxa/list.json?taxon_id=txn:…&rel=immpar&show=immparent&vocab=pbdb&extids=yes` |
| Retain the selected classification opinion | `/data1.2/taxa/opinions.json?taxon_id=txn:…&op_type=class&show=basis,ref,crmod&vocab=pbdb&extids=yes` |

`taxon_id` accepts comma-separated identifiers; `id` is its alias. `rel=exact` selects the matching names, `rel=current` selects current variants, and `rel=accepted` also resolves synonym/invalid-name assignments. `rel=immpar` returns the immediate containing taxon even when it is a junior synonym; `rel=parent` substitutes the senior synonym. `rel=all_parents&immediate` is another documented ancestry query. The bounded frontier walk avoids requesting a whole subtree. [Taxa list documentation](https://paleobiodb.org/data1.2/taxa/list_doc.html)

`op_type=class` selects opinions algorithmically chosen by PBDB as classification opinions. The default is `all`, which also includes historical, unselected opinions. Preserve the opinion's `status`: its `parent_no` may express a synonym or other opinion relationship, so it is not independently a containment edge. [Taxa opinions documentation](https://paleobiodb.org/data1.2/taxa/opinions_doc.html)

## Identity and parent semantics

`txn:N` selects the currently accepted **variant of the named taxon**; `var:N` selects the exact spelling/rank variant with that record number. These differ from resolving the accepted senior synonym. Pure numeric identifiers are deprecated. Preserve the supplied type and the returned identity mapping; matching numeric suffixes do not establish that two selectors are interchangeable. [Identifier documentation](https://paleobiodb.org/data1.2/general/identifiers_doc.html), [single-taxon selector examples](https://paleobiodb.org/data1.2/taxa/single_doc.html)

| Field | Meaning and acquisition policy |
| --- | --- |
| `orig_no` | Provider taxonomic-name identity; output as `txn:` with `extids=yes`. |
| `taxon_no` | Selected spelling/rank variant; output as `var:`. Keep both IDs. |
| `taxon_name`, `taxon_rank` | Returned variant's supplied name/rank; do not manufacture omitted ranks. |
| `parent_no` | Containing taxon, substituting its senior synonym if present. |
| `immpar_no` | Actual immediate containing taxon, including a junior synonym. Prefer this when supplied. |
| `accepted_no`, `accepted_name`, `accepted_rank`, `difference` | Accepted-name assignment and reason; retain separately from containment. |
| `reference_no`, `primary_reference`, `created`, `modified`, `taxon_attr`, `flags` | Retain as source provenance, alongside both parent fields and names. |

The field meanings and output blocks are documented in [taxa/list](https://paleobiodb.org/data1.2/taxa/list_doc.html). The official serializer marks `immpar_no` as deduplicated against the underlying senior-parent ID, explaining why `show=immparent` can still omit it when the two are equal. Consequently `immpar_no` followed by `parent_no` is supported; omission alone does not mean parentless. The source also converts `orig_no`/parent/accepted identifiers to `txn:` and variant identifiers to `var:`. [Official TaxonData serializer](https://github.com/paleobiodb/data_service/blob/2401eafe079202cc4ac5607c64216f192556f451/lib/PB2/TaxonData.pm#L232), [identifier conversion](https://github.com/paleobiodb/data_service/blob/2401eafe079202cc4ac5607c64216f192556f451/lib/PB2/TaxonData.pm#L3998)

An absent classification is documented as possible. A missing parent on an ordinary taxon does not certify a root. An empty archived `rel=immpar` response can support an available-service boundary, but does not establish biological consensus. This is an acquisition inference, not an additional PBDB guarantee. [Field availability](https://paleobiodb.org/data1.2/taxa/list_doc.html)

## Batching, pagination, diagnostics, and provenance

Use explicit `vocab=pbdb` because JSON defaults to compact field names. `extids=yes` makes typed IDs explicit. `limit` and zero-based `offset` support paging. `rowcount` requests result counts; `datainfo=yes` instead supplies provider, license, access time, query URL, and parameters. `strict=yes` converts warnings into errors; without it, PBDB can return good records while reporting bad/ignored inputs. [Special parameters](https://paleobiodb.org/data1.2/special_doc.html)

The reviewed official pages document comma-ID lists but publish no numeric request-rate quota or maximum ID-list length. The local 100-selector batches, 1,000-record pages, sequential requests, response-size/depth/concept bounds, and bounded transient retries are client policies. Continue paging from actual `records` arrays until a short page, detect repeated pages, retain warnings, and do not silently publish a truncated closure. A sequence of live requests has no documented snapshot-isolation guarantee. Save exact raw response bytes, request parameters, retrieval time, source license, content hashes, and row references so replay uses the acquired evidence. [List selector documentation](https://paleobiodb.org/data1.2/taxa/list_doc.html), [pagination and datainfo documentation](https://paleobiodb.org/data1.2/special_doc.html)

Occurrence `identified_no` has a separate serialization caveat: the official basic occurrence block declares deduplication against `accepted_no`, although its prose describes omission in compact vocabulary. A missing field therefore needs the surrounding identity/name/rank evidence; it does not alone prove an unnumbered identification. [Official OccurrenceData block](https://github.com/paleobiodb/data_service/blob/2401eafe079202cc4ac5607c64216f192556f451/lib/PB2/OccurrenceData.pm#L252)

## Live observations and implementation discrepancy

1. A bounded [Hydrictis request](https://paleobiodb.org/data1.2/taxa/list.json?taxon_id=txn:41115&rel=exact&show=immparent,attr,ref,crmod&vocab=pbdb&extids=yes&datainfo=yes&strict=yes&limit=5&offset=0) returned `orig_no=txn:41115`, `taxon_no=var:41115`, `parent_no=txn:54982` (Lutrinae), with `immpar_no` omitted. The [classification opinion](https://paleobiodb.org/data1.2/taxa/opinions.json?taxon_id=txn:41115&op_type=class&show=basis,ref,crmod&vocab=pbdb&extids=yes&strict=yes&limit=5) was `opn:923315`, status `belongs to`, parent `txn:54982`, reference `ref:84724`. The taxon authority reference was separately `ref:4783`; these references serve different provenance roles.

2. The documentation's [current-variant example `txn:285777`](https://paleobiodb.org/data1.2/taxa/list.json?taxon_id=txn:285777&rel=exact&show=immparent,attr,ref,crmod&vocab=pbdb&extids=yes&limit=5) returned **Dascillus**, `orig_no=txn:71894`, `taxon_no=var:71894`, together with warning `Unknown taxon '285777'`. The [exact-variant selector `var:285777`](https://paleobiodb.org/data1.2/taxa/list.json?taxon_id=var:285777&rel=exact&show=immparent,attr,ref,crmod&vocab=pbdb&extids=yes&limit=5) returned **Dascyllus**, `orig_no=txn:71894`, `taxon_no=var:285777`, `difference=misspelling of`. The warning is consistent with the source's numeric returned-ID check. [Official warning generation](https://github.com/paleobiodb/data_service/blob/2401eafe079202cc4ac5607c64216f192556f451/lib/PB2/TaxonData.pm#L3111)

3. **Inference for current `acquire.py`:** `strict=yes` can turn that usable current-variant resolution into a rejected batch. Its alias rule constructs a requested alias from the returned variant's numeric suffix, which cannot represent the mapping `txn:285777 -> txn:71894 / var:71894`. The retained `orig_no == rejected_selector` fallback also cannot recover this particular example. Any repair should archive the original typed request and returned mapping/warnings explicitly, validate all returned rows, and retain diagnostics; it should never resolve this by blindly replacing `txn:` with `var:`. No implementation or database changes were made for this research note.
