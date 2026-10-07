"""Transactional archive metadata and raw-revision audit through an injected store."""

import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ingestion.archive import (
    ArchiveError,
    ArchiveStore,
    canonical_bytes,
    read_object,
    read_raw,
    sha,
    verify_archive,
)
from app.ingestion.pbdb import digest, stable_id
from app.models import SourceArchive, SourceArchiveObject, SourceRecordRevision


def register_archive(session: Session, store: ArchiveStore, manifest_hash: str) -> UUID:
    manifest = verify_archive(store, manifest_hash)
    archive_id = stable_id("source-archive", manifest_hash)
    existing = session.get(SourceArchive, archive_id)
    if existing is not None:
        if existing.state != "ready" or existing.manifest_hash != manifest_hash:
            raise ArchiveError("Existing archive metadata is incomplete or inconsistent")
        return archive_id
    objects = {f["hash"]: f for f in manifest["files"]}
    sizes = {h: f["bytes"] for h, f in objects.items()}
    for entry in manifest["files"]:
        if entry["kind"] == "provider-index":
            for line in read_object(store, entry).splitlines():
                obj = json.loads(line)["object"]
                sizes[obj["hash"]] = obj["bytes"]
    session.execute(
        insert(SourceArchive).values(
            id=archive_id,
            provider=manifest["provider"],
            snapshot_hash=manifest["snapshot_hash"],
            manifest_hash=manifest_hash,
            retrieved_at=datetime.fromisoformat(manifest["retrieved_at"]),
            scope=manifest["scope"],
            adapter_version=manifest["adapter_version"],
            policy_version=manifest["policy_version"],
            rights=manifest["rights"],
            storage_reference=store.reference,
            compression="gzip",
            byte_size=sum(sizes.values()),
            state="writing",
            manifest=manifest,
        )
    )
    for entry in objects.values():
        session.execute(
            insert(SourceArchiveObject).values(
                archive_id=archive_id,
                object_hash=entry["hash"],
                original_hash=entry["original_hash"],
                compressed_bytes=entry["bytes"],
                original_bytes=entry["original_bytes"],
                record_count=entry["records"],
                kind=entry["kind"],
            )
        )
    session.execute(
        text("UPDATE source_archive SET state='verifying' WHERE id=:id"), {"id": archive_id}
    )
    # No scientific source revision can reference WRITING/VERIFYING via the DDL guard.
    verify_archive(store, manifest_hash)
    session.execute(
        text("UPDATE source_archive SET state='ready' WHERE id=:id"), {"id": archive_id}
    )
    return archive_id


def object_metadata(row: Any) -> dict[str, Any]:
    return {
        "hash": row.object_hash,
        "original_hash": row.original_hash,
        "bytes": row.compressed_bytes,
        "original_bytes": row.original_bytes,
        "records": row.record_count,
        "kind": row.kind,
        "compression": "gzip",
    }


def raw_revision(
    session: Session, store: ArchiveStore, source_record_id: UUID, content_hash: str
) -> dict[str, Any]:
    revision = session.get(SourceRecordRevision, (source_record_id, content_hash))
    if revision is None:
        raise ArchiveError("Unknown retained source revision")
    if revision.raw_payload is not None:
        if digest(revision.raw_payload) != content_hash:
            raise ArchiveError("Hot raw revision hash mismatch")
        return cast(dict[str, Any], revision.raw_payload)
    obj = session.get(SourceArchiveObject, revision.archive_object_id)
    if obj is None:
        raise ArchiveError("Missing archived raw evidence locator")
    archive = session.get(SourceArchive, obj.archive_id)
    if archive is None or archive.state != "ready":
        raise ArchiveError("Raw archive is not READY")
    # Verify the pinned marker and manifest before trusting database locators.
    if (
        store.get(f"{archive.manifest_hash}.ready")
        != canonical_bytes({"manifest_hash": archive.manifest_hash})
        or sha(store.get(f"{archive.manifest_hash}.manifest")) != archive.manifest_hash
    ):
        raise ArchiveError("Archive manifest integrity failed")
    if revision.archive_row is None:
        raise ArchiveError("Raw evidence locator has no row ordinal")
    return read_raw(
        store, object_metadata(obj), revision.archive_row, str(source_record_id), content_hash
    )


def audit_archives(session: Session, store: ArchiveStore) -> dict[str, Any]:
    failures = []
    verified = 0
    for archive in session.scalars(select(SourceArchive), execution_options={"yield_per": 1}):
        try:
            if archive.state != "ready":
                raise ArchiveError("Archive publication is not READY")
            manifest = verify_archive(store, archive.manifest_hash)
            if manifest != archive.manifest:
                raise ArchiveError("PostgreSQL/owned archive manifest mismatch")
            verified += 1
        except ArchiveError as error:
            failures.append({"archive_id": str(archive.id), "error": str(error)})
    return {
        "status": "verified" if not failures else "failed",
        "verified": verified,
        "failures": failures,
    }


def audit_raw_revisions(session: Session, store: ArchiveStore) -> dict[str, int]:
    """Hash every retained raw revision with one bounded object buffer."""
    hot, cold = 0, 0
    for revision in session.scalars(
        select(SourceRecordRevision).where(SourceRecordRevision.raw_payload.is_not(None)),
        execution_options={"yield_per": 256},
    ).yield_per(256):
        if digest(revision.raw_payload) != revision.content_hash:
            raise ArchiveError("Hot retained raw revision hash differs")
        hot += 1
    objects = session.scalars(
        select(SourceArchiveObject)
        .where(
            SourceArchiveObject.id.in_(
                select(SourceRecordRevision.archive_object_id).where(
                    SourceRecordRevision.raw_payload.is_(None)
                )
            )
        )
        .order_by(SourceArchiveObject.id),
        execution_options={"yield_per": 256},
    ).yield_per(256)
    for obj in objects:
        archive = session.get(SourceArchive, obj.archive_id)
        if archive is None or archive.state != "ready":
            raise ArchiveError("Cold raw revision archive is not READY")
        lines = read_object(store, object_metadata(obj)).splitlines()
        if len(lines) != obj.record_count:
            raise ArchiveError("Cold raw archive row count differs")
        for revision in session.scalars(
            select(SourceRecordRevision).where(
                SourceRecordRevision.archive_object_id == obj.id,
                SourceRecordRevision.raw_payload.is_(None),
            ),
            execution_options={"yield_per": 256},
        ).yield_per(256):
            ordinal = revision.archive_row
            if ordinal is None or not 0 <= ordinal < len(lines):
                raise ArchiveError("Cold raw archive ordinal is invalid")
            row = json.loads(lines[ordinal])
            if (
                row["source_record_id"] != str(revision.source_record_id)
                or row["content_hash"] != revision.content_hash
                or digest(row["raw"]) != revision.content_hash
            ):
                raise ArchiveError("Cold raw retained identity/hash differs")
            cold += 1
    expected = int(session.scalar(text("SELECT count(*) FROM source_record_revision")) or 0)
    if hot + cold != expected:
        raise ArchiveError("Raw audit did not cover the complete revision population")
    return {"verified_hot": hot, "verified_cold": cold, "verified_total": expected}


def audit_normalizations(session: Session) -> dict[str, int]:
    """Reconstruct and hash every retained PBDB normalization, including history.

    Server-side fetching and a bounded lateral proof frame prevent whole-corpus
    payload/proof buffering. The extra edge detects an unsupported fanout.
    """
    session.execute(text("SET LOCAL jit=off"))
    query = text("""SELECT n.adapter_version,n.normalization_hash,n.payload,n.frame_format,
      coalesce(f.dependencies,'[]'::jsonb) dependencies
      FROM normalized_source_revision n
      LEFT JOIN LATERAL (
        SELECT jsonb_agg(jsonb_build_array(d.source_record_id::text,d.content_hash)
          ORDER BY d.source_record_id,d.content_hash) dependencies
        FROM (SELECT r.source_record_id,r.content_hash FROM source_proof_edge e
          JOIN source_record_revision r USING(revision_key)
          WHERE n.frame_format='compact' AND e.normalization_key=n.normalization_key
          ORDER BY r.source_record_id,r.content_hash LIMIT 50001) d
      ) f ON true
      WHERE EXISTS(SELECT 1 FROM source_record s JOIN source_dataset ds
        ON ds.id=s.source_dataset_id WHERE s.id=n.source_record_id
          AND ds.external_dataset_id='pbdb:public:florida:v1')
      ORDER BY n.normalization_key""")
    count = 0
    for row in session.execute(query, execution_options={"yield_per": 256}):
        payload = row.payload
        if row.frame_format == "compact":
            if len(row.dependencies) > 50000:
                raise ArchiveError("Retained normalization exceeds complete proof fanout bound")
            payload = {**payload, "dependencies": row.dependencies}
        if digest({"adapter": row.adapter_version, "payload": payload}) != row.normalization_hash:
            raise ArchiveError("Retained normalization hash differs from its complete proof frame")
        count += 1
    return {"verified_normalizations": count}


def archive_objects(session: Session, archive_id: UUID) -> dict[str, int]:
    return {
        row.object_hash: row.id
        for row in session.scalars(
            select(SourceArchiveObject).where(SourceArchiveObject.archive_id == archive_id)
        )
    }
