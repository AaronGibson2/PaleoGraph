"""Walk retained PBDB parent identities; ranks and names never infer an edge."""

import hashlib
import json
from typing import Any
from uuid import UUID

from app.taxonomy.policy import QUALIFIED, Classification, Term, normalized, pbdb_classification


def provider_id(value: Any) -> str | None:
    if isinstance(value, str) and value.startswith(("txn:", "var:")) and value[4:].isdigit():
        return value if int(value[4:]) > 0 else None
    return None


def actual_parent(row: dict[str, Any]) -> str | None:
    return provider_id(row.get("immpar_no")) or provider_id(row.get("parent_no"))


def parent_path(
    selector: str, records: dict[str, dict[str, Any]]
) -> tuple[tuple[Term, ...], bool, str | None]:
    terms: list[Term] = []
    seen: set[str] = set()
    current: str | None = selector
    reason = None
    complete = False
    while current:
        if current in seen or len(seen) >= 512:
            reason = f"circular parent {current}" if current in seen else "parent depth bound"
            break
        seen.add(current)
        row = records.get(current)
        if row is None:
            reason = f"missing parent {current}"
            break
        concept = provider_id(row.get("orig_no")) or current
        terms.append(Term(row["taxon_name"], row.get("taxon_rank"), concept, provenance=row))
        current = actual_parent(row)
        if current is None:
            complete = str(row.get("parent_no")) in {"0", "txn:0"} or bool(
                row.get("terminal_boundary")
            )
            if not complete:
                reason = "parent not supplied"
    return tuple(reversed(terms)), complete, reason


def classification_from_graph(
    taxon_id: UUID,
    name: str,
    rank: str | None,
    raw: dict[str, Any],
    records: dict[str, dict[str, Any]],
    snapshot: str,
) -> Classification:
    identified = provider_id(raw.get("identified_no"))
    accepted = provider_id(raw.get("accepted_no"))
    selector = identified if identified in records else accepted if accepted in records else None
    if selector is None:
        # Retained conventional fields are still source evidence when no graph exists.
        return pbdb_classification(taxon_id, name, rank, raw)
    terms, complete, reason = parent_path(selector, records)
    provenance: dict[str, Any] = {
        **records[selector],
        "snapshot_hash": snapshot,
        "identified_no": identified,
        "occurrence_accepted_no": accepted,
        "identification_name": name,
        "path_complete": complete,
        "partial_reason": reason,
    }
    qualification = tuple(
        str(raw[k])
        for k in ("genus_reso", "species_reso", "identification_qualifier")
        if raw.get(k)
    )
    if QUALIFIED.search(name):
        qualification += ("qualified source name",)
    implicit_identified = (
        not raw.get("identified_no")
        and selector == accepted
        and isinstance(raw.get("accepted_name"), str)
        and normalized(name) == normalized(raw["accepted_name"])
        and rank == raw.get("accepted_rank")
        and not qualification
        and not raw.get("difference")
    )
    if implicit_identified:
        # PBDB's structured serializer deduplicates identified_no against
        # accepted_no even in pbdb vocabulary. An explicit accepted assignment,
        # equal unqualified name/rank and no difference witness this identity.
        provenance["identity_resolution"] = "identified_no deduplicated against accepted_no"
    if selector == identified or implicit_identified:
        # The variant/occurrence spelling remains visible under PBDB's own current
        # containment context. Recombination/synonym links remain separate evidence.
        leaf = Term(name, rank, terms[-1].concept, taxon_id, provenance=provenance)
        terms = terms[:-1] + (leaf,)
        placement = None if complete else "partial"
    else:
        # An accepted assignment is not proof that an unnumbered entered name is
        # a new taxon or taxonomic child. This final display edge is labeled context.
        provenance["relationship"] = "accepted identification context"
        key = hashlib.sha256(
            json.dumps([accepted, normalized(name), rank, qualification]).encode()
        ).hexdigest()
        terms += (Term(name, rank, "identification:" + key, taxon_id, False, provenance),)
        placement = "unresolved"
    return Classification(
        taxon_id, "pbdb", terms, qualification, rooted=complete, leaf_placement=placement
    )
