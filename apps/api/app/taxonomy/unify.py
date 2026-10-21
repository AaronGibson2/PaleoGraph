"""Compact, reversible display alignment; never changes a provider classification.

UFVP's ranked directory is the compact spine. A PBDB node can join it only at
one compatible name/rank/context. Extra provider levels are retained in concept
proofs. Conflicting ranked ancestors, canonical ambiguity and qualifiers isolate.
"""

from collections import defaultdict
from typing import Any
from uuid import UUID

from app.taxonomy.policy import normalized

CLADES = {"unranked clade", "clade"}


def rank_agrees(a: str | None, b: str | None) -> bool:
    return bool(
        a and b and (a == b or a in CLADES or b in CLADES or {a, b} == {"order", "suborder"})
    )


def compatible(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    """Every overlapping ranked context agrees, allowing explicitly nested clades.

    A missing rank is absence, not contradiction. Different named groups at the
    same rank may only bridge when that exact name also occurs as a source clade.
    A target needs a shared parent anchor, except an explicit kingdom boundary.
    """
    if not rank_agrees(a[-1]["rank"], b[-1]["rank"]):
        return False
    parents_a, parents_b = a[:-1], b[:-1]
    anchors = {
        normalized(x["name"])
        for x in parents_a
        for y in parents_b
        if normalized(x["name"]) == normalized(y["name"]) and rank_agrees(x["rank"], y["rank"])
    }
    if not anchors and a[-1]["rank"] != "kingdom":
        return False
    # Shared names must occur in the same order: never fold an ancestor into a child.
    order_a = list(
        dict.fromkeys(normalized(x["name"]) for x in parents_a if normalized(x["name"]) in anchors)
    )
    order_b = list(
        dict.fromkeys(normalized(x["name"]) for x in parents_b if normalized(x["name"]) in anchors)
    )
    if order_a != order_b:
        return False
    # A unique same-named family is an adequate anchor for its own grouping and
    # descendants even when providers place it in different orders. Family/genus
    # disagreement remains isolating, so this is not name-only homonym merging.
    families_a = {normalized(x["name"]) for x in a if x["rank"] == "family"}
    families_b = {normalized(x["name"]) for x in b if x["rank"] == "family"}
    shared_family = bool(families_a & families_b)
    class_anchor = any(x["rank"] == "class" and normalized(x["name"]) in anchors for x in parents_a)
    for left, right in ((parents_a, parents_b), (parents_b, parents_a)):
        # Providers can repeat a rank along an explicitly nested path. Compare
        # its nearest occurrence, not a remote outer class against an inner one.
        nearest = {x["rank"]: x for x in left if x["rank"] and x["rank"] not in CLADES}
        peers = {x["rank"]: x for x in right if x["rank"] and x["rank"] not in CLADES}
        for term in nearest.values():
            rank = term["rank"]
            if rank in peers and normalized(peers[rank]["name"]) != normalized(term["name"]):
                nested = any(
                    normalized(x["name"]) == normalized(term["name"]) for x in right
                ) or any(normalized(x["name"]) == normalized(peers[rank]["name"]) for x in left)
                if not nested:
                    if (
                        shared_family
                        and class_anchor
                        and rank
                        in {
                            "order",
                            "suborder",
                            "superorder",
                            "superfamily",
                            "subclass",
                            "infraclass",
                        }
                    ):
                        continue
                    return False
    return True


def unify(
    nodes: dict[UUID, dict[str, Any]], concepts: list[dict[str, Any]], leaves: dict[UUID, UUID]
) -> tuple[dict[UUID, dict[str, Any]], list[dict[str, Any]], dict[UUID, UUID]]:
    sources: dict[UUID, set[str]] = defaultdict(set)
    for concept in concepts:
        sources[concept["node_id"]].add(concept["source"])
    candidates: dict[str, list[UUID]] = defaultdict(list)
    for key, node in nodes.items():
        if "ufvp" in sources[key] and node["placement"] == "supported":
            candidates[normalized(node["name"])].append(key)
    redirect = {key: key for key in nodes}
    for key, node in nodes.items():
        if sources[key] != {"pbdb"} or node["placement"] not in {"supported", "partial"}:
            continue
        matches = [
            target
            for target in candidates[normalized(node["name"])]
            if compatible(nodes[target]["path"], node["path"])
        ]
        if len(matches) == 1:
            redirect[key] = matches[0]
            target_node = nodes[matches[0]]
            if (
                target_node["rank"] != node["rank"]
                and not {target_node["rank"], node["rank"]} & CLADES
            ):
                target_node["summary"]["source_disagreement_note"] = (
                    "Sources assign different ranks to this group. Both ranks are retained below."
                )
            for rank in ("order", "suborder"):
                left = next(
                    (x["name"] for x in reversed(target_node["path"][:-1]) if x["rank"] == rank),
                    None,
                )
                right = next(
                    (x["name"] for x in reversed(node["path"][:-1]) if x["rank"] == rank), None
                )
                if left and right and normalized(left) != normalized(right):
                    target_node["summary"]["source_disagreement_note"] = (
                        "Sources place this group in different higher classifications. "
                        "One browse grouping retains both complete source paths below."
                    )
        elif not matches and candidates[normalized(node["name"])]:
            note = (
                "Source ranks or containing groups differ; these browse placements remain separate."
            )
            node["summary"]["source_disagreement_note"] = note
            for target in candidates[normalized(node["name"])]:
                nodes[target]["summary"]["source_disagreement_note"] = note
    # A source-only ambiguous parent also isolates its descendants. Do not bypass it.
    for key in redirect:
        current = nodes[key]["parent_id"]
        while current is not None:
            if nodes[current]["placement"] in {"ambiguous", "qualified", "unresolved"}:
                redirect[key] = key
                break
            current = nodes[current]["parent_id"]
    result = {key: node for key, node in nodes.items() if redirect[key] == key}
    for key, target in redirect.items():
        if key == target:
            continue
        target_path = {UUID(term["id"]) for term in nodes[target]["path"]}
        for term in nodes[key]["path"][:-1]:
            ancestor = redirect[UUID(term["id"])]
            # Equal ranked groups explicitly nested by one provider but siblings
            # in the other have different scope, not just missing intermediate ranks.
            if (
                ancestor not in target_path
                and "ufvp" in sources[ancestor]
                and nodes[ancestor]["rank"] == nodes[target]["rank"]
            ):
                nodes[ancestor]["summary"]["source_disagreement_note"] = (
                    "Source containment differs. Counts follow this displayed browse tree; "
                    "complete original source classifications remain below."
                )
    # An explicit shared kingdom inherits its unique retained upper context so
    # Animalia is not a second root next to PBDB's Life/Eucarya branch.
    uppers: dict[UUID, set[UUID]] = defaultdict(set)
    for key, target in redirect.items():
        if key != target and nodes[target]["parent_id"] is None:
            parent = nodes[key]["parent_id"]
            if parent is not None:
                uppers[target].add(redirect[parent])
    for key, node in result.items():
        parent = node["parent_id"]
        node["parent_id"] = (
            redirect[parent]
            if parent
            else next(iter(uppers[key]))
            if len(uppers[key]) == 1
            else None
        )
    # Reconstruct displayed paths after reparenting; identifiers stay stable for
    # retained spine nodes. Removed node IDs are recorded as URL aliases at rebuild.
    paths: dict[UUID, list[dict[str, Any]]] = {}

    def path(key: UUID, seen: frozenset[UUID] = frozenset()) -> list[dict[str, Any]]:
        if key in seen:
            raise ValueError("Cyclic unified browse placement")
        if key not in paths:
            node = result[key]
            prefix = path(node["parent_id"], seen | {key}) if node["parent_id"] else []
            paths[key] = prefix + (
                [{"id": str(key), "name": node["name"], "rank": node["rank"]}]
                if node["placement"] != "container"
                else []
            )
        return paths[key]

    for key, node in result.items():
        node["path"] = path(key)
    for concept in concepts:
        old = concept["node_id"]
        concept["node_id"] = redirect[old]
        if old != redirect[old]:
            concept["details"]["browse_path_adjusted"] = True
            result[redirect[old]]["summary"]["unified"] = True
    unique = {(c["node_id"], c["source"], c["concept_key"]): c for c in concepts}
    own: dict[UUID, set[str]] = defaultdict(set)
    for concept in concepts:
        if concept["source"] == "pbdb":
            key = concept["concept_key"].split(":taxon:")[0]
            if key.startswith(("txn:", "var:")):
                own[concept["node_id"]].add("pbdb:" + key)
    # Visual membership is nearest-first, from retained source nodes and the
    # shared spine. It remains UUID-based, never guessed from a display label.
    for node in result.values():
        ids: list[str] = []
        for ancestor in reversed(node["path"]):
            ancestor_id = UUID(ancestor["id"])
            for value in [
                *sorted(own[ancestor_id]),
                *reversed(result[ancestor_id]["summary"].get("visual_ids", [])),
            ]:
                if value not in ids:
                    ids.append(value)
        node["summary"]["visual_ids_nearest"] = ids
    return result, list(unique.values()), {taxon: redirect[node] for taxon, node in leaves.items()}
