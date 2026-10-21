"""Different source path depth must not create parallel ordinary browse branches."""

from uuid import NAMESPACE_URL, uuid5

import pytest
from sqlalchemy import text

from app.taxonomy.build import plan
from app.taxonomy.policy import Classification, Term


def source(key, names):
    return Classification(
        uuid5(NAMESPACE_URL, key),
        key,
        tuple(Term(name, rank, key + name, canonical=key == "pbdb") for name, rank in names),
        rooted=True,
    )


def test_source_only_intermediate_clades_do_not_duplicate_mammals():
    ufvp = source(
        "ufvp",
        [
            ("Animalia", "kingdom"),
            ("Chordata", "phylum"),
            ("Mammalia", "class"),
            ("Canidae", "family"),
            ("Canis", "genus"),
        ],
    )
    pbdb = source(
        "pbdb",
        [
            ("Life", "unranked clade"),
            ("Animalia", "kingdom"),
            ("Bilateria", "unranked clade"),
            ("Chordata", "phylum"),
            ("Vertebrata", "subphylum"),
            ("Mammalia", "class"),
            ("Theria", "subclass"),
            ("Canidae", "family"),
            ("Canis", "genus"),
        ],
    )
    nodes, concepts, leaves = plan([ufvp, pbdb])
    assert leaves[ufvp.taxon_id] == leaves[pbdb.taxon_id]
    assert len([n for n in nodes.values() if n["name"] == "Mammalia"]) == 1
    assert {c["source"] for c in concepts if c["node_id"] == leaves[ufvp.taxon_id]} == {
        "ufvp",
        "pbdb",
    }
    assert plan([ufvp, pbdb]) == plan([pbdb, ufvp])
    assert not nodes[leaves[ufvp.taxon_id]]["summary"].get("source_disagreement_note")


def test_repeated_rank_containment_difference_is_visible_without_splitting_shared_groups():
    ufvp = source("ufvp", [("Animalia", "kingdom"), ("Chordata", "phylum"), ("Mammalia", "class")])
    fish = Classification(
        uuid5(NAMESPACE_URL, "fish"),
        "ufvp",
        ufvp.terms[:-1] + (Term("Osteichthyes", "class", "fish", canonical=False),),
        rooted=True,
    )
    pbdb = source(
        "pbdb",
        [
            ("Animalia", "kingdom"),
            ("Chordata", "phylum"),
            ("Osteichthyes", "class"),
            ("Mammalia", "class"),
        ],
    )
    nodes, _, leaves = plan([ufvp, fish, pbdb])
    assert leaves[ufvp.taxon_id] == leaves[pbdb.taxon_id]
    assert (
        "Source containment differs"
        in nodes[leaves[fish.taxon_id]]["summary"]["source_disagreement_note"]
    )


@pytest.mark.parametrize("extra", ["class", "unranked clade", "subclass"])
def test_explicit_outer_repeated_ranks_are_not_conflicting_inner_classes(extra):
    ufvp = source("ufvp", [("Animalia", "kingdom"), ("Reptilia", "class"), ("Crocodylia", "order")])
    pbdb = source(
        "pbdb",
        [
            ("Life", "unranked clade"),
            ("Animalia", "kingdom"),
            ("Outer source group", extra),
            ("Reptilia", "class"),
            ("Crocodylia", "unranked clade"),
        ],
    )
    _, concepts, leaves = plan([ufvp, pbdb])
    assert len(set(leaves.values())) == 1
    preserved = next(
        c for c in concepts if c["source"] == "pbdb" and c["details"]["name"] == "Crocodylia"
    )
    assert preserved["details"]["supplied_path"][2]["name"] == "Outer source group"
    assert preserved["details"]["browse_path_adjusted"]


def test_a_missing_family_can_join_but_conflicting_explicit_families_cannot():
    ufvp = source(
        "ufvp",
        [("Animalia", "kingdom"), ("Mammalia", "class"), ("Canidae", "family"), ("Canis", "genus")],
    )
    missing = source("pbdb", [("Animalia", "kingdom"), ("Mammalia", "class"), ("Canis", "genus")])
    assert len(set(plan([ufvp, missing])[2].values())) == 1
    conflict = source(
        "pbdb",
        [("Animalia", "kingdom"), ("Mammalia", "class"), ("Felidae", "family"), ("Canis", "genus")],
    )
    assert len(set(plan([ufvp, conflict])[2].values())) == 2


def test_unified_visual_membership_is_nearest_first_and_provider_scoped():
    ufvp = source("ufvp", [("Animalia", "kingdom"), ("Reptilia", "class"), ("Crocodylia", "order")])
    pbdb = Classification(
        uuid5(NAMESPACE_URL, "pbdb"),
        "pbdb",
        (
            Term("Animalia", "kingdom", "txn:1"),
            Term("Reptilia", "class", "txn:2"),
            Term("Crocodylia", "unranked clade", "txn:36582"),
        ),
        rooted=True,
    )
    nodes, _, leaves = plan([ufvp, pbdb])
    assert nodes[leaves[ufvp.taxon_id]]["summary"]["visual_ids_nearest"][0] == "pbdb:txn:36582"


def test_shared_family_bridges_a_different_order_with_an_explicit_disagreement_note():
    ufvp = source(
        "ufvp",
        [
            ("Animalia", "kingdom"),
            ("Aves", "class"),
            ("Pelecaniformes", "order"),
            ("Phalacrocoracidae", "family"),
            ("Phalacrocorax", "genus"),
        ],
    )
    pbdb = source(
        "pbdb",
        [
            ("Animalia", "kingdom"),
            ("Aves", "class"),
            ("Suliformes", "order"),
            ("Phalacrocoracidae", "family"),
            ("Phalacrocorax", "genus"),
        ],
    )
    nodes, concepts, leaves = plan([ufvp, pbdb])
    assert leaves[ufvp.taxon_id] == leaves[pbdb.taxon_id]
    assert (
        "different higher classifications"
        in nodes[leaves[ufvp.taxon_id]]["summary"]["source_disagreement_note"]
    )
    assert (
        len(
            {
                tuple(t["name"] for t in c["details"]["supplied_path"])
                for c in concepts
                if c["node_id"] == leaves[ufvp.taxon_id]
            }
        )
        == 2
    )


@pytest.mark.integration
def test_search_prefers_supported_shared_group_over_an_equal_unresolved_name(db_session, tmp_path):
    from uuid import UUID

    from test_taxonomy import fixture_rows, make_archive

    from app.ingestion.import_ufvp import ingest
    from app.taxonomy.queries import listing
    from app.taxonomy.schemas import TaxonomyQuery

    ingest(db_session, make_archive(tmp_path, fixture_rows()), raw_dir=tmp_path / "retained")
    query = TaxonomyQuery(q="Smilodon")
    node = next(n for n in listing(db_session, query, search=True).items if n.name == "Smilodon")
    db_session.execute(
        text("""INSERT INTO taxonomy_browse_node
        (id,scope,parent_id,name,rank,search_name,placement,path,ufvp_count,pbdb_count,summary)
        SELECT :id,scope,parent_id,name,NULL,search_name,'unresolved',path,
        ufvp_count,pbdb_count,summary FROM taxonomy_browse_node WHERE id=:template"""),
        {"id": UUID(int=1), "template": node.id},
    )
    results = listing(db_session, query, search=True).items
    assert results[0].id == node.id
    assert any(n.id == UUID(int=1) for n in results)


@pytest.mark.integration
def test_old_browse_urls_resolve_after_merge_and_repeat_rebuild(db_session, tmp_path):
    from test_taxonomy import fixture_rows, make_archive

    from app.ingestion.import_ufvp import ingest
    from app.taxonomy.build import rebuild
    from app.taxonomy.queries import detail, listing
    from app.taxonomy.schemas import TaxonomyQuery

    ingest(db_session, make_archive(tmp_path, fixture_rows()), raw_dir=tmp_path / "retained")
    node = listing(db_session, TaxonomyQuery(q="Smilodon"), search=True).items[0]
    old = uuid5(NAMESPACE_URL, "old-browse-url")
    db_session.execute(
        text("INSERT INTO taxonomy_browse_alias(old_id,node_id) VALUES (:old,:node)"),
        {"old": old, "node": node.id},
    )
    for _ in range(2):
        rebuild(db_session)
        assert detail(db_session, old, TaxonomyQuery()).node.id == node.id
