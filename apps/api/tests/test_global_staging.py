"""Disk staging is exactly equivalent to retained scientific normalization."""

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.db import Base
from app.ingestion.archive import ArchiveError, LocalArchiveStore, verify_archive
from app.ingestion.global_pipeline import target_guard
from app.ingestion.global_staging import DiskStage, archive_snapshot, restore_snapshot
from app.ingestion.import_pbdb import plan, record_id
from app.ingestion.pbdb import ADAPTER_VERSION, Snapshot, digest

FIXTURE = Path(__file__).parent / "fixtures/pbdb"


def test_normal_target_rejects_empty_restore_evidence_and_changed_current_rows(
    tmp_path, monkeypatch
):
    engine = create_engine("postgresql+psycopg://paleograph:unused@127.0.0.1:5432/paleograph")
    header = {"scope": {"mode": "global", "complete_scope": True}}
    receipt = tmp_path / "checkpoint.json"
    evidence = {
        "label": "pre-5b2",
        "status": "verified",
        "approved_snapshot_hash": digest(header),
        "baseline": {"migration": "0014_design_c_native_cache"},
        "restore": {"migration": "0014_design_c_native_cache"},
    }
    receipt.write_text(json.dumps(evidence), encoding="utf8")
    with pytest.raises(ValueError, match="scientific equivalence"):
        target_guard(engine, header, receipt)
    rows = {name: {"rows": 0, "sha256": "a" * 64} for name in Base.metadata.tables}
    digests = {
        name: "b" * 32
        for name in (
            "source",
            "interpretation",
            "catalog_science",
            "locality_summary",
            "taxon_summary",
        )
    }
    for section in ("baseline", "restore"):
        evidence[section].update(full_rows=rows, ufvp_digests=digests)
    dump = tmp_path / "checkpoint.dump"
    dump.write_bytes(b"retained test checkpoint bytes")
    evidence.update(
        path=str(dump), sha256=hashlib.sha256(dump.read_bytes()).hexdigest(), archive_files={}
    )
    receipt.write_text(json.dumps(evidence), encoding="utf8")
    monkeypatch.setattr("app.ingestion.global_pipeline.checkpoint_fingerprints", lambda _engine: {})
    with pytest.raises(ValueError, match="changed since"):
        target_guard(engine, header, receipt)
    monkeypatch.setattr(
        "app.ingestion.global_pipeline.checkpoint_fingerprints", lambda _engine: rows
    )
    target_guard(engine, header, receipt)
    dump.write_bytes(b"replaced checkpoint")
    with pytest.raises(ValueError, match="checkpoint bytes changed"):
        target_guard(engine, header, receipt)
    engine.dispose()


def test_staged_normalization_and_complete_proofs_match_existing_adapter(tmp_path):
    store = LocalArchiveStore(tmp_path / "objects")
    archived, header = archive_snapshot(FIXTURE, store)
    original = Snapshot.load(FIXTURE)
    assert verify_archive(store, archived)["snapshot_hash"] == original.hash
    records, dependencies = plan(original)
    with_stage = DiskStage(tmp_path / "stage.sqlite", original.hash)
    with_stage.stage(store, archived)
    counts = with_stage.prepare_records(header, batch_size=3)
    assert counts["occurrence"] == 8
    with_stage.prepare_edges()
    # Stop after one committed normalization batch, close, then resume.
    first = next(with_stage.normalize(batch_size=3))
    with_stage.close()
    resumed = DiskStage(tmp_path / "stage.sqlite", original.hash)
    assert int(resumed.get("normalization_cursor")) == first
    list(resumed.normalize(batch_size=3))
    retained = resumed.db.execute("SELECT * FROM record").fetchall()
    assert len(retained) == len(records)
    for row in retained:
        key = (row["kind"], row["external"])
        assert row["hash"] == records[key]["hash"]
        assert json.loads(row["evidence"]) == records[key]["normalized"]
        frame = sorted((str(record_id(*dep)), records[dep]["hash"]) for dep in dependencies[key])
        payload = {
            "record_type": key[0],
            "external_id": key[1],
            "evidence": records[key]["normalized"],
            "dependencies": frame,
        }
        assert digest({"adapter": ADAPTER_VERSION, "payload": payload}) == row["normalization_hash"]
        actual = [
            tuple(r)
            for r in resumed.db.execute(
                """SELECT r.source_id,r.hash
          FROM proof p JOIN record r ON r.k=p.target WHERE p.owner=?
          ORDER BY r.source_id,r.hash""",
                (row["k"],),
            )
        ]
        assert actual == frame
    before = counts.copy()
    resumed.stage(store, archived)
    assert resumed.prepare_records(header) == before
    resumed.prepare_edges()
    assert list(resumed.normalize()) == []
    resumed.close()


def test_staging_artifact_cannot_be_reused_for_different_snapshot(tmp_path):
    stage = DiskStage(tmp_path / "stage.sqlite", "1" * 64)
    stage.close()
    with pytest.raises(ArchiveError, match="different snapshot"):
        DiskStage(tmp_path / "stage.sqlite", "2" * 64)


def test_completed_staging_cannot_copy_tampered_cached_normalization(tmp_path):
    store = LocalArchiveStore(tmp_path / "objects")
    archived, header = archive_snapshot(FIXTURE, store)
    stage = DiskStage(tmp_path / "stage.sqlite", digest(header))
    stage.stage(store, archived)
    stage.prepare_records(header)
    stage.prepare_edges()
    list(stage.normalize())
    row = stage.db.execute("SELECT * FROM record WHERE kind='occurrence' LIMIT 1").fetchone()
    assert stage.verified_normalization(row)["external_id"] == row["external"]
    stage.db.execute("UPDATE record SET evidence='{}' WHERE k=?", (row["k"],))
    stage.db.commit()
    row = stage.db.execute("SELECT * FROM record WHERE k=?", (row["k"],)).fetchone()
    with pytest.raises(ArchiveError, match="staged normalization hash"):
        stage.verified_normalization(row)
    stage.close()


def test_provider_count_change_or_incomplete_global_control_blocks_publication(tmp_path):
    store = LocalArchiveStore(tmp_path / "objects")
    archived, header = archive_snapshot(FIXTURE, store)
    stage = DiskStage(tmp_path / "stage.sqlite", digest(header))
    stage.stage(store, archived)
    changed = {
        **header,
        "scope": {"mode": "global"},
        "counts_before": {"occurrence": 8},
        "counts_after": {"occurrence": 9},
    }
    with pytest.raises(ArchiveError, match="changed global"):
        stage.prepare_records(changed)
    changed["counts_after"] = changed["counts_before"]
    with pytest.raises(ArchiveError, match="every retained kind"):
        stage.prepare_records(changed)
    stage.close()


def test_pinned_archive_rebuild_needs_no_original_response_directory(tmp_path):
    store = LocalArchiveStore(tmp_path / "objects")
    archived, header = archive_snapshot(FIXTURE, store)
    stage = DiskStage(tmp_path / "independent-rebuild.sqlite", digest(header))
    stage.stage(store, archived)
    counts = stage.prepare_records(header)
    stage.prepare_edges()
    list(stage.normalize())
    assert counts["occurrence"] == 8
    assert sum(counts.values()) == stage.db.execute("SELECT count(*) FROM record").fetchone()[0]
    stage.close()
    recovered = restore_snapshot(store, archived, tmp_path / "recovered")
    assert Snapshot.load(recovered).hash == digest(header)
