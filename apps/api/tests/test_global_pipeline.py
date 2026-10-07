"""Commit/restart checks use only the guarded, project-owned disposable database."""

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.discovery.pbdb import inspect_occurrence, occurrence_catalog
from app.discovery.schemas import ContextQuery
from app.ingestion.archive import LocalArchiveStore
from app.ingestion.archive_db import audit_normalizations, raw_revision
from app.ingestion.global_pipeline import ingest_global, schema_name, target_guard
from app.ingestion.import_pbdb import ingest_snapshot, plan, record_id
from app.ingestion.pbdb import ADAPTER_VERSION, Snapshot, digest, stable_id
from app.ingestion.storage_conversion import convert_to_design_c, restore_legacy
from app.models import NormalizedSourceRevision, SourceRecord

FIXTURE = Path(__file__).parent / "fixtures/pbdb"


@pytest.mark.integration
def test_large_cache_refresh_preserves_exact_revision_authority(db_session):
    from app.ingestion.import_pbdb import DATASET_UUID

    ingest_snapshot(db_session, Snapshot.load(FIXTURE))
    node = db_session.scalars(
        select(NormalizedSourceRevision)
        .join(SourceRecord, SourceRecord.id == NormalizedSourceRevision.source_record_id)
        .where(SourceRecord.record_type == "reference")
        .limit(1)
    ).one()
    assert node.payload["dependencies"] == []
    rows = []
    for index in range(4096):
        adapter = f"cache-history-test-{index}"
        rows.append(
            {
                "source_record_id": node.source_record_id,
                "content_hash": node.content_hash,
                "normalization_hash": digest({"adapter": adapter, "payload": node.payload}),
                "adapter_version": adapter,
                "ingestion_run_id": node.ingestion_run_id,
                "payload": node.payload,
                "frame_format": "full",
            }
        )
    # One statement crosses the large-set boundary with valid historical hashes.
    db_session.execute(insert(NormalizedSourceRevision).values(rows))
    expected = db_session.scalar(
        text("""SELECT count(*) FROM normalized_source_revision n
      LEFT JOIN source_normalization_current c USING(source_record_id)
      WHERE c.source_record_id IS NULL OR n.content_hash<>c.content_hash
        OR n.normalization_hash<>c.normalization_hash""")
    )
    assert expected == 4096
    assert db_session.scalar(text("SELECT count(*) FROM source_normalization_invalid")) == expected
    db_session.execute(
        text("UPDATE source_dataset SET is_synthetic=true WHERE id=:id"), {"id": DATASET_UUID}
    )
    assert (
        db_session.scalar(text("SELECT count(*) FROM source_normalization_invalid")) == 4096 + 375
    )
    db_session.execute(
        text("UPDATE source_dataset SET is_synthetic=false WHERE id=:id"), {"id": DATASET_UUID}
    )
    assert db_session.scalar(text("SELECT count(*) FROM source_normalization_invalid")) == expected


@pytest.mark.integration
def test_committed_staging_failure_resume_atomic_publish_and_exact_replay(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires dedicated migrated integration database")
    engine = create_engine(make_url(url).set(host="127.0.0.1"), connect_args={"connect_timeout": 5})
    snapshot = Snapshot.load(FIXTURE)
    target_guard(engine, snapshot.manifest, None)
    # This test owns committed work. Never clear a normal or populated target.
    assert engine.url.database == "paleograph_test" and engine.url.port == 55432
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM source_record")) == 0
    store = LocalArchiveStore(tmp_path / "archive")
    work = tmp_path / "work"
    failures = ["normalization_batch", "postgres_batch", "before_ready_switch"]

    def stop_at(point):
        if point == failures[0]:
            raise RuntimeError(f"deliberate interruption {point}")

    try:
        for _point in tuple(failures):
            with pytest.raises(RuntimeError, match="deliberate interruption"):
                ingest_global(engine, FIXTURE, store, work, batch_size=3, hook=stop_at)
            failures.pop(0)
            with engine.connect() as c:
                assert c.scalar(text("SELECT count(*) FROM source_record")) == 0
                assert c.scalar(text("SELECT state FROM global_ingestion_job")) == "failed"
                assert c.scalar(text("SELECT version FROM source_dataset")) is None
        result = ingest_global(engine, FIXTURE, store, work, batch_size=3)
        assert result["status"] == "ready"
        with pytest.raises(DBAPIError, match="Published archive object metadata is immutable"):
            with engine.begin() as connection:
                connection.execute(
                    text("""INSERT INTO source_archive_object
                  (archive_id,object_hash,original_hash,compressed_bytes,original_bytes,
                   record_count,kind)
                  SELECT archive_id,repeat('f',64),original_hash,compressed_bytes,
                    original_bytes,record_count,kind FROM source_archive_object LIMIT 1""")
                )
        records, dependencies = plan(snapshot)
        with Session(engine) as session:
            for name in ("occurrence", "material_evidence", "occurrence_evidence", "catalog_entry"):
                assert (
                    session.scalar(
                        text("SELECT reltuples FROM pg_class WHERE oid=to_regclass(:name)"),
                        {"name": name},
                    )
                    > 0
                )
            assert audit_normalizations(session)["verified_normalizations"] == len(records)
            assert session.scalar(text("SELECT count(*) FROM source_record")) == len(records)
            assert session.scalar(text("SELECT count(*) FROM source_normalization_invalid")) == 0
            assert session.scalar(text("SELECT count(*) FROM source_record_dependency")) == 0
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM source_record_revision WHERE raw_payload IS NOT NULL"
                    )
                )
                == 0
            )
            assert session.scalar(text("SELECT records_inserted FROM ingestion_run")) == len(
                records
            )
            assert session.scalar(text("SELECT records_updated FROM ingestion_run")) == 0
            for n in session.scalars(select(NormalizedSourceRevision)):
                key = (n.payload["record_type"], n.payload["external_id"])
                original = records[key]
                assert (
                    raw_revision(session, store, n.source_record_id, n.content_hash)
                    == original["raw"]
                )
                frame = session.execute(
                    text("""SELECT dependency_record_id,dependency_content_hash
                    FROM source_dependency_frame WHERE source_record_id=:id
                      AND content_hash=:hash AND normalization_hash=:norm
                    ORDER BY dependency_record_id,dependency_content_hash"""),
                    {
                        "id": n.source_record_id,
                        "hash": n.content_hash,
                        "norm": n.normalization_hash,
                    },
                ).all()
                expected = sorted(
                    (str(record_id(*d)), records[d]["hash"]) for d in dependencies[key]
                )
                assert [(str(r[0]), r[1]) for r in frame] == expected
                payload = {**n.payload, "dependencies": expected}
                assert (
                    digest({"adapter": ADAPTER_VERSION, "payload": payload}) == n.normalization_hash
                )
            page = occurrence_catalog(session, ContextQuery())
            assert page.total == 8
            detail = inspect_occurrence(session, stable_id("occurrence", "148077"))
            assert detail["history_complete"]
            assert detail["original_identification"]["identified_name"] == "aff. Halitherium olseni"
            assert detail["latest_identification"]["accepted_name"] == "Crenatosiren olseni"
            assert detail["source_numeric_age"] == {"older_ma": None, "younger_ma": None}
        before = sorted(p.name for p in (tmp_path / "archive").iterdir())
        replay = ingest_global(engine, FIXTURE, store, work)
        assert replay["exact_replay"] and replay["mutations"] == {}
        assert before == sorted(p.name for p in (tmp_path / "archive").iterdir())
        restored = restore_legacy(engine, store)
        assert restored == {
            "rehydrated_raw": len(records),
            "rehydrated_normalizations": len(records),
        }

        # Interrupt the legacy conversion after it has persisted READY bytes;
        # recovery depends on the pinned archive, not a hidden temporary file.
        def interrupt_conversion(point):
            if point == "before_raw_removal":
                raise RuntimeError("deliberate conversion interruption")

        with pytest.raises(RuntimeError, match="conversion interruption"):
            convert_to_design_c(engine, FIXTURE, store, hook=interrupt_conversion)
        with engine.connect() as c:
            assert c.scalar(
                text("SELECT count(*) FROM source_record_revision WHERE raw_payload IS NOT NULL")
            ) == len(records)
        assert convert_to_design_c(engine, FIXTURE, store)["status"] == "ready"
        with Session(engine) as session:
            assert occurrence_catalog(session, ContextQuery()).model_dump() == page.model_dump()
            assert inspect_occurrence(session, stable_id("occurrence", "148077")) == detail
        assert restore_legacy(engine, store)["rehydrated_raw"] == len(records)
        assert convert_to_design_c(engine, FIXTURE, store)["status"] == "ready"
        changed = tmp_path / "changed"
        shutil.copytree(FIXTURE, changed)
        header = json.loads((changed / "manifest.json").read_bytes())
        entry = next(e for e in header["responses"] if e["kind"] == "references")
        file = changed / entry["file"]
        body = json.loads(file.read_bytes())
        body["records"][0]["pubtitle"] = "Changed retained reference, deliberate revision test"
        encoded = json.dumps(body).encode()
        file.write_bytes(encoded)
        entry.update(bytes=len(encoded), sha256=hashlib.sha256(encoded).hexdigest())
        (changed / "manifest.json").write_text(json.dumps(header), encoding="utf8")
        with engine.connect() as c:
            prior_raw = c.scalar(text("SELECT count(*) FROM source_record_revision"))
            prior_nodes = c.scalar(text("SELECT count(*) FROM normalized_source_revision"))
        observed_old = []

        def inspect_atomic_switch(point):
            if point == "before_ready_switch":
                with Session(engine) as reader:
                    assert (
                        reader.scalar(text("SELECT version FROM source_dataset")) == snapshot.hash
                    )
                    assert occurrence_catalog(reader, ContextQuery()).total == 8
                    observed_old.append(True)

        newer = ingest_global(engine, changed, store, work, hook=inspect_atomic_switch)
        assert observed_old == [True]
        assert newer["mutations"]["source"] == 1
        with Session(engine) as session:
            assert (
                session.scalar(text("SELECT count(*) FROM source_record_revision")) == prior_raw + 1
            )
            assert (
                session.scalar(text("SELECT count(*) FROM normalized_source_revision"))
                > prior_nodes
            )
            assert occurrence_catalog(session, ContextQuery()).total == 8
            assert session.scalar(text("SELECT version FROM source_dataset")) == digest(header)
    finally:
        with engine.begin() as c:
            for schema in c.scalars(text("SELECT staging_schema FROM global_ingestion_job")):
                c.execute(text(f"DROP SCHEMA IF EXISTS {schema_name(schema)} CASCADE"))
            c.execute(text("TRUNCATE source,source_archive CASCADE"))
        engine.dispose()


@pytest.mark.integration
@pytest.mark.parametrize(
    "point",
    [
        "before_archive",
        "archive_batch",
        "after_archive_before_verify",
        "backfill_batch",
        "before_raw_removal",
        "before_conversion_ready",
    ],
)
def test_conversion_interruption_boundaries_preserve_and_resume_evidence(tmp_path, point):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires dedicated integration database")
    engine = create_engine(make_url(url).set(host="127.0.0.1"), connect_args={"connect_timeout": 5})
    assert engine.url.database == "paleograph_test" and engine.url.port == 55432
    snapshot = Snapshot.load(FIXTURE)
    store = LocalArchiveStore(tmp_path / "archive")
    with Session(engine) as session:
        assert session.scalar(text("SELECT count(*) FROM source_record")) == 0
        ingest_snapshot(session, snapshot)
        before = occurrence_catalog(session, ContextQuery()).model_dump()

    def stop(boundary):
        if boundary == point:
            raise RuntimeError("deliberate boundary interruption")

    try:
        with pytest.raises(RuntimeError, match="boundary interruption"):
            convert_to_design_c(engine, FIXTURE, store, hook=stop)
        with Session(engine) as session:
            assert occurrence_catalog(session, ContextQuery()).model_dump() == before
        assert convert_to_design_c(engine, FIXTURE, store)["status"] == "ready"
        records, _ = plan(snapshot)
        with Session(engine) as session:
            for key, row in records.items():
                assert raw_revision(session, store, record_id(*key), row["hash"]) == row["raw"]
            assert occurrence_catalog(session, ContextQuery()).model_dump() == before
    finally:
        with engine.begin() as c:
            c.execute(text("TRUNCATE source,source_archive CASCADE"))
        engine.dispose()
