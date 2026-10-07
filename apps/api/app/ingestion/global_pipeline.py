"""Archive-first, bounded, resumable PBDB ingestion with one atomic read revision.

Only completed staging enters scientific tables. PostgreSQL COPY + set-based
publication preserve all original identities and full flattened version proofs.
No network acquisition, mapping, cloud credentials or archive garbage collection.
"""

import hashlib
import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb
from sqlalchemy import CursorResult, Engine, Table, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from app.db import Base
from app.discovery.occurrence_browse import rebuild as rebuild_members
from app.discovery.pbdb import inspect_occurrence, occurrence_catalog
from app.discovery.pbdb import rebuild as rebuild_catalog
from app.discovery.schemas import ContextQuery
from app.ingestion.archive import (
    ArchiveError,
    ArchiveStore,
    publish_manifest,
    raw_chunks,
    verify_archive,
)
from app.ingestion.archive_db import archive_objects, register_archive
from app.ingestion.global_staging import DiskStage, archive_snapshot
from app.ingestion.import_pbdb import DATASET_UUID, SOURCE_UUID, build_rows
from app.ingestion.metrics import memory_bytes
from app.ingestion.pbdb import (
    ADAPTER_VERSION,
    DATASET,
    PROVIDER,
    SERVICE,
    IdentificationRecord,
    OccurrenceRecord,
    digest,
    stable_id,
)
from app.models import (
    CollectionEvent,
    CollectionReferenceEvidence,
    GlobalIngestionJob,
    IdentificationEvidence,
    IngestionRun,
    Locality,
    MaterialEvidence,
    NormalizedSourceRevision,
    Occurrence,
    OpinionReferenceEvidence,
    ProviderAgeEvidence,
    ResearchReference,
    Source,
    SourceArchive,
    SourceDataset,
    SourceNormalizationCurrent,
    SourceRecord,
    SourceRecordRevision,
    Taxon,
    event_evidence,
    locality_evidence,
    occurrence_evidence,
    taxon_evidence,
)

TABLES: dict[str, Table] = {
    "source": cast(Table, SourceRecord.__table__),
    "revision": cast(Table, SourceRecordRevision.__table__),
    "normalized": cast(Table, NormalizedSourceRevision.__table__),
    "current": cast(Table, SourceNormalizationCurrent.__table__),
    "reference": cast(Table, ResearchReference.__table__),
    "locality": cast(Table, Locality.__table__),
    "event": cast(Table, CollectionEvent.__table__),
    "taxon": cast(Table, Taxon.__table__),
    "occurrence": cast(Table, Occurrence.__table__),
    "provider_age": cast(Table, ProviderAgeEvidence.__table__),
    "identification": cast(Table, IdentificationEvidence.__table__),
    "material": cast(Table, MaterialEvidence.__table__),
    "collection_reference": cast(Table, CollectionReferenceEvidence.__table__),
    "opinion_reference": cast(Table, OpinionReferenceEvidence.__table__),
    "taxon_link": taxon_evidence,
    "locality_link": locality_evidence,
    "event_link": event_evidence,
    "occurrence_link": occurrence_evidence,
}
ORDER = (
    "source",
    "revision",
    "reference",
    "locality",
    "event",
    "taxon",
    "occurrence",
    "normalized",
    "provider_age",
    "identification",
    "material",
    "collection_reference",
    "opinion_reference",
    "taxon_link",
    "locality_link",
    "event_link",
    "occurrence_link",
)
IMMUTABLE = {
    "revision",
    "normalized",
    "provider_age",
    "identification",
    "material",
    "collection_reference",
    "opinion_reference",
    "taxon_link",
    "locality_link",
    "event_link",
    "occurrence_link",
}
SCHEMA = re.compile(r"pbdb_stage_[0-9a-f]{32}\Z")


def observe_memory(metrics: dict[str, Any]) -> None:
    # Constant retained memory independent of the number of ingested batches.
    sample = metrics.setdefault("memory", {"samples": 0, "rss_sum": 0, "peak_rss_bytes": 0})
    sample["samples"] += 1
    sample["rss_sum"] += memory_bytes(peak=False)
    sample["peak_rss_bytes"] = max(sample["peak_rss_bytes"], memory_bytes())
    sample["average_rss_bytes"] = sample["rss_sum"] // sample["samples"]


def checkpoint_fingerprints(engine: Engine) -> dict[str, dict[str, Any]]:
    """Bounded, complete row evidence for the future normal-target checkpoint.

    Both backup/restore and the still-current target must match. A receipt with
    omitted tables or empty UFVP digests is not a restore proof.
    """
    result: dict[str, dict[str, Any]] = {}
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        for name, table in sorted(Base.metadata.tables.items()):
            columns = ",".join(f'"{column.name}"' for column in table.columns)
            order = ",".join(f'"{column.name}"' for column in table.primary_key)
            checksum = hashlib.sha256()
            rows = 0
            query = text(
                f"SELECT row_to_json(q)::text FROM "
                f'(SELECT {columns} FROM "{name}" ORDER BY {order}) q'
            )
            for row in (
                connection.execution_options(stream_results=True).execute(query).yield_per(256)
            ):
                checksum.update(row[0].encode("utf8"))
                checksum.update(b"\n")
                rows += 1
            result[name] = {"rows": rows, "sha256": checksum.hexdigest()}
    return result


def target_guard(engine: Engine, header: dict[str, Any], checkpoint: Path | None) -> None:
    url = engine.url
    disposable = {
        ("paleograph_test", 55432),
        ("paleograph_browser", 56432),
        ("paleograph_pbdb_canary", 58432),
        ("paleograph_phase5b1", 62432),
        ("paleograph_phase5b1_pilot", 63432),
    }
    if url.host not in {"localhost", "127.0.0.1"} or url.username != url.database:
        raise ValueError("Unsupported PBDB ingestion target")
    if (url.database, url.port) in disposable:
        return
    restore_prefix = {
        62432: "paleograph_phase5b1_restore_",
        63432: "paleograph_phase5b1_pilot_restore_",
    }.get(url.port or 0)
    if restore_prefix and re.fullmatch(restore_prefix + r"[0-9a-f]{8}", url.database or ""):
        return
    if url.database != "paleograph" or url.port != 5432 or checkpoint is None:
        raise ValueError("Normal global ingestion requires a restore-verified pre-5B2 checkpoint")
    if header["scope"].get("mode") != "global" or header["scope"].get("test_only"):
        raise ValueError("Normal target requires real complete global scope, never a pilot")
    evidence = json.loads(checkpoint.read_bytes())
    baseline = evidence.get("baseline", {})
    restored = evidence.get("restore", {})
    ufvp = baseline.get("ufvp_digests", {})
    full_rows = baseline.get("full_rows", {})
    ufvp_keys = {"source", "interpretation", "catalog_science", "locality_summary", "taxon_summary"}
    if (
        evidence.get("label") != "pre-5b2"
        or evidence.get("status") != "verified"
        or evidence.get("approved_snapshot_hash") != digest(header)
        or baseline.get("migration") != "0014_design_c_native_cache"
        or restored.get("migration") != "0014_design_c_native_cache"
        or not isinstance(ufvp, dict)
        or set(ufvp) != ufvp_keys
        or any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value)
            for value in ufvp.values()
        )
        or ufvp != restored.get("ufvp_digests")
        or not isinstance(full_rows, dict)
        or set(full_rows) != set(Base.metadata.tables)
        or any(
            not isinstance(value, dict)
            or not isinstance(value.get("rows"), int)
            or value["rows"] < 0
            or not isinstance(value.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
            for value in full_rows.values()
        )
        or full_rows != restored.get("full_rows")
    ):
        raise ValueError("Global checkpoint does not prove pinned restore/scientific equivalence")
    with Path(evidence["path"]).open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != evidence["sha256"]:
            raise ValueError("Pre-5B2 checkpoint bytes changed")
    if checkpoint_fingerprints(engine) != full_rows:
        raise ValueError("Normal target changed since its restore-verified checkpoint")
    # Retained cold evidence requires the checkpoint's coupled archive inventory.
    inventory = evidence.get("archive_files")
    if not isinstance(inventory, dict) or (full_rows["source_archive"]["rows"] and not inventory):
        raise ValueError("Pre-5B2 checkpoint requires a verified coupled archive inventory")
    archive_root = Path(evidence["archive_root"]).resolve() if inventory else None
    for key, expected in inventory.items():
        if not re.fullmatch(r"[0-9a-f]{64}\.(?:gz|manifest|ready)", key):
            raise ValueError("Invalid checkpoint archive key")
        assert archive_root is not None
        with (archive_root / key).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError("Pre-5B2 checkpoint archive bytes changed")
    # Explicit future permit only. Phase 5B1 runners never construct/pass one.


def schema_name(name: str) -> str:
    if not SCHEMA.fullmatch(name):
        raise ValueError("Invalid private PBDB staging schema")
    return name


def checkpoint_job(
    engine: Engine, job_id: UUID, state: str, checkpoint: dict[str, Any], metrics: dict[str, Any]
) -> None:
    with engine.begin() as c:
        c.execute(
            text("""UPDATE global_ingestion_job SET state=:state,checkpoint=CAST(:cp AS jsonb),
          metrics=CAST(:metrics AS jsonb),updated_at=now(),error=NULL WHERE id=:id"""),
            {
                "id": job_id,
                "state": state,
                "cp": json.dumps(checkpoint),
                "metrics": json.dumps(metrics),
            },
        )


def create_staging(engine: Engine, schema: str) -> None:
    schema = schema_name(schema)
    with engine.begin() as c:
        c.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        for table in TABLES.values():
            c.execute(
                text(f"""CREATE TABLE IF NOT EXISTS {schema}.{table.name}
              (LIKE public.{table.name} INCLUDING DEFAULTS
               INCLUDING IDENTITY INCLUDING GENERATED)""")
            )
            keys = ",".join(col.name for col in table.primary_key)
            # Staging has no scientific FKs; primary-key indexes make checkpoint
            # replay conflicts explicit and final set-based joins deterministic.
            c.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS stage_{table.name}_pk "
                    f"ON {schema}.{table.name}({keys})"
                )
            )
        c.execute(
            text(f"""CREATE TABLE IF NOT EXISTS {schema}.proof
          (normalization_key bigint NOT NULL,revision_key bigint NOT NULL)""")
        )


def copy_rows(connection: Any, schema: str, table: Table, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    names = list(rows[0])
    json_names = {col.name for col in table.columns if isinstance(col.type, JSONB)}
    with connection.cursor().copy(
        f"COPY {schema}.{table.name}({','.join(names)}) FROM STDIN"
    ) as copy:
        for row in rows:
            copy.write_row(
                tuple(
                    Jsonb(row[n]) if n in json_names and row[n] is not None else row[n]
                    for n in names
                )
            )


def occurrence_from_stage(stage: DiskStage, external: str) -> OccurrenceRecord:
    row = stage.db.execute("SELECT raw FROM occurrence WHERE external=?", (external,)).fetchone()
    if row is None:
        raise ArchiveError("Missing staged occurrence history")
    data = json.loads(row[0])
    return OccurrenceRecord(
        data["id"],
        data["collection_id"],
        tuple(IdentificationRecord(**i) for i in data["identifications"]),
        data["complete_history"],
    )


def stage_postgres(
    engine: Engine,
    stage: DiskStage,
    store: ArchiveStore,
    archive_id: UUID,
    job: GlobalIngestionJob,
    cp: dict[str, Any],
    metrics: dict[str, Any],
    batch_size: int,
    hook: Callable[[str], None],
) -> None:
    schema = schema_name(job.staging_schema)
    create_staging(engine, schema)
    with Session(engine) as s:
        objects = archive_objects(s, archive_id)
    cursor = int(cp.get("postgres_cursor", 0))
    while batch := stage.db.execute(
        "SELECT * FROM record WHERE k>? ORDER BY k LIMIT ?", (cursor, batch_size)
    ).fetchall():
        records = {
            (r["kind"], r["external"]): {
                "raw": json.loads(r["raw"]),
                "normalized": json.loads(r["evidence"]),
                "hash": r["hash"],
            }
            for r in batch
        }
        occurrences = [
            occurrence_from_stage(stage, r["external"]) for r in batch if r["kind"] == "occurrence"
        ]
        rows = build_rows(records, {k: set() for k in records}, occurrences, job.id, job.created_at)
        normalized_by_id = {str(r["source_record_id"]): r for r in rows["normalized"]}
        revisions_by_id = {str(r["source_record_id"]): r for r in rows["revision"]}
        for source in rows["source"]:
            source["raw_payload"] = None
        for r in batch:
            n = normalized_by_id[r["source_id"]]
            verified = stage.verified_normalization(r)
            n["payload"].pop("dependencies")
            if n["payload"] != {
                key: value for key, value in verified.items() if key != "dependencies"
            }:
                raise ArchiveError("Bulk canonical assembler changed original normalization bytes")
            n["normalization_hash"] = r["normalization_hash"]
            n["normalization_key"] = r["k"]
            n["frame_format"] = "compact"
            raw = revisions_by_id[r["source_id"]]
            locator = stage.db.execute(
                "SELECT object_hash,ordinal FROM locator WHERE source_id=? AND hash=?",
                (r["source_id"], r["hash"]),
            ).fetchone()
            if locator is None:
                raise ArchiveError("No verified archived revision locator")
            raw.update(
                raw_payload=None,
                revision_key=r["k"],
                archive_object_id=objects[locator[0]],
                archive_row=locator[1],
            )
        for current in rows["current"]:
            current["normalization_hash"] = normalized_by_id[str(current["source_record_id"])][
                "normalization_hash"
            ]
        with engine.begin() as c:
            raw_connection = c.connection.driver_connection
            if raw_connection is None:
                raise RuntimeError("Missing PostgreSQL driver connection")
            for name, table in TABLES.items():
                copy_rows(raw_connection, schema, table, rows[name])
            keys = [r["k"] for r in batch]
            placeholders = ",".join("?" for _ in keys)
            with raw_connection.cursor().copy(f"COPY {schema}.proof FROM STDIN") as copy:
                for pair in stage.db.execute(
                    f"SELECT owner,target FROM proof WHERE owner IN ({placeholders})", keys
                ):
                    copy.write_row(tuple(pair))
            cursor = batch[-1]["k"]
            cp["postgres_cursor"] = cursor
            c.execute(
                text("""UPDATE global_ingestion_job SET checkpoint=CAST(:cp AS jsonb),
              updated_at=now() WHERE id=:id"""),
                {"cp": json.dumps(cp), "id": job.id},
            )
        observe_memory(metrics)
        hook("postgres_batch")


def merge_table(session: Session, schema: str, name: str) -> int:
    table = TABLES[name]
    keys = [col.name for col in table.primary_key]
    names = [col.name for col in table.columns if col.computed is None and col.identity is None]
    columns = ",".join(names)
    conflict = ",".join(keys)
    if name in IMMUTABLE:
        action = "DO NOTHING"
    else:
        update = [n for n in names if n not in {*keys, "created_at", "first_seen_at"}]
        changed = [
            n
            for n in update
            if n not in {"updated_at", "last_seen_at", "ingested_at", "ingestion_run_id"}
        ]
        set_sql = ",".join(f"{n}=excluded.{n}" for n in update)
        condition = " OR ".join(
            f"public.{table.name}.{n} IS DISTINCT FROM excluded.{n}" for n in changed
        )
        action = f"DO UPDATE SET {set_sql} WHERE {condition}"
    result = session.execute(
        text(f"""INSERT INTO public.{table.name}({columns})
      SELECT {columns} FROM {schema}.{table.name} WHERE true ON CONFLICT({conflict}) {action}""")
    )
    return int(cast(CursorResult[Any], result).rowcount)


def publish_staged(
    engine: Engine,
    store: ArchiveStore,
    job: GlobalIngestionJob,
    archive_id: UUID,
    header: dict[str, Any],
    counts: dict[str, int],
    metrics: dict[str, Any],
    hook: Callable[[str], None],
) -> dict[str, Any]:
    schema = schema_name(job.staging_schema)
    publication_started = time.perf_counter()
    with Session(engine) as session, session.begin():
        archive = session.get(SourceArchive, archive_id)
        if archive is None or archive.state != "ready":
            raise ArchiveError("Publication archive is not READY")
        verify_archive(store, archive.manifest_hash)
        session.execute(text("SELECT pg_advisory_xact_lock(74003001)"))
        session.execute(text("SET LOCAL jit=off"))
        session.execute(text("SET LOCAL work_mem='64MB'"))
        inserted = int(
            session.scalar(
                text(f"""SELECT count(*) FROM {schema}.source_record s
          LEFT JOIN public.source_record r ON r.id=s.id WHERE r.id IS NULL""")
            )
            or 0
        )
        mutations = {name: merge_table(session, schema, name) for name in ORDER}
        session.execute(
            text(f"""CREATE TABLE {schema}.keymap AS
          SELECT sn.normalization_key stage_key,n.normalization_key,r.revision_key
          FROM {schema}.normalized_source_revision sn
          JOIN normalized_source_revision n USING(source_record_id,content_hash,normalization_hash)
          JOIN source_record_revision r USING(source_record_id,content_hash)""")
        )
        session.execute(text(f"CREATE UNIQUE INDEX stage_keymap_pk ON {schema}.keymap(stage_key)"))
        mapped = int(session.scalar(text(f"SELECT count(*) FROM {schema}.keymap")) or 0)
        if mapped != sum(counts.values()):
            raise ArchiveError("Staging source/revision key mapping is incomplete")
        dangling = session.scalar(
            text(f"""SELECT count(*) FROM {schema}.proof e
          LEFT JOIN {schema}.keymap owner ON owner.stage_key=e.normalization_key
          LEFT JOIN {schema}.keymap target ON target.stage_key=e.revision_key
          WHERE owner.stage_key IS NULL OR target.stage_key IS NULL""")
        )
        if dangling:
            raise ArchiveError("Staging contains an unmapped proof endpoint")
        result = session.execute(
            text(f"""INSERT INTO source_proof_edge
          SELECT owner.normalization_key,target.revision_key FROM {schema}.proof e
          JOIN {schema}.keymap owner ON owner.stage_key=e.normalization_key
          JOIN {schema}.keymap target ON target.stage_key=e.revision_key ON CONFLICT DO NOTHING""")
        )
        mutations["proof"] = int(cast(CursorResult[Any], result).rowcount)
        missing = session.scalar(
            text(f"""SELECT count(*) FROM {schema}.proof e
          JOIN {schema}.keymap owner ON owner.stage_key=e.normalization_key
          JOIN {schema}.keymap target ON target.stage_key=e.revision_key
          LEFT JOIN source_proof_edge p ON p.normalization_key=owner.normalization_key
            AND p.revision_key=target.revision_key WHERE p.normalization_key IS NULL""")
        )
        if missing:
            raise ArchiveError("Published proof is incomplete")
        mutations["current"] = merge_table(session, schema, "current")
        if header["scope"].get("mode") == "global":
            session.execute(
                text(f"""UPDATE source_record r SET is_current=false
              WHERE r.source_dataset_id=:dataset AND r.is_current
                AND NOT EXISTS(SELECT 1 FROM {schema}.source_record incoming
                               WHERE incoming.id=r.id)"""),
                {"dataset": DATASET_UUID},
            )
        session.execute(
            text("""UPDATE source_dataset SET version=:version,publication_archive_id=:archive,
          title=:title,published_at=now(),updated_at=now() WHERE id=:dataset"""),
            {
                "version": digest(header),
                "archive": archive_id,
                "dataset": DATASET_UUID,
                "title": "PBDB public global"
                if header["scope"].get("mode") == "global"
                else "PBDB public Florida",
            },
        )
        # Autovacuum cannot observe these newly merged rows before commit.
        # Give discovery's joins the caller's real population, including fresh
        # canonical/evidence tables, instead of empty-table estimates.
        statistics_started = time.perf_counter()
        for table in TABLES.values():
            session.execute(text(f'ANALYZE "{table.name}"'))
        metrics["publication_statistics_seconds"] = time.perf_counter() - statistics_started
        hook("before_discovery")
        start = time.perf_counter()
        projection = rebuild_catalog(session)
        for name in ("catalog_entry", "catalog_term", "context_term", "taxon_path"):
            session.execute(text(f'ANALYZE "{name}"'))
        membership = rebuild_members(session)
        session.execute(text("ANALYZE occurrence_browse_member"))
        metrics["discovery_seconds"] = time.perf_counter() - start
        # Partial retained scopes preserve unseen records; validate the complete
        # current publication, not just this batch's incoming occurrence count.
        expected = int(
            session.scalar(
                text("""SELECT count(*) FROM source_record
          WHERE source_dataset_id=:dataset AND record_type='occurrence' AND is_current"""),
                {"dataset": DATASET_UUID},
            )
            or 0
        )
        if projection["occurrences"] != expected or membership["occurrences"] != expected:
            raise ArchiveError("Published discovery is incomplete")
        # Actual warm product reads run before the transaction becomes visible.
        page = occurrence_catalog(session, ContextQuery(source="pbdb", limit=3))
        if page.total != expected or (expected and not page.items):
            raise ArchiveError("Staged product catalog is incomplete")
        for item in page.items:
            detail = inspect_occurrence(session, item.id)
            if item.specimen_id is not None or not detail["history_complete"]:
                raise ArchiveError("Product inspection lost occurrence/history semantics")
        metrics["product_validation"] = {"total": page.total, "inspected": len(page.items)}
        hook("before_ready_switch")
        observe_memory(metrics)
        metrics["publication_seconds"] = time.perf_counter() - publication_started
        if metrics.get("wal_start_lsn"):
            metrics["wal_inserted_bytes"] = int(
                session.scalar(
                    text(
                        "SELECT pg_wal_lsn_diff(pg_current_wal_insert_lsn(),CAST(:start AS pg_lsn))"
                    ),
                    {"start": metrics["wal_start_lsn"]},
                )
                or 0
            )
        metrics["mutations"] = mutations
        metrics["published_counts"] = counts
        session.execute(
            text("""UPDATE ingestion_run SET status='completed',completed_at=now(),
          records_read=:records,records_accepted=:records,records_inserted=:inserted,
          records_updated=:updated,error_summary=NULL WHERE id=:id"""),
            {
                "id": job.id,
                "records": sum(counts.values()),
                "inserted": inserted,
                "updated": mutations["source"] - inserted,
            },
        )
        session.execute(
            text("""UPDATE global_ingestion_job SET state='ready',archive_id=:archive,
          metrics=CAST(:metrics AS jsonb),updated_at=now(),error=NULL WHERE id=:id"""),
            {"id": job.id, "archive": archive_id, "metrics": json.dumps(metrics)},
        )
        return {"status": "ready", "job_id": str(job.id), "archive_id": str(archive_id), **metrics}


def cleanup_staging(engine: Engine, job: GlobalIngestionJob) -> None:
    with engine.begin() as c:
        ready = c.scalar(
            text("SELECT state='ready' FROM global_ingestion_job WHERE id=:id"), {"id": job.id}
        )
        if not ready:
            raise ValueError("Cannot remove unfinished staging")
        c.execute(text(f"DROP SCHEMA IF EXISTS {schema_name(job.staging_schema)} CASCADE"))


def ingest_global(
    engine: Engine,
    snapshot_path: Path,
    store: ArchiveStore,
    work: Path,
    *,
    batch_size: int = 256,
    hook: Callable[[str], None] | None = None,
    normal_checkpoint: Path | None = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    if not 1 <= batch_size <= 1000:
        raise ValueError("Bounded ingestion batch must be 1..1000")
    header_path = snapshot_path / "manifest.json"
    if header_path.stat().st_size > 32 * 1024 * 1024:
        raise ArchiveError("Snapshot header exceeds bounded manifest size")
    header = json.loads(header_path.read_bytes())
    target_guard(engine, header, normal_checkpoint)
    notify = hook or (lambda _: None)
    snapshot_hash = digest(header)
    job_id = stable_id("ingestion-job", snapshot_hash)
    started = time.perf_counter()
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(74005001)")):
            raise ValueError("Another PBDB staging/publication writer is active")
        try:
            with Session(engine) as session, session.begin():
                if session.scalar(text("SELECT current_database()")) != engine.url.database:
                    raise ValueError("Connected database differs from guarded target")
                if (
                    session.scalar(text("SELECT version_num FROM alembic_version"))
                    != "0014_design_c_native_cache"
                ):
                    raise ValueError(
                        "Design C ingestion requires the validated 0013/0014 migrations"
                    )
                session.execute(
                    insert(Source)
                    .values(
                        id=SOURCE_UUID,
                        name=PROVIDER,
                        homepage_url="https://paleobiodb.org/",
                        api_url=SERVICE,
                    )
                    .on_conflict_do_nothing()
                )
                session.execute(
                    insert(SourceDataset)
                    .values(
                        id=DATASET_UUID,
                        source_id=SOURCE_UUID,
                        external_dataset_id=DATASET,
                        title="PBDB retained scope",
                        publisher=PROVIDER,
                        dataset_url=SERVICE,
                        license="CC0 1.0",
                        retrieved_at=datetime.now(UTC),
                        is_synthetic=False,
                    )
                    .on_conflict_do_nothing()
                )
                job = session.get(GlobalIngestionJob, job_id)
                if job is None:
                    job = GlobalIngestionJob(
                        id=job_id,
                        dataset_id=DATASET_UUID,
                        snapshot_hash=snapshot_hash,
                        state="archiving",
                        staging_schema="pbdb_stage_" + job_id.hex,
                        checkpoint={},
                        metrics={},
                    )
                    session.add(job)
                    session.flush()
                    session.execute(
                        insert(IngestionRun).values(
                            id=job_id,
                            source_dataset_id=DATASET_UUID,
                            started_at=job.created_at,
                            status="running",
                            source_version=snapshot_hash,
                            importer_version=ADAPTER_VERSION,
                            snapshot={"phase": "Design C", "snapshot_hash": snapshot_hash},
                        )
                    )
                # Capture detached immutable run facts before releasing this short transaction.
                session.expunge(job)
            if job.state == "ready":
                with Session(engine) as session:
                    archive = session.get(SourceArchive, job.archive_id)
                    if archive is None:
                        raise ArchiveError("Ready job lost its archive metadata")
                    verify_archive(store, archive.manifest_hash)
                if cleanup:
                    cleanup_staging(engine, job)
                return {
                    "status": "ready",
                    "exact_replay": True,
                    "mutations": {},
                    "job_id": str(job_id),
                }
            cp = cast(dict[str, Any], dict(job.checkpoint))
            metrics = cast(dict[str, Any], dict(job.metrics))
            if "wal_start_lsn" not in metrics:
                with engine.connect() as connection:
                    metrics["wal_start_lsn"] = str(
                        connection.scalar(text("SELECT pg_current_wal_insert_lsn()"))
                    )
            observe_memory(metrics)
            notify("before_archive")
            original_hash, header = archive_snapshot(snapshot_path, store)
            cp["original_archive"] = original_hash
            checkpoint_job(engine, job_id, "staging", cp, metrics)
            notify("archive_verified")
            stage = DiskStage(work / f"{job_id.hex}.sqlite", snapshot_hash)
            try:
                stage.stage(store, original_hash)
                notify("responses_staged")
                counts = stage.prepare_records(header, batch_size)
                stage.prepare_edges()
                checkpoint_job(engine, job_id, "normalizing", cp, metrics)
                for cursor in stage.normalize(batch_size):
                    cp["normalization_cursor"] = cursor
                    observe_memory(metrics)
                    checkpoint_job(engine, job_id, "normalizing", cp, metrics)
                    notify("normalization_batch")
                manifest = verify_archive(store, original_hash)
                chunks = []
                for metadata, locators in raw_chunks(store, stage.raw_records()):
                    chunks.append(metadata)
                    with stage.db:
                        stage.db.executemany(
                            "INSERT OR REPLACE INTO locator VALUES(?,?,?,?)",
                            ((sid, h, metadata["hash"], ordinal) for sid, h, ordinal in locators),
                        )
                manifest = {
                    **manifest,
                    "files": [*manifest["files"], *chunks],
                    "counts": {
                        **manifest["counts"],
                        "raw_revisions": sum(counts.values()),
                        "by_kind": counts,
                    },
                }
                ready_hash = publish_manifest(store, manifest)
                with Session(engine) as session, session.begin():
                    archive_id = register_archive(session, store, ready_hash)
                    session.execute(
                        text("UPDATE global_ingestion_job SET archive_id=:archive WHERE id=:id"),
                        {"archive": archive_id, "id": job_id},
                    )
                    session.execute(
                        text(
                            "UPDATE ingestion_run SET snapshot=CAST(:snapshot AS jsonb) "
                            "WHERE id=:id"
                        ),
                        {
                            "id": job_id,
                            "snapshot": json.dumps(
                                {"manifest_hash": ready_hash, "manifest": manifest}
                            ),
                        },
                    )
                notify("before_backfill")
                stage_postgres(
                    engine, stage, store, archive_id, job, cp, metrics, batch_size, notify
                )
                cp["archive_manifest"] = ready_hash
                metrics["staged_source_records"] = sum(counts.values())
                metrics["staged_proofs"] = stage.db.execute(
                    "SELECT count(*) FROM proof"
                ).fetchone()[0]
                metrics["staging_seconds"] = time.perf_counter() - started
                metrics["sqlite_bytes"] = sum(
                    p.stat().st_size
                    for p in (
                        stage.path,
                        Path(str(stage.path) + "-wal"),
                        Path(str(stage.path) + "-shm"),
                    )
                    if p.exists()
                )
                checkpoint_job(engine, job_id, "validated", cp, metrics)
                notify("staging_validated")
                checkpoint_job(engine, job_id, "publishing", cp, metrics)
                result = publish_staged(
                    engine, store, job, archive_id, header, counts, metrics, notify
                )
            finally:
                stage.close()
            if cleanup:
                cleanup_staging(engine, job)
            result["duration_seconds"] = time.perf_counter() - started
            return result
        except Exception as error:
            with engine.begin() as c:
                c.execute(
                    text("""UPDATE global_ingestion_job SET state='failed',error=:error,
                  updated_at=now() WHERE id=:id AND state<>'ready'"""),
                    {"id": job_id, "error": f"{type(error).__name__}: {error}"[:2000]},
                )
                c.execute(
                    text("""UPDATE ingestion_run SET status='failed',completed_at=now(),
                  error_summary=:error WHERE id=:id AND status<>'completed'"""),
                    {"id": job_id, "error": f"{type(error).__name__}: {error}"[:2000]},
                )
            raise
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(74005001)"))
