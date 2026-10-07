"""Source-aware user-facing contracts on independent retained scientific fixtures."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_catalog_contract_keeps_occurrences_material_and_cursor_scope_distinct(
    db_session, tmp_path
):
    from test_ufvp import fixture_rows, make_archive

    from app.db import get_session
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.import_ufvp import ingest
    from app.ingestion.pbdb import Snapshot
    from app.main import create_app

    ingest_snapshot(db_session, Snapshot.load(Path(__file__).parent / "fixtures/pbdb"))
    assert (
        ingest(db_session, make_archive(tmp_path, fixture_rows()), raw_dir=tmp_path / "raw").status
        == "completed"
    )
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        published = client.get("/api/v1/catalog", params={"source": "pbdb", "limit": 3})
        assert published.status_code == 200
        page = published.json()
        assert page["total"] == 8
        assert all(
            item["specimen_id"] is None and item["evidence_kind"] == "occurrence"
            for item in page["items"]
        )
        assert all(
            item["source"] == "pbdb" and item["source_license"] == "CC0 1.0"
            for item in page["items"]
        )
        assert page["counts"] == {"museum_material": 0, "published_occurrences": 8}
        lineage = client.get("/api/v1/lineage", params={"source": "all", "limit": 100}).json()
        assert sum(i["assertion_count"] for i in lineage["items"]) == 16
        assert sum(i["assertion_count"] for i in lineage["items"] if i["source"] == "pbdb") == 8
        assert all(
            i["known_age_count"] + i["unknown_age_count"] == i["assertion_count"]
            for i in lineage["items"]
        )
        mixed = client.get("/api/v1/catalog", params={"source": "all"}).json()
        assert mixed["total"] == 16
        assert mixed["counts"] == {"museum_material": 8, "published_occurrences": 8}
        assert sum(item["specimen_id"] is not None for item in mixed["items"]) == 8
        incompatible = client.get(
            "/api/v1/catalog", params={"source": "ufvp", "cursor": page["next_cursor"]}
        )
        assert incompatible.status_code == 422
        assert client.get("/api/v1/catalog", params={"source": "unknown"}).status_code == 422


@pytest.mark.integration
def test_projected_occurrence_membership_equals_authority_and_invalidates_on_dependency_change(
    db_session,
):
    from sqlalchemy import text

    from app.discovery.multi_source import InternalQuery, occurrence_catalog
    from app.discovery.occurrence_browse import rebuild
    from app.discovery.product import catalog
    from app.discovery.schemas import ContextQuery
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.pbdb import Snapshot

    ingest_snapshot(db_session, Snapshot.load(Path(__file__).parent / "fixtures/pbdb"))
    authoritative = occurrence_catalog(db_session, InternalQuery(source="pbdb"))
    rebuild(db_session)
    projected = catalog(db_session, ContextQuery(source="pbdb"))
    assert {i.id for i in projected.items} == {i.id for i in authoritative.items}
    assert projected.total == authoritative.total == 8
    db_session.execute(
        text("UPDATE source_record SET is_current=false WHERE record_type='material'")
    )
    after = catalog(db_session, ContextQuery(source="pbdb"))
    live = occurrence_catalog(db_session, InternalQuery(source="pbdb"))
    assert after.total == live.total == 5
    assert {i.id for i in after.items} == {i.id for i in live.items}
    rebuild(db_session)
    db_session.execute(
        text("""DELETE FROM source_normalization_current
        WHERE source_record_id=(SELECT source_record_id FROM catalog_entry WHERE occurrence_id=:id)
        """),
        {"id": after.items[0].id},
    )
    projected = catalog(db_session, ContextQuery(source="pbdb"))
    live = occurrence_catalog(db_session, InternalQuery(source="pbdb"))
    assert projected.total == live.total == 4


@pytest.mark.integration
def test_public_pbdb_context_lineage_detail_and_explicit_references(db_session):
    from app.db import get_session
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.pbdb import Snapshot, stable_id
    from app.main import create_app

    ingest_snapshot(db_session, Snapshot.load(Path(__file__).parent / "fixtures/pbdb"))
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        occurrence = str(stable_id("occurrence", "187885"))
        detail = client.get(f"/api/v1/entities/occurrence/{occurrence}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["entity"]["source"] == "pbdb"
        assert body["occurrence"]["material_evidence_count"] > 0
        assert body["occurrence"]["modern_position"]["status"] == "datum-unverified"
        assert "references" not in body["occurrence"]
        context = next(e for e in body["related"] if e["kind"] == "locality")
        dossier = client.get(
            f"/api/v1/localities/{context['id']}", params={"source": "pbdb"}
        ).json()
        assert dossier["entity"]["source"] == "pbdb"
        assert dossier["assertion_count"] > 0 and dossier["specimen_count"] == 0
        assert dossier["properties"]["longitude"] is None
        lineage = client.get("/api/v1/lineage", params={"source": "pbdb"}).json()
        assert lineage["items"] and all(i["specimen_count"] == 0 for i in lineage["items"])
        focused = client.get(
            "/api/v1/lineage", params={"source": "pbdb", "focus": lineage["items"][0]["id"]}
        )
        assert focused.status_code == 200
        refs = client.get(f"/api/v1/entities/occurrence/{occurrence}/references").json()
        assert refs["items"] and any(i["role"] == "identification" for i in refs["items"])
        ref = refs["items"][0]["id"]
        assert client.get(f"/api/v1/entities/reference/{ref}").status_code == 200
        found = client.get("/api/v1/search", params={"source": "pbdb", "q": "187885"}).json()
        assert found["items"][0]["kind"] == "occurrence"
        collection_hit = client.get(
            "/api/v1/search", params={"source": "pbdb", "q": "col:18554"}
        ).json()
        assert collection_hit["items"][0]["kind"] == "locality"
        assert collection_hit["items"][0]["subtitle"] == "PBDB collection context"
        mapped = client.get("/api/v1/map/places", params={"source": "pbdb"}).json()
        assert mapped["total_places"] == 0 and mapped["unmapped_published_occurrences"] == 8
