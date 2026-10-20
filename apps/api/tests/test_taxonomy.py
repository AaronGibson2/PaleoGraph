"""Taxonomy is a reversible browse projection, tested through placement and reads."""

from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ufvp import fixture_rows, make_archive

from app.ingestion.import_ufvp import ingest
from app.taxonomy.build import plan, rebuild
from app.taxonomy.policy import Classification, Term, complete_prefix, pbdb_classification
from app.taxonomy.queries import detail, listing
from app.taxonomy.schemas import TaxonomyQuery


def identifier(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, value)


def classification(
    source: str, values: list[tuple[str, str | None]], key: str = "leaf", **kwargs
) -> Classification:
    return Classification(
        identifier(source + key),
        source,
        tuple(Term(name, rank, source + name) for name, rank in values),
        **kwargs,
    )


BASE = [("Animalia", "kingdom"), ("Chordata", "phylum"), ("Mammalia", "class")]


def test_matching_path_unifies_browse_only_and_is_reversible() -> None:
    a = classification("ufvp", BASE + [("Canis", "genus")])
    b = classification("pbdb", BASE + [("Canis", "genus")])
    nodes, concepts, leaves = plan([a, b])
    assert leaves[a.taxon_id] == leaves[b.taxon_id]
    assert len([c for c in concepts if c["node_id"] == leaves[a.taxon_id]]) == 2
    assert a.taxon_id != b.taxon_id
    assert nodes[leaves[a.taxon_id]]["name"] == "Canis"


@pytest.mark.parametrize(
    "difference", ["parent", "rank", "qualifier", "unknown-rank", "accepted-conflict"]
)
def test_incompatible_equal_labels_remain_distinct(difference: str) -> None:
    a = classification("ufvp", BASE + [("Canis", "genus")])
    values = BASE + [("Canis", "genus")]
    kwargs = {}
    if difference == "parent":
        values = BASE + [("Felidae", "family"), ("Canis", "genus")]
    if difference == "rank":
        values = BASE + [("Canis", "family")]
    if difference == "unknown-rank":
        values = BASE + [("Canis", None)]
    if difference == "qualifier":
        kwargs["qualifiers"] = ("cf.",)
    if difference == "accepted-conflict":
        kwargs["conflict"] = True
    b = classification("pbdb", values, **kwargs)
    _, _, leaves = plan([a, b])
    assert leaves[a.taxon_id] != leaves[b.taxon_id]


def test_two_anchors_allow_only_unique_supported_upper_placement() -> None:
    full = classification("ufvp", BASE + [("Canidae", "family")])
    partial = classification("pbdb", BASE[1:] + [("Canidae", "family")])
    _, concepts, leaves = plan([full, partial])
    assert leaves[full.taxon_id] == leaves[partial.taxon_id]
    assert any(c["source"] == "pbdb" and c["details"]["upper_path_placement"] for c in concepts)
    one = (Term("Mammalia", "class", "one"),)
    assert complete_prefix(one, [full.terms]) == (one, False)


def test_ambiguous_upper_context_does_not_complete_partial_path() -> None:
    a = classification("ufvp", BASE)
    b = classification("ufvp", [("Other kingdom", "kingdom")] + BASE[1:], "other")
    partial = classification("pbdb", BASE[1:])
    nodes, _, leaves = plan([a, b, partial])
    assert nodes[leaves[partial.taxon_id]]["path"][0]["name"] == "Chordata"
    assert any(n["name"] == "Partial classification" for n in nodes.values())


def test_missing_ranks_are_not_fabricated() -> None:
    source = classification("ufvp", [BASE[0], BASE[2], ("Canidae", "family")])
    nodes, _, leaves = plan([source])
    assert [x["name"] for x in nodes[leaves[source.taxon_id]]["path"]] == [
        "Animalia",
        "Mammalia",
        "Canidae",
    ]


def test_rebuild_input_order_has_no_effect_and_shared_nodes_do_not_duplicate() -> None:
    values = [classification("ufvp", BASE), classification("pbdb", BASE)]
    assert plan(values) == plan(list(reversed(values)))
    nodes, concepts, _ = plan(values)
    assert len(nodes) == 3
    assert len({(c["node_id"], c["source"], c["concept_key"]) for c in concepts}) == len(concepts)


def test_same_provider_distinct_canonical_identifiers_do_not_collapse() -> None:
    a = Classification(
        identifier("a"),
        "pbdb",
        (Term("Animalia", "kingdom", "txn:1"), Term("Canis", "genus", "txn:2")),
    )
    b = Classification(
        identifier("b"),
        "pbdb",
        (Term("Animalia", "kingdom", "txn:1"), Term("Canis", "genus", "txn:3")),
    )
    nodes, _, leaves = plan([a, b])
    assert leaves[a.taxon_id] != leaves[b.taxon_id]
    assert nodes[leaves[a.taxon_id]]["placement"] == "ambiguous"


@pytest.mark.parametrize("rank", ["subfamily", "subgenus", "subspecies", "unranked clade"])
def test_additional_explicit_ranks_survive(rank: str) -> None:
    value = pbdb_classification(
        identifier(rank),
        "Source name",
        rank,
        {
            "phylum": "Chordata",
            "class": "Mammalia",
            "accepted_name": "Source name",
            "accepted_no": "txn:42",
        },
    )
    assert value.terms[-1].rank == rank
    assert plan([value])[0][plan([value])[2][value.taxon_id]]["rank"] == rank


@pytest.fixture
def florida(db_session: Session, tmp_path: Path) -> Session:
    run = ingest(db_session, make_archive(tmp_path, fixture_rows()), raw_dir=tmp_path / "retained")
    assert run.status == "completed", run.error_summary
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.pbdb import Snapshot

    ingest_snapshot(db_session, Snapshot.load(Path(__file__).parent / "fixtures/pbdb"))
    return db_session


@pytest.mark.integration
def test_roots_source_counts_and_evidence_types(florida: Session) -> None:
    roots = listing(florida, TaxonomyQuery())
    ufvp = listing(florida, TaxonomyQuery(source="ufvp"))
    pbdb = listing(florida, TaxonomyQuery(source="pbdb"))
    assert sum(n.counts.evidence_count for n in roots.items) == florida.scalar(
        text("SELECT count(*) FROM taxonomy_browse_member")
    )
    assert sum(n.counts.ufvp_material_count for n in roots.items) == 8
    assert all(n.counts.pbdb_occurrence_count == 0 for n in ufvp.items)
    assert all(n.counts.ufvp_material_count == 0 for n in pbdb.items)
    assert any(len(n.sources) == 2 for n in roots.items)


@pytest.mark.integration
def test_children_ancestors_search_and_legacy_source_urls(florida: Session) -> None:
    root = next(n for n in listing(florida, TaxonomyQuery()).items if n.name == "Animalia")
    children = listing(florida, TaxonomyQuery(), parent=root.id)
    assert children.items and all(c.parent_id == root.id for c in children.items)
    found = listing(florida, TaxonomyQuery(q="Smilodon"), search=True)
    assert found.items
    selected = detail(florida, found.items[0].id, TaxonomyQuery())
    assert selected.ancestors
    concept = next(c for c in selected.concepts if c.taxon_id is not None)
    assert detail(florida, concept.taxon_id, TaxonomyQuery()).node.id == selected.node.id


@pytest.mark.integration
def test_search_prioritizes_exact_names_then_prefixes_before_substrings(florida: Session) -> None:
    matches = listing(florida, TaxonomyQuery(q="Smilodon"), search=True)
    template = next(node for node in matches.items if node.name == "Smilodon")
    # Only disposable browse rows are added; source assertions remain unchanged.
    for name in ["Rhizosmilodon", "Smilodon synthetic"]:
        florida.execute(
            text("""INSERT INTO taxonomy_browse_node
                (id,scope,parent_id,name,rank,search_name,placement,path,
                 ufvp_count,pbdb_count,summary)
                SELECT :id,scope,parent_id,:name,rank,:search,placement,path,
                    ufvp_count,pbdb_count,summary FROM taxonomy_browse_node WHERE id=:template"""),
            {
                "id": identifier(name),
                "name": name,
                "search": name.casefold(),
                "template": template.id,
            },
        )
    results = listing(florida, TaxonomyQuery(q=" SMILODON "), search=True)
    names = [node.name for node in results.items]
    assert names[0] == "Smilodon"
    assert names.index("Smilodon synthetic") < names.index("Rhizosmilodon")


@pytest.mark.integration
def test_direct_and_inclusive_counts_partition_evidence(florida: Session) -> None:
    nodes = (
        florida.execute(text("SELECT id FROM taxonomy_browse_node WHERE ufvp_count+pbdb_count>0"))
        .scalars()
        .all()
    )
    for identifier in nodes:
        selected = detail(florida, identifier, TaxonomyQuery()).node
        children = listing(florida, TaxonomyQuery(limit=100), parent=identifier)
        assert selected.counts.evidence_count == selected.counts.direct_count + sum(
            c.counts.evidence_count for c in children.items
        )
        assert (
            selected.counts.known_age_count + selected.counts.unknown_age_count
            == selected.counts.evidence_count
        )


@pytest.mark.integration
def test_projection_rebuild_is_deterministic_and_changes_no_existing_rows(florida: Session) -> None:
    names = (
        florida.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename NOT LIKE 'taxonomy_browse_%'"
            )
        )
        .scalars()
        .all()
    )

    def fingerprint(table: str):
        assert table.replace("_", "").isalnum()
        return florida.scalar(
            text(
                "SELECT md5(coalesce(string_agg(h,'' ORDER BY h),'')) "
                f"FROM (SELECT md5(to_jsonb(t)::text) h FROM {table} t) hashes"
            )
        )

    before = {name: fingerprint(name) for name in names}
    first = rebuild(florida)
    projected = {
        name: fingerprint(name)
        for name in (
            "taxonomy_browse_node",
            "taxonomy_browse_concept",
            "taxonomy_browse_member",
            "taxonomy_browse_path",
        )
    }
    second = rebuild(florida)
    assert first["input_hash"] == second["input_hash"]
    assert before == {name: fingerprint(name) for name in names}
    assert projected == {name: fingerprint(name) for name in projected}


@pytest.mark.integration
def test_pagination_filters_empty_context_and_dirty_snapshot(florida: Session) -> None:
    query = TaxonomyQuery(q="a", limit=1)
    first = listing(florida, query, search=True)
    assert first.next_offset == 1
    second = listing(florida, query.model_copy(update={"offset": 1}), search=True)
    assert first.items[0].id != second.items[0].id
    assert listing(florida, TaxonomyQuery(older_ma=4000, younger_ma=3000)).total == 0
    florida.execute(text("UPDATE browse_projection_state SET input_revision=input_revision+1"))
    with pytest.raises(HTTPException) as error:
        listing(florida, TaxonomyQuery())
    assert error.value.status_code == 503


def test_ambiguous_parent_identity_remains_distinct_in_descendant_paths() -> None:
    first = Classification(
        identifier("first"),
        "pbdb",
        (
            Term("Animalia", "kingdom", "txn:1"),
            Term("Same family", "family", "txn:2"),
            Term("Same genus", "genus", "txn:4"),
        ),
    )
    second = Classification(
        identifier("second"),
        "pbdb",
        (
            Term("Animalia", "kingdom", "txn:1"),
            Term("Same family", "family", "txn:3"),
            Term("Same genus", "genus", "txn:4"),
        ),
    )
    nodes, _, leaves = plan([first, second])
    assert leaves[first.taxon_id] != leaves[second.taxon_id]
    assert nodes[leaves[first.taxon_id]]["parent_id"] != nodes[leaves[second.taxon_id]]["parent_id"]
    assert plan([first, second]) == plan([second, first])


@pytest.mark.integration
def test_ancestor_and_concept_pages_preserve_complete_traceability(florida: Session) -> None:
    from app.taxonomy.queries import ancestor_page, concept_page

    found = listing(florida, TaxonomyQuery(q="Mammalia"), search=True).items[0]
    selected = detail(florida, found.id, TaxonomyQuery())
    assert ancestor_page(florida, found.id, TaxonomyQuery()).items == selected.ancestors
    first = concept_page(florida, found.id, TaxonomyQuery(limit=1))
    assert first.total == selected.concept_total
    assert first.items == selected.concepts[:1]
    if first.next_offset:
        second = concept_page(florida, found.id, TaxonomyQuery(limit=1, offset=1))
        assert second.items == selected.concepts[1:2]
        assert first.items[0].concept_key != second.items[0].concept_key


@pytest.mark.integration
def test_batched_ancestor_children_match_lazy_pages_and_preserve_source_age_filters(
    florida: Session,
) -> None:
    from app.taxonomy.queries import branch_children

    selected = listing(florida, TaxonomyQuery(q="Smilodon"), search=True).items[0]
    for query in [
        TaxonomyQuery(limit=1),
        TaxonomyQuery(source="pbdb", limit=1),
        TaxonomyQuery(older_ma=4000, younger_ma=3000, limit=1),
    ]:
        batch = branch_children(florida, selected.id, query)
        assert batch.next_offset is None
        assert len(batch.items) == len(detail(florida, selected.id, query).ancestors)
        for branch in batch.items:
            assert branch.page == listing(florida, query, parent=branch.parent_id)
            assert len(branch.page.items) <= query.limit


def test_equal_named_upper_paths_with_distinct_concepts_are_not_unique_support() -> None:
    first = (
        Term("Animalia", "kingdom", "one"),
        Term("Chordata", "phylum", "chordata"),
        Term("Mammalia", "class", "mammalia"),
    )
    second = (Term("Animalia", "kingdom", "other"),) + first[1:]
    assert complete_prefix(first[1:], [first, second]) == (first[1:], False)


def test_derived_assertion_uuids_group_by_compatible_path_without_merging_identity() -> None:
    first = Classification(
        identifier("uf-higher"),
        "ufvp",
        (
            Term("Animalia", "kingdom", "upper", canonical=False),
            Term("Mammalia", "class", "classification-hash", canonical=False),
        ),
    )
    second = Classification(
        identifier("uf-leaf"),
        "ufvp",
        (
            Term("Animalia", "kingdom", "upper", canonical=False),
            Term("Mammalia", "class", "identification-hash", canonical=False),
        ),
    )
    pbdb = classification("pbdb", [("Animalia", "kingdom"), ("Mammalia", "class")])
    nodes, concepts, leaves = plan([first, second, pbdb])
    assert len(set(leaves.values())) == 1
    assert nodes[leaves[first.taxon_id]]["placement"] == "supported"
    assert len([c for c in concepts if c["node_id"] == leaves[first.taxon_id]]) == 3


def test_an_unranked_leaf_does_not_label_its_supported_upper_nodes_unresolved() -> None:
    value = classification("ufvp", BASE + [("Unranked identification", None)])
    nodes, _, leaves = plan([value])
    leaf = nodes[leaves[value.taxon_id]]
    assert leaf["placement"] == "unresolved"
    assert nodes[leaf["parent_id"]]["placement"] == "supported"
