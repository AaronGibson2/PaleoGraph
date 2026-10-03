import csv
import io
import json
import zipfile
from pathlib import Path
from uuid import UUID

import pytest
from fixtures.synthetic import seed_demo
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.explore.queries import map_occurrences, occurrence_detail
from app.explore.schemas import ExploreQuery
from app.ingestion.import_ufvp import ingest
from app.ingestion.ufvp import Archive, normalize, parse_metadata, stable_id
from app.models import (
    Occurrence,
    SourceDataset,
    SourceRecord,
    SourceRecordRevision,
    Specimen,
    taxon_evidence,
)

FIXTURE = Path(__file__).parent / "fixtures/ufvp"


def fixture_rows() -> list[dict[str, str]]:
    return json.loads((FIXTURE / "records.json").read_text(encoding="utf-8"))


def make_archive(tmp_path: Path, rows: list[dict[str, str]]) -> Archive:
    target = tmp_path / "fixture.zip"
    output = io.StringIO(newline="")
    # The official meta.xml defines the order; fixture JSON retains that order.
    fields = list(fixture_rows()[0])
    writer = csv.writer(output, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
    writer.writerow(fields)
    writer.writerows([[row.get(key, "") for key in fields] for row in rows])
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("occurrence.txt", output.getvalue())
        archive.writestr("meta.xml", (FIXTURE / "meta.xml").read_bytes())
        archive.writestr("eml.xml", (FIXTURE / "eml.xml").read_bytes())
    return Archive(target)


def test_metadata_and_archive_boundary(tmp_path: Path) -> None:
    archive = make_archive(tmp_path, fixture_rows())
    assert archive.metadata.version == "1.182"
    assert archive.metadata.publisher == "Florida Museum of Natural History"
    assert archive.metadata.citation is None
    assert archive.metadata.license.endswith("/by-nc/4.0/")
    assert list(archive.rows()) == fixture_rows()
    changed_rights = (FIXTURE / "eml.xml").read_bytes().replace(b"by-nc/4.0", b"by/4.0")
    with pytest.raises(ValueError, match="license"):
        parse_metadata(changed_rights)


def test_physical_material_identifiers_geology_and_unknown_numeric_ages() -> None:
    raw = fixture_rows()[0]
    normalized = normalize(raw)
    assert normalized.source_id == raw["id"]
    assert normalized.raw == raw
    assert normalized.latitude == 27.49
    assert normalized.geology["earliestEpochOrLowestSeries"] == "Pleistocene, late"
    assert normalized.modified_at is None  # Source timezone is absent.
    assert stable_id("specimen", raw["id"]).version == 4
    assert stable_id("specimen", raw["id"]) != stable_id("occurrence", raw["id"])


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"decimalLatitude": ""}, "missing or nonnumeric coordinates"),
        ({"decimalLatitude": "NaN"}, "missing or nonnumeric coordinates"),
        ({"decimalLongitude": "181"}, "out-of-range coordinates"),
        ({"geodeticDatum": "NAD27"}, "unsupported or unspecified datum"),
        ({"geodeticDatum": ""}, "unsupported or unspecified datum"),
        ({"informationWithheld": "locality withheld"}, "withheld"),
    ],
)
def test_unusable_or_withheld_coordinates(changes: dict[str, str], status: str) -> None:
    normalized = normalize({**fixture_rows()[0], **changes})
    assert normalized.latitude is None and normalized.longitude is None
    assert normalized.coordinate_status == status


def test_generalized_positions_and_unparsed_uncertainty() -> None:
    normalized = normalize(
        {
            **fixture_rows()[0],
            "dataGeneralizations": "rounded position",
            "coordinateUncertaintyInMeters": "300 m",
        }
    )
    assert normalized.generalized and normalized.latitude is not None
    assert normalized.uncertainty is None
    assert any("uncertainty" in warning for warning in normalized.warnings)
    assert normalized.raw["coordinateUncertaintyInMeters"] == "300 m"
    assert (
        normalize({**fixture_rows()[0], "scientificName": ""}).name == "Identification not supplied"
    )
    with pytest.raises(ValueError, match="physical material"):
        normalize({**fixture_rows()[0], "basisOfRecord": "HumanObservation"})


@pytest.mark.integration
def test_idempotent_material_import_and_revision_history(
    db_session: Session, tmp_path: Path
) -> None:
    rows = fixture_rows()
    archive = make_archive(tmp_path, rows)
    first = ingest(db_session, archive, raw_dir=tmp_path / "retained")
    assert first.status == "completed" and first.records_inserted == 8
    second = ingest(db_session, archive, raw_dir=tmp_path / "retained")
    assert second.status == "completed" and second.records_inserted == second.records_updated == 0
    assert db_session.scalar(select(func.count()).select_from(Specimen)) == 8
    assert db_session.scalar(select(func.count()).select_from(Occurrence)) == 8
    specimen = db_session.get(Specimen, stable_id("specimen", rows[0]["id"]))
    assert specimen is not None and specimen.occurrence_identifier == rows[0]["occurrenceID"]
    assert specimen.catalog_number == rows[0]["catalogNumber"]
    changed = {**rows[0], "catalogNumber": "changed fictional test identifier"}
    third = ingest(
        db_session, make_archive(tmp_path, [changed, *rows[1:]]), raw_dir=tmp_path / "retained"
    )
    assert third.records_updated == 1
    assert db_session.scalar(select(func.count()).select_from(SourceRecordRevision)) == 9
    assert db_session.get(Occurrence, stable_id("occurrence", rows[0]["id"])) is not None


@pytest.mark.integration
def test_sample_partial_failure_and_complete_lifecycle(db_session: Session, tmp_path: Path) -> None:
    rows = fixture_rows()
    ingest(db_session, make_archive(tmp_path, rows), limit=None, raw_dir=tmp_path / "retained")
    sample = ingest(
        db_session, make_archive(tmp_path, rows[:2]), limit=2, raw_dir=tmp_path / "retained"
    )
    assert sample.status == "completed"
    assert (
        db_session.scalar(
            select(func.count()).select_from(SourceRecord).where(SourceRecord.is_current)
        )
        == 8
    )
    partial = ingest(
        db_session,
        make_archive(tmp_path, [rows[0], {**rows[1], "basisOfRecord": "unknown"}]),
        limit=None,
        raw_dir=tmp_path / "retained",
    )
    assert partial.status == "partial" and partial.records_failed == 1
    assert (
        db_session.scalar(
            select(func.count()).select_from(SourceRecord).where(SourceRecord.is_current)
        )
        == 8
    )
    complete = ingest(
        db_session, make_archive(tmp_path, rows[:2]), limit=None, raw_dir=tmp_path / "retained"
    )
    assert complete.status == "completed"
    assert (
        db_session.scalar(
            select(func.count()).select_from(SourceRecord).where(SourceRecord.is_current)
        )
        == 2
    )
    assert db_session.scalar(select(func.count()).select_from(Specimen)) == 8  # Never hard deleted.


@pytest.mark.integration
def test_same_catalog_triplet_remains_distinct_material(
    db_session: Session, tmp_path: Path
) -> None:
    rows = fixture_rows()
    rows[1] = {
        **rows[1],
        **{key: rows[0][key] for key in ("institutionCode", "collectionCode", "catalogNumber")},
    }
    run = ingest(db_session, make_archive(tmp_path, rows[:2]), raw_dir=tmp_path / "retained")
    assert run.records_accepted == 2
    identifiers: list[UUID] = list(db_session.scalars(select(Specimen.id)))
    assert len(set(identifiers)) == 2


@pytest.mark.integration
def test_real_api_semantics_and_snapshot_provenance(db_session: Session, tmp_path: Path) -> None:
    rows = fixture_rows()
    ingest(db_session, make_archive(tmp_path, rows), raw_dir=tmp_path / "retained")
    seed_demo(db_session)
    bounds = {"west": -180, "south": -90, "east": 180, "north": 90}
    museum = map_occurrences(db_session, ExploreQuery(**bounds))
    assert museum.returned == 8 and all(not item.is_synthetic for item in museum.items)
    assert all(item.older_ma is None and item.younger_ma is None for item in museum.items)
    assert (
        map_occurrences(db_session, ExploreQuery(**bounds, older_ma=5, younger_ma=2)).returned == 0
    )
    assert map_occurrences(db_session, ExploreQuery(**bounds)).returned == 8
    statements: list[str] = []

    def record_query(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", record_query)
    try:
        detail = occurrence_detail(db_session, stable_id("occurrence", rows[0]["id"]))
    finally:
        event.remove(db_session.bind, "before_cursor_execute", record_query)
    assert len(statements) == 2
    assert detail is not None and detail.specimen is not None
    assert detail.specimen.catalog_number == rows[0]["catalogNumber"]
    assert detail.source_values["earliestEpochOrLowestSeries"] == "Pleistocene, late"
    assert detail.evidence[0].license.endswith("/by-nc/4.0/")
    dataset = db_session.get(SourceDataset, detail.evidence[0].dataset_id)
    assert dataset is not None
    dataset.version = "fictional later snapshot"
    db_session.flush()
    db_session.expire_all()
    old_detail = occurrence_detail(db_session, detail.id)
    assert old_detail is not None and old_detail.evidence[0].dataset_version == "1.182"


@pytest.mark.integration
def test_failed_snapshot_and_replaced_current_evidence(db_session: Session, tmp_path: Path) -> None:
    rows = fixture_rows()
    ingest(db_session, make_archive(tmp_path, rows), raw_dir=tmp_path / "retained")
    record_id = stable_id("record", rows[0]["id"])
    old_taxon = db_session.scalar(
        select(taxon_evidence.c.taxon_id).where(taxon_evidence.c.source_record_id == record_id)
    )
    changed = {**rows[0], "scientificName": "Fictional revised identification"}
    ingest(db_session, make_archive(tmp_path, [changed]), raw_dir=tmp_path / "retained")
    links = list(
        db_session.scalars(
            select(taxon_evidence.c.taxon_id).where(taxon_evidence.c.source_record_id == record_id)
        )
    )
    assert len(links) == 1 and links[0] != old_taxon
    archive = make_archive(tmp_path, rows)

    def broken_rows():
        yield rows[0]
        raise ValueError("Fictional damaged core stream")

    archive.rows = broken_rows
    failed = ingest(db_session, archive, limit=None, raw_dir=tmp_path / "retained")
    assert failed.status == "failed" and failed.records_failed == 1
    assert "damaged core stream" in (failed.error_summary or "")
    assert (
        db_session.scalar(
            select(func.count()).select_from(SourceRecord).where(SourceRecord.is_current)
        )
        == 8
    )
