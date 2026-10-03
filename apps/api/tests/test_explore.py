from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fixtures.synthetic import demo_id, seed_demo
from pydantic import ValidationError
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.explore.queries import age_overlap, map_occurrences, occurrence_detail
from app.explore.schemas import ExploreQuery
from app.main import create_app
from app.models import CollectionEvent, Occurrence, SourceDataset, SourceRecord, Taxon

WORLD = {"west": -180, "south": -90, "east": 180, "north": 90}


@pytest.mark.parametrize(
    "changes",
    [
        {"west": -181},
        {"north": 91},
        {"south": 10, "north": 0},
        {"older_ma": 1},
        {"older_ma": 1, "younger_ma": 2},
        {"older_ma": -1, "younger_ma": 0},
        {"west": float("nan")},
        {"older_ma": float("inf"), "younger_ma": 0},
        {"limit": 1001},
    ],
)
def test_query_rejects_invalid_bounds(changes: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        ExploreQuery.model_validate({**WORLD, **changes})


def test_validation_and_time_metadata_without_database() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/map/occurrences", params={**WORLD, "older_ma": 2})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_REQUEST"
        config = client.get("/api/v1/time-intervals").json()
        assert config["kind"] == "international_chronostratigraphic_chart"
        assert config["version"] == "2026-06"


@pytest.fixture
def seeded(db_session: Session) -> Session:
    seed_demo(db_session)
    db_session.execute(text("UPDATE source_dataset SET is_synthetic = false"))
    return db_session


@pytest.mark.integration
@pytest.mark.parametrize(
    "older,younger,expected",
    [
        ("2", "1", True),
        ("3", "2", True),
        ("1", "0", True),
        ("4", "3", False),
        ("0.9", "0", False),
        (None, None, False),
        ("2", None, False),
        (None, "1", False),
        ("1", "1", True),
    ],
)
def test_inclusive_overlap(
    db_session: Session, older: str | None, younger: str | None, expected: bool
) -> None:
    item = CollectionEvent(
        name="Test context",
        older_ma=Decimal(older) if older else None,
        younger_ma=Decimal(younger) if younger else None,
    )
    db_session.add(item)
    db_session.flush()
    matched = db_session.scalar(
        select(CollectionEvent.id).where(CollectionEvent.id == item.id, age_overlap(2, 1))
    )
    assert (matched is not None) == expected


@pytest.mark.integration
def test_seed_idempotency_and_reset(seeded: Session) -> None:
    seeded.execute(text("UPDATE source_dataset SET is_synthetic = true"))
    seed_demo(seeded)
    assert seeded.scalar(select(func.count()).select_from(Occurrence)) == 40
    assert seeded.scalar(select(func.count()).select_from(SourceRecord)) == 40
    unrelated = Taxon(scientific_name="Unrelated concept")
    seeded.add(unrelated)
    seeded.flush()
    seed_demo(seeded, reset=True)
    assert seeded.get(Taxon, unrelated.id) is not None
    assert seeded.scalar(select(func.count()).select_from(Occurrence)) == 40
    assert demo_id(6, 0).version == 4


@pytest.mark.integration
def test_bbox_and_unknown_ages(seeded: Session) -> None:
    all_ages = map_occurrences(seeded, ExploreQuery(**WORLD))
    assert all_ages.returned == 36  # Two missing-location examples (four assertions).
    assert any(item.older_ma is None or item.younger_ma is None for item in all_ages.items)
    filtered = map_occurrences(seeded, ExploreQuery(**WORLD, older_ma=2, younger_ma=1))
    assert 0 < filtered.returned < all_ages.returned
    assert all(item.older_ma is not None and item.younger_ma is not None for item in filtered.items)
    assert map_occurrences(seeded, ExploreQuery(west=0, east=1, south=0, north=1)).returned == 0
    limited = map_occurrences(seeded, ExploreQuery(**WORLD, limit=2))
    assert limited.returned == 2 and limited.truncated


@pytest.mark.integration
def test_antimeridian_and_boundary_points(seeded: Session) -> None:
    for i, lon in enumerate((175, -175, 170, -170)):
        seeded.execute(
            text(
                "UPDATE locality SET geom = ST_SetSRID(ST_MakePoint(:lon, 0), 4326) WHERE id = :id"
            ),
            {"lon": lon, "id": demo_id(4, i)},
        )
    response = map_occurrences(seeded, ExploreQuery(west=170, east=-170, south=-1, north=1))
    assert response.returned == 8
    assert {item.longitude for item in response.items} == {175, -175, 170, -170}


@pytest.mark.integration
@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE collection_event SET older_ma = -1",
        "UPDATE collection_event SET older_ma = 0, younger_ma = 2",
        "UPDATE collection_event SET older_ma = 'NaN'::numeric",
        "UPDATE locality SET geom = ST_SetSRID(ST_MakePoint(181, 0), 4326)",
        "UPDATE locality SET geom = ST_SetSRID(ST_MakePoint(0, 91), 4326)",
        "UPDATE locality SET location_is_withheld = true WHERE geom IS NOT NULL",
        "UPDATE source_record SET source_dataset_id = 'de000000-0000-4000-8000-000200000001' "
        "WHERE ingestion_run_id = 'de000000-0000-4000-8000-000800000000'",
    ],
)
def test_database_constraints(seeded: Session, statement: str) -> None:
    with pytest.raises(IntegrityError), seeded.begin_nested():
        seeded.execute(text(statement))


@pytest.mark.integration
def test_source_identity_is_dataset_scoped(seeded: Session) -> None:
    with pytest.raises(IntegrityError), seeded.begin_nested():
        seeded.execute(
            text("UPDATE source_record SET source_record_id = 'DEMO-001' WHERE id = :id"),
            {"id": demo_id(7, 2)},
        )
    seeded.execute(
        text("UPDATE source_record SET source_record_id = 'DEMO-001' WHERE id = :id"),
        {"id": demo_id(7, 1)},
    )
    assert seeded.scalar(select(func.count()).select_from(SourceDataset)) == 2


@pytest.mark.integration
def test_detail_provenance_and_constant_queries(seeded: Session) -> None:
    statements: list[str] = []

    def record_query(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(seeded.bind, "before_cursor_execute", record_query)
    try:
        detail = occurrence_detail(seeded, demo_id(6, 0))
    finally:
        event.remove(seeded.bind, "before_cursor_execute", record_query)
    assert len(statements) == 2
    assert detail is not None and not detail.evidence[0].is_synthetic
    assert detail.evidence[0].dataset_id == demo_id(2, 0)
    assert detail.evidence[0].ingestion_run_id == demo_id(8, 0)
    assert "raw_payload" not in detail.model_dump()
    withheld = occurrence_detail(seeded, demo_id(6, 38))
    assert withheld is not None and withheld.location_is_withheld
    assert withheld.latitude is None and withheld.longitude is None


@pytest.mark.integration
def test_api_contract(seeded: Session) -> None:
    app = create_app()

    def override() -> Iterator[Session]:
        yield seeded

    app.dependency_overrides[get_session] = override
    with TestClient(app) as client:
        response = client.get("/api/v1/map/occurrences", params=WORLD)
        assert response.status_code == 200
        body = response.json()
        assert body["returned"] == 36 and body["truncated"] is False
        item = body["items"][0]
        assert isinstance(item["latitude"], float) and not item["is_synthetic"]
        detail = client.get(f"/api/v1/occurrences/{item['id']}")
        assert detail.status_code == 200
        assert detail.json()["evidence"][0]["source_record_id"].startswith("DEMO-")
        assert client.get(f"/api/v1/occurrences/{uuid4()}").json()["error"]["code"] == "NOT_FOUND"
