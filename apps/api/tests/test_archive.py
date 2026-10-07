"""Scientific archive publication and evidence retrieval through the real store interface."""

import gzip
import json

import pytest

from app.ingestion.archive import (
    ArchiveError,
    LocalArchiveStore,
    canonical_bytes,
    publish_manifest,
    raw_chunks,
    read_object,
    read_raw,
    sha,
    verify_archive,
    write_object,
)
from app.ingestion.pbdb import digest


def archived(tmp_path):
    store = LocalArchiveStore(tmp_path / "objects")
    raw = {"occurrence_no": "occ:1", "identified_name": "Retained scientific assertion"}
    row = {"source_record_id": "source-1", "content_hash": digest(raw), "raw": raw}
    metadata, locators = next(iter(raw_chunks(store, [row])))
    manifest = {
        "format": "paleograph-source-archive-v1",
        "provider": "test-only provider",
        "snapshot_hash": digest({"snapshot": 1}),
        "retrieved_at": "2026-10-06T00:00:00+00:00",
        "scope": {"mode": "test-only"},
        "adapter_version": "pbdb-adapter-v1",
        "policy_version": "pbdb-provider-envelope-v1",
        "rights": "CC0 1.0",
        "migration": "0013_design_c",
        "files": [metadata],
        "counts": {"raw_revisions": 1},
    }
    return store, raw, row, metadata, locators, manifest


def test_immutable_verified_publication_replay_and_evidence(tmp_path):
    store, raw, row, meta, locators, manifest = archived(tmp_path)
    published = publish_manifest(store, manifest)
    assert verify_archive(store, published) == manifest
    before = {p.name: p.read_bytes() for p in store.root.iterdir()}
    assert publish_manifest(store, manifest) == published
    assert before == {p.name: p.read_bytes() for p in store.root.iterdir()}
    assert locators == [("source-1", row["content_hash"], 0)]
    assert read_raw(store, meta, 0, "source-1", row["content_hash"]) == raw
    changed = {**manifest, "snapshot_hash": digest({"snapshot": 2})}
    assert publish_manifest(store, changed) != published
    assert verify_archive(store, published) == manifest


@pytest.mark.parametrize("failure", ["missing", "truncated", "corrupt", "wrong-hash"])
def test_corruption_or_missing_object_blocks_ready(tmp_path, failure):
    store, _, _, meta, _, manifest = archived(tmp_path)
    path = store.root / f"{meta['hash']}.gz"
    if failure == "missing":
        path.unlink()
    elif failure == "truncated":
        path.write_bytes(path.read_bytes()[:12])
    elif failure == "corrupt":
        path.write_bytes(b"corrupt archive")
    else:
        meta["original_hash"] = "0" * 64
    with pytest.raises(ArchiveError):
        publish_manifest(store, manifest)
    assert not list(store.root.glob("*.ready"))


@pytest.mark.parametrize("failure", ["incomplete", "manifest-mismatch", "unavailable"])
def test_incomplete_manifest_or_storage_failure_never_publishes(tmp_path, failure):
    store, _, _, _, _, manifest = archived(tmp_path)
    if failure == "incomplete":
        manifest["files"] = []
    elif failure == "manifest-mismatch":
        manifest["counts"]["raw_revisions"] = 2
    else:

        class Unavailable:
            reference = "test-only unavailable"

            def get(self, key):
                raise ArchiveError("Archive storage unavailable")

            def put(self, key, body):
                raise ArchiveError("Archive storage unavailable")

        store = Unavailable()
    with pytest.raises(ArchiveError):
        publish_manifest(store, manifest)
    assert not list((tmp_path / "objects").glob("*.ready"))


def test_missing_ready_marker_is_not_recreated_by_integrity_check(tmp_path):
    store, _, _, _, _, manifest = archived(tmp_path)
    published = publish_manifest(store, manifest)
    (store.root / f"{published}.ready").unlink()
    with pytest.raises(ArchiveError, match="unavailable"):
        verify_archive(store, published)
    assert not list(store.root.glob("*.ready"))


def test_manifest_bytes_and_marker_mismatch_fail_closed(tmp_path):
    store, _, _, _, _, manifest = archived(tmp_path)
    published = publish_manifest(store, manifest)
    (store.root / f"{published}.manifest").write_bytes(b"wrong manifest")
    with pytest.raises(ArchiveError, match="manifest hash"):
        verify_archive(store, published)
    (store.root / f"{published}.manifest").write_bytes(canonical_bytes(manifest))
    (store.root / f"{published}.ready").write_text('{"manifest_hash":"wrong"}')
    with pytest.raises(ArchiveError, match="marker mismatch"):
        verify_archive(store, published)


def test_immutable_key_cannot_replace_content(tmp_path):
    store, _, _, meta, _, _ = archived(tmp_path)
    with pytest.raises(ArchiveError, match="Immutable"):
        store.put(f"{meta['hash']}.gz", b"replacement")


@pytest.mark.parametrize("change", ["ordinal", "identity", "revision"])
def test_wrong_raw_revision_locator_rejected(tmp_path, change):
    store, _, row, meta, _, _ = archived(tmp_path)
    ordinal = 1 if change == "ordinal" else 0
    source = "wrong" if change == "identity" else "source-1"
    content_hash = "0" * 64 if change == "revision" else row["content_hash"]
    with pytest.raises(ArchiveError):
        read_raw(store, meta, ordinal, source, content_hash)


def test_forged_inner_evidence_rejected_even_when_outer_hashes_match(tmp_path):
    store, _, row, _, _, manifest = archived(tmp_path)
    forged = {**row, "raw": {"changed": "scientific evidence"}}
    meta = write_object(store, canonical_bytes(forged) + b"\n", kind="raw-records", records=1)
    manifest["files"] = [meta]
    with pytest.raises(ArchiveError, match="evidence hash"):
        publish_manifest(store, manifest)
    with pytest.raises(ArchiveError, match="identity/hash"):
        read_raw(store, meta, 0, "source-1", row["content_hash"])


def test_truncated_gzip_with_matching_compressed_hash_rejected(tmp_path):
    store, _, row, meta, _, _ = archived(tmp_path)
    compressed = gzip.compress(canonical_bytes(row))[:12]
    key = sha(compressed)
    store.put(f"{key}.gz", compressed)
    with pytest.raises(ArchiveError, match="compression"):
        read_object(store, {**meta, "hash": key, "bytes": len(compressed)})


def test_invalid_key_cannot_escape_local_archive_store(tmp_path):
    store = LocalArchiveStore(tmp_path)
    for key in ("../secret.gz", "C:/private.gz", "not-a-hash.gz"):
        with pytest.raises(ArchiveError, match="key"):
            store.get(key)


def test_nonfinite_raw_evidence_and_wrong_manifest_format_rejected(tmp_path):
    store, _, _, _, _, manifest = archived(tmp_path)
    manifest["format"] = "unknown format"
    with pytest.raises(ArchiveError, match="format"):
        publish_manifest(store, manifest)
    with pytest.raises(ValueError):
        canonical_bytes({"evidence": float("nan")})
    assert json.loads(canonical_bytes({"raw": "à"})) == {"raw": "à"}
