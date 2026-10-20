"""PBDB parent graphs, provider variants and occurrence identities stay distinct."""

from uuid import NAMESPACE_URL, uuid5

from app.taxonomy.build import plan
from app.taxonomy.pbdb_hierarchy import classification_from_graph, parent_path


def graph():
    return {
        "txn:1": {
            "orig_no": "txn:1",
            "taxon_no": "var:1",
            "taxon_name": "Life",
            "taxon_rank": "unranked clade",
            "parent_no": "0",
        },
        "txn:2": {
            "orig_no": "txn:2",
            "taxon_no": "var:2",
            "taxon_name": "Animalia",
            "taxon_rank": "kingdom",
            "parent_no": "txn:1",
        },
        "txn:3": {
            "orig_no": "txn:3",
            "taxon_no": "var:3",
            "taxon_name": "Mustelidae",
            "taxon_rank": "family",
            "parent_no": "txn:2",
        },
        "txn:4": {
            "orig_no": "txn:4",
            "taxon_no": "var:4",
            "taxon_name": "Lontra",
            "taxon_rank": "genus",
            "parent_no": "txn:3",
        },
        "txn:5": {
            "orig_no": "txn:5",
            "taxon_no": "var:5",
            "taxon_name": "Lontra canadensis",
            "taxon_rank": "species",
            "parent_no": "txn:4",
            "accepted_no": "txn:5",
        },
        "var:6": {
            "orig_no": "txn:5",
            "taxon_no": "var:6",
            "taxon_name": "Lutra canadensis",
            "taxon_rank": "species",
            "parent_no": "txn:4",
            "accepted_no": "txn:5",
            "accepted_name": "Lontra canadensis",
            "difference": "recombined as",
        },
    }


def test_recombined_identification_keeps_name_and_supported_parents():
    value = classification_from_graph(
        uuid5(NAMESPACE_URL, "occ1"),
        "Lutra canadensis",
        "species",
        {"identified_no": "var:6", "accepted_no": "txn:5"},
        graph(),
        "snapshot",
    )
    assert [t.name for t in value.terms] == [
        "Life",
        "Animalia",
        "Mustelidae",
        "Lontra",
        "Lutra canadensis",
    ]
    nodes, concepts, leaves = plan([value])
    assert nodes[leaves[value.taxon_id]]["parent_id"] is not None
    assert len(nodes) == 5
    assert concepts[-1]["details"]["hierarchy"]["accepted_no"] == "txn:5"


def test_actual_parent_and_repeated_unranked_levels_are_preserved():
    records = graph()
    records["txn:4"]["immpar_no"] = "txn:7"
    records["txn:7"] = {
        "orig_no": "txn:7",
        "taxon_name": "Intermediate clade",
        "taxon_rank": "unranked clade",
        "parent_no": "txn:3",
    }
    terms, complete, reason = parent_path("txn:5", records)
    assert complete and reason is None
    assert [t.name for t in terms][-3:] == ["Intermediate clade", "Lontra", "Lontra canadensis"]


def test_missing_parent_and_cycles_are_explicit():
    records = graph()
    del records["txn:3"]
    assert parent_path("txn:5", records)[1:] == (False, "missing parent txn:3")
    records = graph()
    records["txn:3"]["parent_no"] = "txn:5"
    assert parent_path("txn:5", records)[1:] == (False, "circular parent txn:5")


def test_no_identified_id_uses_explicit_accepted_context_without_inventing_identity():
    value = classification_from_graph(
        uuid5(NAMESPACE_URL, "unknown"),
        "Verbatim subspecies",
        "subspecies",
        {"accepted_no": "txn:5"},
        graph(),
        "snapshot",
    )
    assert value.terms[-2].concept == "txn:5"
    assert value.terms[-1].concept.startswith("identification:")
    assert value.terms[-1].provenance["relationship"] == "accepted identification context"
    assert value.leaf_placement == "unresolved"


def test_shared_parent_deduplication_and_deterministic_plan():
    a = classification_from_graph(
        uuid5(NAMESPACE_URL, "a"),
        "Lutra canadensis",
        "species",
        {"identified_no": "var:6"},
        graph(),
        "snapshot",
    )
    b = classification_from_graph(
        uuid5(NAMESPACE_URL, "b"),
        "Lutra canadensis",
        "species",
        {"identified_no": "var:6"},
        graph(),
        "snapshot",
    )
    assert plan([a, b]) == plan([b, a])
    nodes, concepts, leaves = plan([a, b])
    assert len(nodes) == 5 and len(set(leaves.values())) == 1
    assert len({(c["node_id"], c["source"], c["concept_key"]) for c in concepts}) == len(concepts)


def test_provider_deduplicated_identified_id_keeps_supported_accepted_identity():
    value = classification_from_graph(
        uuid5(NAMESPACE_URL, "deduplicated-id"),
        "Lontra canadensis",
        "species",
        {"accepted_no": "txn:5", "accepted_name": "Lontra canadensis", "accepted_rank": "species"},
        graph(),
        "snapshot",
    )
    assert value.leaf_placement is None and value.rooted
    assert value.terms[-1].concept == "txn:5"
    assert value.terms[-1].provenance["identified_no"] is None
    assert value.terms[-1].provenance["identity_resolution"]


def test_unentered_or_qualified_name_does_not_inherit_deduplicated_identity():
    value = classification_from_graph(
        uuid5(NAMESPACE_URL, "unentered-id"),
        "Lontra canadensis",
        "subspecies",
        {"accepted_no": "txn:5", "accepted_name": "Lontra canadensis", "accepted_rank": "species"},
        graph(),
        "snapshot",
    )
    assert value.leaf_placement == "unresolved"
    assert value.terms[-1].concept.startswith("identification:")
