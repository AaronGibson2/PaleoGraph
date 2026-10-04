"""Association and source-classification contracts, against disposable PostGIS only."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from test_ufvp import fixture_rows, make_archive

from app.discovery.associations import fauna, lineage, localities, locality_summary
from app.discovery.queries import catalog
from app.discovery.schemas import ContextQuery
from app.ingestion.import_ufvp import ingest


@pytest.fixture
def material(db_session: Session, tmp_path: Path) -> Session:
    run = ingest(db_session, make_archive(tmp_path, fixture_rows()), raw_dir=tmp_path / "retained")
    assert run.status == "completed"
    return db_session


@pytest.mark.integration
def test_locality_counts_and_associations_are_conjunctive(material: Session) -> None:
    first = catalog(material, ContextQuery()).items[0]
    assert first.locality_id
    query = ContextQuery(locality_id=first.locality_id)
    summary = locality_summary(material, first.locality_id, ContextQuery())
    assertions = catalog(material, query)
    assert summary.assertion_count == assertions.total
    assert summary.specimen_count == len({item.specimen_id for item in assertions.items})
    assert summary.source_taxon_count == len({item.taxon_id for item in assertions.items})
    assert fauna(material, query).total == summary.source_taxon_count
    assert len(localities(material, query).items) == 1
    assert (
        locality_summary(
            material, first.locality_id, ContextQuery(older_ma=4000, younger_ma=3000)
        ).assertion_count
        == 0
    )


@pytest.mark.integration
def test_lineage_spans_describe_material_and_source_membership(material: Session) -> None:
    roots = lineage(material, ContextQuery())
    assert roots.items
    assert roots.relationship == "source-classification membership; not ancestry"
    node = roots.items[0]
    assert node.assertion_count > 0
    assert node.known_age_count + node.unknown_age_count == node.assertion_count
    if node.older_ma is not None:
        assert node.older_ma >= node.younger_ma
    children = lineage(material, ContextQuery(), node.id)
    assert all(child.parent_id == node.id for child in children.items)
    if children.items:
        assert children.items[0].assertion_count <= node.assertion_count


@pytest.mark.integration
def test_association_pagination_rejects_changed_context(material: Session) -> None:
    from fastapi import HTTPException

    query = ContextQuery(limit=1)
    page = localities(material, query)
    assert page.next_cursor
    next_page = localities(material, query.model_copy(update={"cursor": page.next_cursor}))
    assert page.items[0].id != next_page.items[0].id
    with pytest.raises(HTTPException, match="stale"):
        localities(
            material, ContextQuery(limit=1, cursor=page.next_cursor, older_ma=2, younger_ma=0)
        )


@pytest.mark.integration
def test_lineage_counts_distinct_specimens_across_source_identifications(material: Session) -> None:
    from sqlalchemy import text

    items = catalog(material, ContextQuery()).items
    different = next(item for item in items if item.taxon_id != items[0].taxon_id)
    material.execute(
        text("UPDATE catalog_entry SET specimen_id=:specimen WHERE occurrence_id=:id"),
        {"specimen": items[0].specimen_id, "id": different.id},
    )
    root = lineage(material, ContextQuery()).items[0]
    assert root.assertion_count == 8
    assert root.specimen_count == 7


@pytest.mark.integration
def test_safe_coordinates_and_colocated_distinct_sites(material: Session) -> None:
    from sqlalchemy import text

    sites = localities(material, ContextQuery(limit=100)).items
    first, second = sites[:2]
    material.execute(
        text(
            "UPDATE locality SET geom=(SELECT geom FROM locality WHERE id=:a), "
            "location_is_generalized=true WHERE id=:b"
        ),
        {"a": first.id, "b": second.id},
    )
    assert localities(material, ContextQuery()).total == 8
    summary = locality_summary(material, second.id, ContextQuery())
    assert summary.properties["location_is_generalized"]
    material.execute(
        text("UPDATE locality SET location_is_withheld=true,geom=NULL WHERE id=:id"),
        {"id": second.id},
    )
    summary = locality_summary(material, second.id, ContextQuery())
    assert summary.properties["longitude"] is None and summary.properties["latitude"] is None
    assert "description" not in summary.properties
    assert "county" not in summary.properties["geography"]


@pytest.mark.integration
def test_missing_ranks_qualifiers_unknown_ages_and_source_revision(
    db_session: Session, tmp_path: Path
) -> None:
    from sqlalchemy import text

    from app.ingestion.ufvp import stable_id

    raw = {
        **fixture_rows()[0],
        "phylum": "",
        "order": "",
        "scientificName": "Smilodon fatalis",
        "identificationQualifier": "cf.",
        "earliestEpochOrLowestSeries": "Miocene, perhaps",
        "earliestPeriodOrLowestSystem": "",
    }
    ingest(db_session, make_archive(tmp_path, [raw]), raw_dir=tmp_path / "retained")
    identified = catalog(db_session, ContextQuery()).items[0]
    page = lineage(db_session, ContextQuery(), identified.taxon_id)
    assert page.focal and page.focal.label == "Smilodon fatalis (cf.)"
    assert [item.subtitle for item in page.breadcrumbs] == [
        "kingdom",
        "class",
        "family",
        "genus",
        "species",
    ]
    assert page.focal.older_ma is None and page.focal.unknown_age_count == 1
    assert lineage(db_session, ContextQuery(older_ma=12, younger_ma=0)).total == 0
    db_session.execute(
        text("UPDATE source_record SET is_current=false WHERE id=:id"),
        {"id": stable_id("record", raw["id"])},
    )
    assert localities(db_session, ContextQuery()).total == 0
    assert lineage(db_session, ContextQuery()).total == 0


@pytest.mark.integration
def test_association_http_contracts_and_validation(material: Session) -> None:
    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import app

    first = catalog(material, ContextQuery()).items[0]
    app.dependency_overrides[get_session] = lambda: material
    try:
        with TestClient(app) as client:
            for path in [
                "localities",
                f"localities/{first.locality_id}",
                f"localities/{first.locality_id}/taxa",
                f"localities/{first.locality_id}/specimens",
                f"taxa/{first.taxon_id}/localities",
                "lineage",
            ]:
                response = client.get(f"/api/v1/{path}")
                assert response.status_code == 200, (path, response.text)
            assert client.get("/api/v1/lineage?focus=not-a-uuid").status_code == 422
            assert client.get("/api/v1/localities?order=unknown").status_code == 422
            assert client.get("/api/v1/localities?older_ma=1").status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_bounded_lineage_pages_and_changed_focus_cursor(material: Session) -> None:
    from fastapi import HTTPException

    kingdom = lineage(material, ContextQuery()).items[0]
    phylum = lineage(material, ContextQuery(), kingdom.id).items[0]
    clade = lineage(material, ContextQuery(), phylum.id).items[0]
    first = lineage(material, ContextQuery(limit=1), clade.id)
    assert first.total == 3 and first.next_cursor
    second = lineage(material, ContextQuery(limit=1, cursor=first.next_cursor), clade.id)
    assert first.items[0].id != second.items[0].id
    with pytest.raises(HTTPException, match="stale"):
        lineage(material, ContextQuery(limit=1, cursor=first.next_cursor), phylum.id)
