"""Verified, resumable Design C conversion and automated legacy rehydration.

Every deletion follows reconstruction from READY archive bytes and verification
of the original normalization hash. Checkpoints are operational PostgreSQL rows;
recovery requires only PostgreSQL and the explicitly pinned archive store.
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.ingestion.archive import (
    ArchiveError,
    ArchiveStore,
    publish_manifest,
    raw_chunks,
    read_object,
    verify_archive,
)
from app.ingestion.archive_db import (
    archive_objects,
    object_metadata,
    raw_revision,
    register_archive,
)
from app.ingestion.global_pipeline import checkpoint_job, target_guard
from app.ingestion.global_staging import archive_snapshot
from app.ingestion.import_pbdb import DATASET_UUID
from app.ingestion.pbdb import digest, stable_id
from app.models import (
    GlobalIngestionJob,
    NormalizedSourceRevision,
    SourceArchive,
    SourceArchiveObject,
    SourceRecord,
    SourceRecordRevision,
)

BATCH = 256


def reconstructed_payload(session: Session, node: NormalizedSourceRevision) -> dict[str, Any]:
    """One bounded complete proof frame, including historical versions."""
    frame = session.execute(
        text("""SELECT dependency_record_id,dependency_content_hash
          FROM source_dependency_frame WHERE source_record_id=:id AND content_hash=:hash
            AND normalization_hash=:norm ORDER BY dependency_record_id,dependency_content_hash
          LIMIT 50001"""),
        {"id": node.source_record_id, "hash": node.content_hash, "norm": node.normalization_hash},
    ).all()
    if len(frame) > 50000:
        raise ArchiveError("Normalization proof exceeds supported fanout bound")
    dependencies = [(str(r[0]), r[1]) for r in frame]
    payload = {**node.payload, "dependencies": dependencies}
    if digest({"adapter": node.adapter_version, "payload": payload}) != node.normalization_hash:
        raise ArchiveError("Reconstructed normalization differs from original immutable hash")
    return payload


def raw_records(engine: Engine, store: ArchiveStore) -> Iterator[dict[str, Any]]:
    with Session(engine) as session:
        query = text("""SELECT r.source_record_id,r.content_hash,r.raw_payload
          FROM source_record_revision r JOIN source_record s ON s.id=r.source_record_id
          WHERE s.source_dataset_id=:dataset ORDER BY r.source_record_id,r.content_hash""")
        for row in session.execute(
            query, {"dataset": DATASET_UUID}, execution_options={"yield_per": BATCH}
        ).yield_per(BATCH):
            raw = row.raw_payload
            if raw is None:
                raw = raw_revision(session, store, row.source_record_id, row.content_hash)
            yield {
                "source_record_id": str(row.source_record_id),
                "content_hash": row.content_hash,
                "raw": raw,
            }


def backfill_archive(
    engine: Engine,
    store: ArchiveStore,
    archive_id: UUID,
    manifest: dict[str, Any],
    hook: Callable[[str], None],
) -> int:
    """Each hash-verified object is a durable checkpoint; safe to replay all objects."""
    with Session(engine) as session:
        objects = archive_objects(session, archive_id)
    count = 0
    for entry in manifest["files"]:
        if entry["kind"] != "raw-records":
            continue
        locators = []
        for ordinal, line in enumerate(read_object(store, entry).splitlines()):
            row = json.loads(line)
            if digest(row["raw"]) != row["content_hash"]:
                raise ArchiveError("Conversion raw reconstruction hash mismatch")
            locators.append(
                {"id": row["source_record_id"], "hash": row["content_hash"], "ordinal": ordinal}
            )
        if len(locators) != entry["records"]:
            raise ArchiveError("Conversion raw object row count mismatch")
        with engine.begin() as c:
            found = c.scalar(
                text("""SELECT count(*) FROM
              jsonb_to_recordset(CAST(:rows AS jsonb)) v(id uuid,hash text,ordinal integer)
              JOIN source_record_revision r
                ON r.source_record_id=v.id AND r.content_hash=v.hash"""),
                {"rows": json.dumps(locators)},
            )
            if found != len(locators):
                raise ArchiveError("Archive contains an unknown conversion revision")
            c.execute(
                text("""UPDATE source_record_revision r SET archive_object_id=:object,
              archive_row=v.ordinal FROM jsonb_to_recordset(CAST(:rows AS jsonb))
              v(id uuid,hash text,ordinal integer)
              WHERE r.source_record_id=v.id AND r.content_hash=v.hash"""),
                {"object": objects[entry["hash"]], "rows": json.dumps(locators)},
            )
        count += len(locators)
        hook("backfill_batch")
    return count


def convert_to_design_c(
    engine: Engine,
    snapshot_path: Path,
    store: ArchiveStore,
    *,
    hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Scope-limited conversion; normal conversion stays gated for a later phase."""
    header_path = snapshot_path / "manifest.json"
    if header_path.stat().st_size > 32 * 1024 * 1024:
        raise ArchiveError("Conversion snapshot header exceeds manifest bound")
    header = json.loads(header_path.read_bytes())
    target_guard(engine, header, None)
    notify = hook or (lambda _: None)
    snapshot_hash = digest({"operation": "design-c-conversion", "snapshot": digest(header)})
    job_id = stable_id("ingestion-job", snapshot_hash)
    with engine.connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(74003001)"))
        try:
            with Session(engine) as session, session.begin():
                job = session.get(GlobalIngestionJob, job_id)
                if job is None:
                    job = GlobalIngestionJob(
                        id=job_id,
                        dataset_id=DATASET_UUID,
                        snapshot_hash=snapshot_hash,
                        state="archiving",
                        staging_schema="pbdb_stage_" + job_id.hex,
                        checkpoint={"purpose": "conversion"},
                        metrics={},
                    )
                    session.add(job)
                    session.flush()
                cp = cast(dict[str, Any], dict(job.checkpoint))
                metrics = cast(dict[str, Any], dict(job.metrics))
                ready = job.state == "ready"
            if ready:
                manifest = verify_archive(store, cp["archive_manifest"])
                return {"status": "ready", "exact_replay": True, "counts": manifest["counts"]}
            if "archive_manifest" not in cp:
                notify("before_archive")
                original, _ = archive_snapshot(snapshot_path, store)
                manifest = verify_archive(store, original)
                chunks = []
                for metadata, _ in raw_chunks(store, raw_records(engine, store)):
                    chunks.append(metadata)
                    notify("archive_batch")
                manifest = {
                    **manifest,
                    "files": [*manifest["files"], *chunks],
                    "counts": {
                        **manifest["counts"],
                        "raw_revisions": sum(f["records"] for f in chunks),
                    },
                    "migration": {"version": "0013_design_c", "operation": "legacy-conversion"},
                }
                cp["archive_manifest"] = publish_manifest(store, manifest)
                checkpoint_job(engine, job_id, "staging", cp, metrics)
                notify("after_archive_before_verify")
            manifest = verify_archive(store, cp["archive_manifest"])
            with Session(engine) as session, session.begin():
                archive_id = register_archive(session, store, cp["archive_manifest"])
                session.execute(
                    text("UPDATE global_ingestion_job SET archive_id=:a WHERE id=:id"),
                    {"a": archive_id, "id": job_id},
                )
            count = backfill_archive(engine, store, archive_id, manifest, notify)
            with engine.connect() as c:
                actual = c.scalar(
                    text("""SELECT count(*) FROM source_record_revision r
                  JOIN source_record s ON s.id=r.source_record_id WHERE s.source_dataset_id=:d"""),
                    {"d": DATASET_UUID},
                )
            if count != actual:
                raise ArchiveError("Conversion archive is not a complete revision population")
            # Prove every retained scientific frame before any duplicate raw
            # encoding is removed. A bad legacy hash leaves its hot evidence intact.
            validation_cursor = 0
            with Session(engine) as session:
                while True:
                    validation_nodes = list(
                        session.scalars(
                            select(NormalizedSourceRevision)
                            .where(
                                NormalizedSourceRevision.normalization_key > validation_cursor,
                                NormalizedSourceRevision.source_record_id.in_(
                                    select(SourceRecord.id).where(
                                        SourceRecord.source_dataset_id == DATASET_UUID
                                    )
                                ),
                            )
                            .order_by(NormalizedSourceRevision.normalization_key)
                            .limit(BATCH)
                        )
                    )
                    if not validation_nodes:
                        break
                    for node in validation_nodes:
                        reconstructed_payload(session, node)
                    validation_cursor = validation_nodes[-1].normalization_key
            cp["normalization_verified"] = validation_cursor
            checkpoint_job(engine, job_id, "validated", cp, metrics)
            notify("before_raw_removal")
            # Every raw locator above was reconstructed and hash-verified before
            # these bounded transactions remove duplicate encodings.
            with engine.begin() as c:
                c.execute(
                    text("""UPDATE source_record_revision r SET raw_payload=NULL
                  FROM source_record s WHERE r.source_record_id=s.id
                    AND s.source_dataset_id=:d AND r.archive_object_id IS NOT NULL"""),
                    {"d": DATASET_UUID},
                )
                c.execute(
                    text("UPDATE source_record SET raw_payload=NULL WHERE source_dataset_id=:d"),
                    {"d": DATASET_UUID},
                )
            cursor = int(cp.get("proof_cursor", 0))
            while True:
                with Session(engine) as session, session.begin():
                    nodes = list(
                        session.scalars(
                            select(NormalizedSourceRevision)
                            .where(
                                NormalizedSourceRevision.normalization_key > cursor,
                                NormalizedSourceRevision.source_record_id.in_(
                                    select(SourceRecord.id).where(
                                        SourceRecord.source_dataset_id == DATASET_UUID
                                    )
                                ),
                            )
                            .order_by(NormalizedSourceRevision.normalization_key)
                            .limit(BATCH)
                        )
                    )
                    if not nodes:
                        break
                    for node in nodes:
                        reconstructed_payload(session, node)
                    keys = [n.normalization_key for n in nodes]
                    session.execute(
                        text("""INSERT INTO source_proof_edge
                      SELECT n.normalization_key,r.revision_key FROM source_record_dependency d
                      JOIN normalized_source_revision n
                        USING(source_record_id,content_hash,normalization_hash)
                      JOIN source_record_revision r ON r.source_record_id=d.dependency_record_id
                        AND r.content_hash=d.dependency_content_hash
                      WHERE n.normalization_key=ANY(:keys) ON CONFLICT DO NOTHING"""),
                        {"keys": keys},
                    )
                    mismatch = session.scalar(
                        text("""SELECT count(*) FROM (
                      (SELECT n.normalization_key,r.revision_key FROM source_record_dependency d
                        JOIN normalized_source_revision n
                          USING(source_record_id,content_hash,normalization_hash)
                        JOIN source_record_revision r ON r.source_record_id=d.dependency_record_id
                          AND r.content_hash=d.dependency_content_hash
                        WHERE n.normalization_key=ANY(:keys)
                       EXCEPT SELECT * FROM source_proof_edge WHERE normalization_key=ANY(:keys))
                      UNION ALL
                      (SELECT * FROM source_proof_edge WHERE normalization_key=ANY(:keys)
                       EXCEPT SELECT n.normalization_key,r.revision_key
                        FROM source_record_dependency d
                        JOIN normalized_source_revision n
                          USING(source_record_id,content_hash,normalization_hash)
                        JOIN source_record_revision r ON r.source_record_id=d.dependency_record_id
                          AND r.content_hash=d.dependency_content_hash
                        WHERE n.normalization_key=ANY(:keys) AND n.frame_format='full')
                    ) missing"""),
                        {"keys": [n.normalization_key for n in nodes if n.frame_format == "full"]},
                    )
                    if mismatch:
                        raise ArchiveError("Compact proof differs from complete legacy proof")
                    for node in nodes:
                        node.payload = {
                            k: v for k, v in node.payload.items() if k != "dependencies"
                        }
                        node.frame_format = "compact"
                    session.flush()
                    for node in nodes:
                        reconstructed_payload(session, node)
                    session.execute(
                        text("""DELETE FROM source_record_dependency d
                      USING normalized_source_revision n WHERE n.normalization_key=ANY(:keys)
                        AND d.source_record_id=n.source_record_id AND d.content_hash=n.content_hash
                        AND d.normalization_hash=n.normalization_hash"""),
                        {"keys": keys},
                    )
                    cursor = nodes[-1].normalization_key
                    cp["proof_cursor"] = cursor
                    session.execute(
                        text(
                            "UPDATE global_ingestion_job SET checkpoint=CAST(:cp AS jsonb) "
                            "WHERE id=:id"
                        ),
                        {"cp": json.dumps(cp), "id": job_id},
                    )
                notify("proof_batch")
            notify("before_conversion_ready")
            metrics = {"archived_revisions": count, "conversion": "hash-and-proof-verified"}
            checkpoint_job(engine, job_id, "ready", cp, metrics)
            return {"status": "ready", **metrics}
        except Exception as error:
            with engine.begin() as c:
                c.execute(
                    text("UPDATE global_ingestion_job SET state='failed',error=:e WHERE id=:id"),
                    {"id": job_id, "e": f"{type(error).__name__}: {error}"[:2000]},
                )
            raise
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(74003001)"))


def restore_legacy(engine: Engine, store: ArchiveStore) -> dict[str, int]:
    """Automated bounded rehydration prerequisite for an Alembic downgrade.

    Each original raw and normalization hash is verified before its hot encoding
    is restored. Failures leave already rehydrated batches valid and resumable.
    """
    target_guard(engine, {"scope": {}}, None)
    raw_count, normalized_count = 0, 0
    with engine.connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(74003001)"))
        try:
            # Read each compressed raw object once, rather than reopening and
            # inflating a 1000-record object separately for each restored row.
            with Session(engine) as metadata:
                objects = metadata.scalars(
                    select(SourceArchiveObject)
                    .where(
                        SourceArchiveObject.id.in_(
                            select(SourceRecordRevision.archive_object_id).where(
                                SourceRecordRevision.raw_payload.is_(None)
                            )
                        )
                    )
                    .order_by(SourceArchiveObject.id),
                    execution_options={"yield_per": BATCH},
                ).yield_per(BATCH)
                last_archive = None
                for obj in objects:
                    if obj.archive_id != last_archive:
                        archive = metadata.get(SourceArchive, obj.archive_id)
                        if archive is None or archive.state != "ready":
                            raise ArchiveError("Legacy restore requires READY archive metadata")
                        verify_archive(store, archive.manifest_hash)
                        last_archive = obj.archive_id
                    lines = read_object(store, object_metadata(obj)).splitlines()
                    if len(lines) != obj.record_count:
                        raise ArchiveError("Legacy restore archive count differs")
                    ordinal = -1
                    while True:
                        with Session(engine) as session, session.begin():
                            revisions = list(
                                session.scalars(
                                    select(SourceRecordRevision)
                                    .where(
                                        SourceRecordRevision.archive_object_id == obj.id,
                                        SourceRecordRevision.archive_row > ordinal,
                                        SourceRecordRevision.raw_payload.is_(None),
                                    )
                                    .order_by(SourceRecordRevision.archive_row)
                                    .limit(BATCH)
                                )
                            )
                            if not revisions:
                                break
                            for revision in revisions:
                                row_number = revision.archive_row
                                if row_number is None or not 0 <= row_number < len(lines):
                                    raise ArchiveError("Legacy restore has invalid row locator")
                                row = json.loads(lines[row_number])
                                if (
                                    row["source_record_id"] != str(revision.source_record_id)
                                    or row["content_hash"] != revision.content_hash
                                    or digest(row["raw"]) != revision.content_hash
                                ):
                                    raise ArchiveError("Legacy restore raw identity/hash differs")
                                revision.raw_payload = row["raw"]
                            session.flush()
                            session.execute(
                                text("""UPDATE source_record s SET raw_payload=r.raw_payload
                              FROM source_record_revision r WHERE r.revision_key=ANY(:keys)
                                AND s.id=r.source_record_id AND s.content_hash=r.content_hash"""),
                                {"keys": [r.revision_key for r in revisions]},
                            )
                            raw_count += len(revisions)
                            ordinal = int(revisions[-1].archive_row or 0)
            cursor = 0
            while True:
                with Session(engine) as session, session.begin():
                    nodes = list(
                        session.scalars(
                            select(NormalizedSourceRevision)
                            .where(
                                NormalizedSourceRevision.normalization_key > cursor,
                                NormalizedSourceRevision.frame_format == "compact",
                            )
                            .order_by(NormalizedSourceRevision.normalization_key)
                            .limit(BATCH)
                        )
                    )
                    if not nodes:
                        break
                    for node in nodes:
                        node.payload = reconstructed_payload(session, node)
                    keys = [n.normalization_key for n in nodes]
                    session.execute(
                        text("""INSERT INTO source_record_dependency
                      SELECT n.source_record_id,n.content_hash,n.normalization_hash,
                             r.source_record_id,r.content_hash FROM source_proof_edge e
                      JOIN normalized_source_revision n USING(normalization_key)
                      JOIN source_record_revision r USING(revision_key)
                      WHERE e.normalization_key=ANY(:keys) ON CONFLICT DO NOTHING"""),
                        {"keys": keys},
                    )
                    for node in nodes:
                        node.frame_format = "full"
                    session.flush()
                    for node in nodes:
                        reconstructed_payload(session, node)
                    session.execute(
                        text("DELETE FROM source_proof_edge WHERE normalization_key=ANY(:keys)"),
                        {"keys": keys},
                    )
                    normalized_count += len(nodes)
                    cursor = nodes[-1].normalization_key
            with engine.begin() as c:
                c.execute(
                    text("""UPDATE global_ingestion_job
                  SET state='failed',checkpoint=checkpoint-'proof_cursor',
                      error='Legacy rehydration completed; compact conversion must be replayed'
                  WHERE checkpoint->>'purpose'='conversion'""")
                )
            return {"rehydrated_raw": raw_count, "rehydrated_normalizations": normalized_count}
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(74003001)"))
