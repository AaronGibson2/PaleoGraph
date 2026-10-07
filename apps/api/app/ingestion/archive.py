"""Immutable provider-neutral archive publication and verified bounded evidence reads.

The store has only put/get; publication owns verification and manifests. A READY
manifest is written last, and PostgreSQL publication additionally requires READY.
No garbage collection or upstream substitution exists here.
"""

import gzip
import hashlib
import io
import json
import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from app.ingestion.pbdb import digest

MAX_OBJECT_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 32 * 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")


class ArchiveError(ValueError):
    """Missing, unavailable or corrupt evidence; never implies valid provenance."""


class ArchiveStore(Protocol):
    @property
    def reference(self) -> str: ...

    def put(self, key: str, content: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...


class LocalArchiveStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def reference(self) -> str:
        return self.root.as_uri()

    def _path(self, key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}\.(gz|manifest|ready)", key):
            raise ArchiveError("Invalid content-addressed archive key")
        target = (self.root / key).resolve()
        if target.parent != self.root:
            raise ArchiveError("Archive path escapes its store")
        return target

    def put(self, key: str, content: bytes) -> None:
        target = self._path(key)
        if len(content) > MAX_OBJECT_BYTES:
            raise ArchiveError("Archive object exceeds bounded object limit")
        if target.exists():
            if self.get(key) != content:
                raise ArchiveError("Immutable archive key already contains different bytes")
            return
        # fsync before an atomic no-clobber link. Concurrent identical publications
        # converge; no overwrite of a ready/historical object is allowed.
        fd, name = tempfile.mkstemp(dir=self.root, prefix="unpublished-")
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if self.get(key) != content:
                    raise ArchiveError("Concurrent archive publication disagrees") from None
        finally:
            temporary.unlink(missing_ok=True)
        if self.get(key) != content:
            raise ArchiveError("Archive reopen verification failed")

    def get(self, key: str) -> bytes:
        target = self._path(key)
        try:
            if target.stat().st_size > MAX_OBJECT_BYTES:
                raise ArchiveError("Archive object exceeds bounded object limit")
            return target.read_bytes()
        except OSError as error:
            raise ArchiveError(f"Archive unavailable: {key}") from error


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_object(store: ArchiveStore, raw: bytes, *, kind: str, records: int) -> dict[str, Any]:
    if len(raw) > MAX_OBJECT_BYTES:
        raise ArchiveError("Expanded archive object exceeds bounded limit")
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    key = sha(compressed)
    store.put(f"{key}.gz", compressed)
    metadata = {
        "hash": key,
        "original_hash": sha(raw),
        "bytes": len(compressed),
        "original_bytes": len(raw),
        "records": records,
        "kind": kind,
        "compression": "gzip",
    }
    if read_object(store, metadata) != raw:
        raise ArchiveError("Archive round-trip changed original source bytes")
    return metadata


def read_object(store: ArchiveStore, metadata: dict[str, Any]) -> bytes:
    key = metadata.get("hash", "")
    if not isinstance(key, str) or not HASH.fullmatch(key):
        raise ArchiveError("Invalid archive object identity")
    compressed = store.get(f"{key}.gz")
    if len(compressed) != metadata["bytes"] or sha(compressed) != key:
        raise ArchiveError("Archive compressed hash/size mismatch")
    if metadata["original_bytes"] > MAX_OBJECT_BYTES or metadata["original_bytes"] < 0:
        raise ArchiveError("Expanded object size violates memory bound")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            body = stream.read(metadata["original_bytes"] + 1)
            if stream.read(1):
                raise ArchiveError("Archive expands beyond declared size")
    except (OSError, EOFError) as error:
        raise ArchiveError("Corrupt/truncated archive compression") from error
    if len(body) != metadata["original_bytes"] or sha(body) != metadata["original_hash"]:
        raise ArchiveError("Archive expanded hash/size mismatch")
    return body


def publish_manifest(store: ArchiveStore, manifest: dict[str, Any]) -> str:
    """Verify every bounded object, then atomically publish immutable READY last."""
    if manifest.get("format") != "paleograph-source-archive-v1":
        raise ArchiveError("Unsupported archive manifest format")
    required = {
        "provider",
        "snapshot_hash",
        "retrieved_at",
        "scope",
        "adapter_version",
        "policy_version",
        "rights",
        "files",
        "counts",
        "migration",
    }
    if required - manifest.keys() or not manifest["files"]:
        raise ArchiveError("Incomplete archive manifest")
    raw_revisions = 0
    for entry in manifest["files"]:
        body = read_object(store, entry)
        if entry["kind"] == "provider-index":
            descriptors = body.splitlines()
            if len(descriptors) != entry["records"]:
                raise ArchiveError("Provider index shard count mismatch")
            for line in descriptors:
                read_object(store, json.loads(line)["object"])
        if entry["kind"] == "raw-records":
            lines = body.splitlines()
            if len(lines) != entry["records"]:
                raise ArchiveError("Canonical raw archive row count mismatch")
            for line in lines:
                row = json.loads(line)
                if digest(row["raw"]) != row["content_hash"]:
                    raise ArchiveError("Canonical evidence hash mismatch")
            raw_revisions += len(lines)
    if manifest["counts"].get("raw_revisions") != raw_revisions:
        raise ArchiveError("Archive manifest raw revision count mismatch")
    encoded = canonical_bytes(manifest)
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ArchiveError("Manifest exceeds bounded metadata limit")
    manifest_hash = sha(encoded)
    store.put(f"{manifest_hash}.manifest", encoded)
    if sha(store.get(f"{manifest_hash}.manifest")) != manifest_hash:
        raise ArchiveError("Manifest reopen hash mismatch")
    store.put(f"{manifest_hash}.ready", canonical_bytes({"manifest_hash": manifest_hash}))
    return manifest_hash


def verify_archive(store: ArchiveStore, manifest_hash: str) -> dict[str, Any]:
    marker = store.get(f"{manifest_hash}.ready")
    if marker != canonical_bytes({"manifest_hash": manifest_hash}):
        raise ArchiveError("Archive READY marker mismatch")
    encoded = store.get(f"{manifest_hash}.manifest")
    if sha(encoded) != manifest_hash:
        raise ArchiveError("Archive manifest hash mismatch")
    manifest: dict[str, Any] = json.loads(encoded)
    # Verification does not create/recreate a missing readiness marker.
    for entry in manifest["files"]:
        body = read_object(store, entry)
        if entry["kind"] == "provider-index":
            for line in body.splitlines():
                read_object(store, json.loads(line)["object"])
    return manifest


def raw_chunks(
    store: ArchiveStore, records: Iterable[dict[str, Any]], *, chunk_size: int = 1000
) -> Iterable[tuple[dict[str, Any], list[tuple[str, str, int]]]]:
    if not 1 <= chunk_size <= 5000:
        raise ArchiveError("Raw chunk batch size must be bounded")
    lines: list[bytes] = []
    locators: list[tuple[str, str, int]] = []
    size = 0
    for row in records:
        if digest(row["raw"]) != row["content_hash"]:
            raise ArchiveError("Raw record differs from its immutable revision hash")
        encoded = canonical_bytes(row)
        if size + len(encoded) + 1 > MAX_OBJECT_BYTES:
            raise ArchiveError("Canonical raw chunk exceeds object bound")
        locators.append((str(row["source_record_id"]), row["content_hash"], len(lines)))
        lines.append(encoded)
        size += len(encoded) + 1
        if len(lines) == chunk_size:
            yield (
                write_object(
                    store, b"\n".join(lines) + b"\n", kind="raw-records", records=len(lines)
                ),
                locators,
            )
            lines, locators, size = [], [], 0
    if lines:
        yield (
            write_object(store, b"\n".join(lines) + b"\n", kind="raw-records", records=len(lines)),
            locators,
        )


def read_raw(
    store: ArchiveStore,
    metadata: dict[str, Any],
    ordinal: int,
    source_record_id: str,
    content_hash: str,
) -> dict[str, Any]:
    rows = read_object(store, metadata).splitlines()
    if len(rows) != metadata["records"] or not 0 <= ordinal < len(rows):
        raise ArchiveError("Invalid raw revision locator")
    row = json.loads(rows[ordinal])
    if (
        row["source_record_id"] != source_record_id
        or row["content_hash"] != content_hash
        or digest(row["raw"]) != content_hash
    ):
        raise ArchiveError("Archived raw revision identity/hash mismatch")
    result: dict[str, Any] = row["raw"]
    return result
