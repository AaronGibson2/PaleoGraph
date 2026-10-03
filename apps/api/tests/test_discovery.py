from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fixtures.synthetic import seed_demo
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from test_ufvp import fixture_rows, make_archive

from app.discovery.index import rebuild
from app.discovery.queries import catalog, detail, graph, places, search
from app.discovery.schemas import ContextQuery, PlaceQuery
from app.discovery.timescale import configuration, interpret, intervals
from app.ingestion.import_ufvp import ingest
from app.ingestion.ufvp import stable_id
from app.models import AgeInterpretation, CatalogEntry, CollectionEvent, SourceDataset, SourceRecord


@pytest.mark.parametrize(
    "label,older,younger",
    [
        ("Miocene, early", 23.04, 15.98),
        ("Miocene, middle", 15.98, 11.63),
        ("Miocene, late", 11.63, 5.333),
        ("Pliocene, early", 5.333, 3.6),
        ("Pliocene, late", 3.6, 2.58),
        ("Pleistocene, early", 2.58, 0.774),
        ("Pleistocene, middle", 0.774, 0.129),
        ("Pleistocene, late", 0.129, 0.0117),
        ("Holocene, middle", 0.0082, 0.0042),
        ("Miocene", 23.04, 5.333),
    ],
)
def test_exact_supported_source_mapping(label: str, older: float, younger: float) -> None:
    age = interpret({"earliestEpochOrLowestSeries": label})
    assert age["status"] == "mapped"
    assert age["older_ma"] == older and age["younger_ma"] == younger
    assert age["source_label"] == label


@pytest.mark.parametrize(
    "label",
    [
        "Miocene, early(?)",
        "Miocene or Pliocene",
        "Miocene-Pleistocene (mixed)",
        "Pleistocene, early or Pleistocene, late",
        "Middle Pliocene",
        "Hemphillian",
        "unrecognized",
        "Miocene/Plio",
        "Miocene, approx",
        "Miocene-LatePliocene",
    ],
)
def test_unresolved_fine_assertions_never_fall_back_to_period(label: str) -> None:
    result = interpret(
        {"earliestEpochOrLowestSeries": label, "earliestPeriodOrLowestSystem": "Neogene"}
    )
    assert result["status"] in {"ambiguous", "unmapped"}
    assert result["older_ma"] is None and result["interval_id"] is None


def test_biochronology_does_not_become_a_numerical_age() -> None:
    assert interpret({"lowestBiostratigraphicZone": "Blancan"})["status"] == "absent"
    assert interpret({"earliestPeriodOrLowestSystem": "Quaternary"})["status"] == "mapped"


def test_reference_hierarchy_and_corrected_bounds() -> None:
    units = intervals()
    assert len(units) == 186
    assert units["Aquitanian"]["older_ma"] == 23.04
    assert units["Aquitanian"]["older_boundary"]["rdf_ma"] == 23.03
    assert units["Ludlow"]["younger_ma"] == 422.7
    for unit in units.values():
        assert unit["older_ma"] >= unit["younger_ma"] >= 0
        seen = set()
        parent = unit["parent"]
        while parent:
            assert parent not in seen
            seen.add(parent)
            assert parent in units
            parent = units[parent]["parent"]
    config = configuration()
    assert config["kind"] != "demo_windows"
    assert config["license_url"].endswith("/by/4.0/")


@pytest.fixture
def indexed(db_session: Session, tmp_path: Path) -> Session:
    run = ingest(db_session, make_archive(tmp_path, fixture_rows()), raw_dir=tmp_path / "retained")
    assert run.status == "completed", run.error_summary
    return db_session


@pytest.mark.integration
def test_atomic_idempotent_projection_preserves_source_facts(indexed: Session) -> None:
    before = indexed.scalar(select(func.count()).select_from(AgeInterpretation))
    result = rebuild(indexed)
    assert result["records"] == 8 and result["derived_records"] > 0
    assert indexed.scalar(select(func.count()).select_from(AgeInterpretation)) == before == 8
    assert (
        indexed.scalar(
            select(func.count())
            .select_from(CollectionEvent)
            .where(CollectionEvent.older_ma.is_not(None))
        )
        == 0
    )
    assert indexed.scalar(select(func.count()).select_from(CatalogEntry)) == 8


@pytest.mark.integration
def test_failed_projection_does_not_deactivate_unseen_source_records(
    indexed: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed_rebuild(session: Session) -> None:
        raise RuntimeError("Intentional projection failure")

    monkeypatch.setattr("app.discovery.index.rebuild", failed_rebuild)
    folder = tmp_path / "failed-rebuild"
    folder.mkdir()
    run = ingest(
        indexed,
        make_archive(folder, fixture_rows()[:1]),
        limit=None,
        raw_dir=folder / "retained",
    )
    assert run.status == "failed" and "Intentional projection failure" in run.error_summary
    assert (
        indexed.scalar(
            select(func.count()).select_from(SourceRecord).where(SourceRecord.is_current)
        )
        == 8
    )
    assert catalog(indexed, ContextQuery()).total == 8


@pytest.mark.integration
def test_cursor_pages_totals_context_and_search_entities(indexed: Session) -> None:
    page = catalog(indexed, ContextQuery(limit=3))
    assert page.total == 8 and len(page.items) == 3 and page.next_cursor
    next_page = catalog(indexed, ContextQuery(limit=3, cursor=page.next_cursor))
    assert not {item.id for item in page.items} & {item.id for item in next_page.items}
    with pytest.raises(HTTPException):
        catalog(indexed, ContextQuery(limit=3, cursor=page.next_cursor, older_ma=2, younger_ma=0))
    rows = fixture_rows()
    result = search(indexed, ContextQuery(q=rows[0]["scientificName"], limit=100))
    assert any(item.kind == "taxon" for item in result.items)
    assert any(item.kind == "specimen" for item in result.items)
    assert result.items[0].label.casefold() == rows[0]["scientificName"].casefold()
    identified = detail(indexed, "specimen", stable_id("specimen", rows[0]["id"]), ContextQuery())
    assert identified.properties["status"] == "mapped"
    assert any(ref.kind == "locality" for ref in identified.related)
    assert any(ref.kind == "collection" for ref in identified.related)
    assert "No bibliographic references" in identified.research_note
    assert catalog(indexed, ContextQuery(older_ma=0.01, younger_ma=0)).total == 0


@pytest.mark.integration
def test_dense_coordinates_keep_localities_and_exhaustive_material(
    db_session: Session,
    tmp_path: Path,
) -> None:
    template = fixture_rows()[0]
    rows = [
        {
            **template,
            "id": f"TEST-ONLY-{i}",
            "catalogNumber": f"TEST-ONLY-{i}",
            "locationID": f"TEST-LOCALITY-{i % 5}",
            "locality": f"Test locality {i % 5}",
        }
        for i in range(73)
    ]
    run = ingest(db_session, make_archive(tmp_path, rows), raw_dir=tmp_path / "retained")
    assert run.status == "completed", run.error_summary
    points = places(db_session, PlaceQuery())
    assert points.total_records == 73 and points.total_places == 1
    assert points.items[0].record_count == 73 and points.items[0].locality_count == 5
    assert points.items[0].longitude == float(template["decimalLongitude"])
    collected = set()
    query = ContextQuery(
        limit=10, at_lon=points.items[0].longitude, at_lat=points.items[0].latitude
    )
    while True:
        page = catalog(db_session, query)
        assert page.total == 73
        assert not collected & {item.id for item in page.items}
        collected.update(item.id for item in page.items)
        if not page.next_cursor:
            break
        query.cursor = page.next_cursor
    assert len(collected) == 73


@pytest.mark.integration
def test_graph_bounded_progression_and_public_isolation(indexed: Session) -> None:
    page = catalog(indexed, ContextQuery(limit=1))
    root = page.items[0]
    neighborhood = graph(indexed, "specimen", root.specimen_id, ContextQuery(limit=3))
    assert len(neighborhood.nodes) == 4 and neighborhood.next_cursor
    assert all(edge.source == f"specimen:{root.specimen_id}" for edge in neighborhood.edges)
    next_page = graph(
        indexed,
        "specimen",
        root.specimen_id,
        ContextQuery(limit=3, cursor=neighborhood.next_cursor),
    )
    assert not {n.id for n in neighborhood.nodes[1:]} & {n.id for n in next_page.nodes[1:]}
    seed_demo(indexed)
    assert catalog(indexed, ContextQuery()).total == 8
    indexed.execute(
        text("UPDATE source_dataset SET is_synthetic=true WHERE id=:id"),
        {"id": indexed.scalar(select(SourceDataset.id).where(~SourceDataset.is_synthetic))},
    )
    assert catalog(indexed, ContextQuery()).total == 0
    with pytest.raises(HTTPException):
        graph(indexed, "specimen", root.specimen_id, ContextQuery())
    with pytest.raises(HTTPException):
        detail(indexed, "locality", uuid4(), ContextQuery())
