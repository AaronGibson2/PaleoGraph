"""Internal source-aware discovery; normal product endpoints remain UFVP-only."""

from pathlib import Path

import pytest
from fastapi import HTTPException


@pytest.mark.integration
def test_source_filtering_preserves_rights_material_counts_taxa_and_age_boundaries(
    db_session, tmp_path
):
    from test_ufvp import fixture_rows, make_archive

    from app.discovery.multi_source import InternalQuery, occurrence_catalog, source_counts
    from app.discovery.queries import catalog
    from app.discovery.schemas import ContextQuery
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.import_ufvp import ingest
    from app.ingestion.pbdb import Snapshot, stable_id

    fixture = Path(__file__).parent / "fixtures/pbdb"
    ingest_snapshot(db_session, Snapshot.load(fixture))
    rows = fixture_rows()
    rows[0].update(scientificName="Crenatosiren olseni", earliestEpochOrLowestSeries="Oligocene")
    result = ingest(db_session, make_archive(tmp_path, rows), raw_dir=tmp_path / "retained")
    assert result.status == "completed"
    assert source_counts(db_session) == {
        "ufvp_assertions": 8,
        "pbdb_occurrences": 8,
        "canonical_specimens": 8,
        "multi_source_occurrences": 16,
    }
    assert catalog(db_session, ContextQuery()).total == 8
    ufvp = occurrence_catalog(db_session, InternalQuery(source="ufvp", q="Crenatosiren"))
    pbdb = occurrence_catalog(db_session, InternalQuery(source="pbdb", q="Crenatosiren"))
    assert ufvp.total == pbdb.total == 1
    assert ufvp.items[0].taxon_id != pbdb.items[0].taxon_id
    assert ufvp.items[0].specimen_id and pbdb.items[0].specimen_id is None
    assert ufvp.items[0].source_license.endswith("/by-nc/4.0/")
    assert pbdb.items[0].source_license == "CC0 1.0"
    assert pbdb.items[0].source_policy_version == "pbdb-provider-envelope-v1"
    assert ufvp.items[0].source_policy_version == "ufvp-geology-v1:ics-2026-06"
    referenced = occurrence_catalog(
        db_session, InternalQuery(source="pbdb", reference_id=stable_id("reference", "17344"))
    )
    assert referenced.total == 1
    assert referenced.items[0].id == pbdb.items[0].id
    assert (
        occurrence_catalog(
            db_session, InternalQuery(source="ufvp", reference_id=stable_id("reference", "17344"))
        ).total
        == 0
    )
    for source, item in [("ufvp", ufvp.items[0]), ("pbdb", pbdb.items[0])]:
        for endpoint in (item.older_ma, item.younger_ma):
            assert (
                occurrence_catalog(
                    db_session,
                    InternalQuery(
                        source=source, q="Crenatosiren", older_ma=endpoint, younger_ma=endpoint
                    ),
                ).total
                == 1
            )
    seen = set()
    cursor = None
    while True:
        page = occurrence_catalog(db_session, InternalQuery(source="all", limit=3, cursor=cursor))
        assert page.total == 16
        assert not seen & {item.id for item in page.items}
        seen.update(item.id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert len(seen) == 16
    page = occurrence_catalog(db_session, InternalQuery(source="pbdb", limit=3))
    with pytest.raises(HTTPException, match="cursor"):
        occurrence_catalog(
            db_session, InternalQuery(source="ufvp", limit=3, cursor=page.next_cursor)
        )
