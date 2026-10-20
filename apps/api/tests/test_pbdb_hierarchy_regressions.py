"""The four reported Florida taxa retain their archived PBDB parent identities."""

import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from app.taxonomy.build import plan
from app.taxonomy.pbdb_hierarchy import classification_from_graph

SNAPSHOT = json.loads((Path(__file__).parent / "fixtures/pbdb_taxonomy_hierarchy.json").read_text())


def classification(case, occurrence="one"):
    return classification_from_graph(
        uuid5(NAMESPACE_URL, case["name"] + occurrence),
        case["name"],
        case["rank"],
        case["raw"],
        SNAPSHOT["records"],
        SNAPSHOT["snapshot_hash"],
    )


@pytest.mark.parametrize("case", SNAPSHOT["cases"], ids=lambda case: case["name"])
def test_reported_species_keep_complete_source_context_and_reversible_identity(case):
    value = classification(case)
    assert value.rooted
    assert [term.name for term in value.terms] == case["expected_path"]
    assert value.leaf_placement == case["expected_placement"]
    nodes, concepts, leaves = plan([value])
    leaf = nodes[leaves[value.taxon_id]]
    assert leaf["parent_id"] is not None
    assert len(leaf["path"]) > 3
    assert [node["name"] for node in nodes.values() if node["parent_id"] is None] == ["Life"]
    source = next(concept for concept in concepts if concept["taxon_id"] == value.taxon_id)
    provenance = source["details"]["hierarchy"]
    assert provenance["snapshot_hash"] == SNAPSHOT["snapshot_hash"]
    assert provenance["proof"]["row_hash"]
    assert provenance["occurrence_accepted_no"] == case["raw"]["accepted_no"]
    if case["name"] == "Bufo woodhousei fowleri":
        assert value.terms[-2].name == "Bufo woodhousei"
        assert value.terms[-1].concept.startswith("identification:")
        assert provenance["relationship"] == "accepted identification context"
        assert value.leaf_placement == "unresolved"
    if case["name"] in {"Lutra canadensis", "Velates floridanus"}:
        assert provenance["accepted_name"] != case["name"]
        assert provenance["difference"] in {"recombined as", "subjective synonym of"}


def test_real_shared_ancestors_deduplicate_and_roots_do_not_scale_with_occurrences():
    cases = SNAPSHOT["cases"]
    small = [classification(case) for case in cases]
    many = [classification(case, str(index)) for case in cases for index in range(50)]
    small_nodes, _, _ = plan(small)
    nodes, concepts, leaves = plan(many)
    assert len(nodes) == len(small_nodes)
    roots = [node for node in nodes.values() if node["parent_id"] is None]
    assert len(roots) == 1 and roots[0]["name"] == "Life"
    assert len(set(leaves.values())) == len(cases)
    assert len({(c["node_id"], c["source"], c["concept_key"]) for c in concepts}) == len(concepts)
    assert plan(many) == plan(list(reversed(many)))
    for key, node in nodes.items():
        parent = node["parent_id"]
        assert parent is None or parent in nodes
        assert parent != key


def test_missing_source_parent_remains_partial_instead_of_a_species_root():
    case = SNAPSHOT["cases"][0]
    records = dict(SNAPSHOT["records"])
    # Keep the supplied leaf and remove its parent proof, reproducing an incomplete archive.
    leaf = records[case["raw"]["identified_no"]]
    records.pop(leaf.get("immpar_no") or leaf["parent_no"])
    value = classification_from_graph(
        uuid5(NAMESPACE_URL, "incomplete-real-florida"),
        case["name"],
        case["rank"],
        case["raw"],
        records,
        SNAPSHOT["snapshot_hash"],
    )
    assert not value.rooted and value.leaf_placement == "partial"
    nodes, _, leaves = plan([value])
    assert nodes[leaves[value.taxon_id]]["parent_id"] is not None
    assert [node["name"] for node in nodes.values() if node["parent_id"] is None] == [
        "Partial classification"
    ]
