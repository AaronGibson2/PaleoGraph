"""Disk-backed PBDB normalization. No whole-source dictionaries or global ID arrays.

Provider responses are bounded pages. SQLite is a recoverable local staging
artifact, not a second product database; PostgreSQL remains the scientific store.
Every published archive can regenerate this artifact without hidden input files.
"""

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.ingestion.archive import (
    MAX_MANIFEST_BYTES,
    MAX_OBJECT_BYTES,
    ArchiveError,
    ArchiveStore,
    canonical_bytes,
    publish_manifest,
    read_object,
    sha,
    verify_archive,
    write_object,
)
from app.ingestion.import_pbdb import json_value, record_id
from app.ingestion.pbdb import (
    ADAPTER_VERSION,
    DATASET,
    POLICY_VERSION,
    PROVIDER,
    SERVICE,
    decode_response,
    digest,
    identification_key,
    identifier,
    is_florida_context,
    normalize_collection,
    normalize_material,
    normalize_measurement,
    normalize_occurrences,
    normalize_opinion,
    normalize_reference,
    normalize_taxon_name,
    optional_identifier,
)

FIELDS = {
    "collections": ("collection", "collection_no", "col"),
    "materials": ("material", "specimen_no", "spm"),
    "measurements": ("measurement", "measurement_no", "mea"),
    "intervals": ("interval", "interval_no", "int"),
    "timescales": ("timescale", "scale_no", "tsc"),
    "references": ("reference", "reference_no", "ref"),
    "opinions": ("opinion", "opinion_no", "opn"),
    "taxa": ("taxon", "taxon_no", "txn"),
}
NORMALIZERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "collection": normalize_collection,
    "material": normalize_material,
    "measurement": normalize_measurement,
    "reference": normalize_reference,
    "opinion": normalize_opinion,
    "taxon": normalize_taxon_name,
}


def response_entries(path: Path, manifest: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if "response_index" not in manifest:
        yield from manifest["responses"]
        return
    index = manifest["response_index"]
    target = (path / index["file"]).resolve()
    if target.parent != path.resolve() or target.stat().st_size != index["bytes"]:
        raise ArchiveError("Invalid provider response index location/size")
    with target.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != index["sha256"]:
            raise ArchiveError("Provider response index hash mismatch")
    count = 0
    with target.open("rb") as stream:
        for line in stream:
            if len(line) > 1024 * 1024:
                raise ArchiveError("Provider response descriptor exceeds bounded size")
            count += 1
            yield json.loads(line)
    if count != index["entries"]:
        raise ArchiveError("Provider response index count mismatch")


def archive_snapshot(path: Path, store: ArchiveStore) -> tuple[str, dict[str, Any]]:
    path = path.resolve()
    header_path = path / "manifest.json"
    if header_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ArchiveError("Snapshot header must be bounded; use sharded response_index")
    header_bytes = header_path.read_bytes()
    header: dict[str, Any] = json.loads(header_bytes)
    if header.get("format") not in {ADAPTER_VERSION, "pbdb-global-export-v1"}:
        raise ArchiveError("Unsupported PBDB snapshot format")
    if header.get("provider_dataset") != DATASET:
        raise ArchiveError("PBDB identity namespace must preserve the existing Florida IDs")
    if header.get("scope", {}).get("mode") not in {"canary", "full-florida", "global", "pilot"}:
        raise ArchiveError("Unsupported scientific source scope")
    files = [write_object(store, header_bytes, kind="provider-manifest", records=1)]
    if header.get("response_index"):
        index_path = (path / header["response_index"]["file"]).resolve()
        if index_path.parent != path:
            raise ArchiveError("Unsafe provider response index path")
        with index_path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                files.append(write_object(store, block, kind="provider-response-index", records=0))
    descriptors: list[bytes] = []
    counts: dict[str, int] = {}
    endpoints = {
        "histories": "occs/list",
        "latest": "occs/list",
        "originals": "occs/list",
        "collections": "colls/list",
        "materials": "specs/list",
        "measurements": "specs/measurements",
        "taxa": "taxa/list",
        "taxon-resolution": "taxa/list",
        "opinions": "taxa/opinions",
        "intervals": "intervals/list",
        "timescales": "timescales/list",
        "references": "refs/list",
        "selection": "occs/list",
    }
    for entry in response_entries(path, header):
        target = (path / entry["file"]).resolve()
        if target.parent != path or target.stat().st_size > MAX_OBJECT_BYTES:
            raise ArchiveError("Unsafe or unbounded retained provider response")
        raw = target.read_bytes()
        if len(raw) != entry["bytes"] or sha(raw) != entry["sha256"] or entry["status"] != 200:
            raise ArchiveError("Provider response hash/size/status mismatch")
        kind, params = entry["kind"], entry["parameters"]
        endpoint = endpoints.get(kind)
        if kind.startswith("census-"):
            endpoint = "occs/list" if "occurrences" in kind else "colls/list"
        if endpoint is None or entry["url"].split("?", 1)[0] != SERVICE + endpoint + ".json":
            raise ArchiveError("Provider endpoint differs from response kind")
        if parse_qs(urlparse(entry["url"]).query) != {k: [str(v)] for k, v in params.items()}:
            raise ArchiveError("Provider URL/selectors disagree")
        if any(
            params.get(k) != v
            for k, v in {
                "rowcount": "yes",
                "datainfo": "yes",
                "vocab": "pbdb",
                "extids": "yes",
                "strict": "yes",
            }.items()
        ):
            raise ArchiveError("Missing strict PBDB response/license/count controls")
        response = decode_response(raw, params, history=kind == "histories")
        if kind in {"taxa", "taxon-resolution", "opinions"}:
            if params.get("rel") != "exact" or params.get("base_id"):
                raise ArchiveError("Unsafe retained taxonomic scope")
            if kind == "taxa" and params.get("variant") != "all":
                raise ArchiveError("Incomplete retained taxonomic variants")
        if kind in {"latest", "originals", "histories"}:
            expected = {"histories": "all", "latest": "latest", "originals": "orig"}[kind]
            if params.get("idtype") != expected or params.get("all_idents"):
                raise ArchiveError("Unsafe identification history selector")
            if params.get("occ_id"):
                wanted = {identifier(v, "occ") for v in str(params["occ_id"]).split(",")}
                received = {identifier(r["occurrence_no"], "occ") for r in response["records"]}
                if wanted != received:
                    raise ArchiveError("Incomplete or unexpected fixed-ID history population")
        obj = write_object(store, raw, kind="provider-response", records=len(response["records"]))
        descriptors.append(canonical_bytes({"entry": entry, "object": obj}))
        counts[kind] = counts.get(kind, 0) + len(response["records"])
        if len(descriptors) == 128:
            files.append(
                write_object(
                    store,
                    b"\n".join(descriptors) + b"\n",
                    kind="provider-index",
                    records=len(descriptors),
                )
            )
            descriptors = []
    if descriptors:
        files.append(
            write_object(
                store,
                b"\n".join(descriptors) + b"\n",
                kind="provider-index",
                records=len(descriptors),
            )
        )
    if not {"histories", "latest", "originals", "collections", "materials"} <= counts.keys():
        raise ArchiveError("Missing provider population/history controls")
    manifest = {
        "format": "paleograph-source-archive-v1",
        "provider": PROVIDER,
        "snapshot_hash": digest(header),
        "retrieved_at": header["retrieval_completed"],
        "scope": header["scope"],
        "adapter_version": ADAPTER_VERSION,
        "policy_version": POLICY_VERSION,
        "rights": "CC0 1.0",
        "migration": "0013_design_c",
        "files": files,
        "counts": {"raw_revisions": 0, "response_rows": counts},
    }
    return publish_manifest(store, manifest), header


def archived_responses(
    store: ArchiveStore, manifest_hash: str
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    manifest = verify_archive(store, manifest_hash)
    for shard in manifest["files"]:
        if shard["kind"] != "provider-index":
            continue
        for line in read_object(store, shard).splitlines():
            descriptor = json.loads(line)
            entry = descriptor["entry"]
            response = decode_response(
                read_object(store, descriptor["object"]),
                entry["parameters"],
                history=entry["kind"] == "histories",
            )
            yield entry, response


def restore_snapshot(store: ArchiveStore, manifest_hash: str, target: Path) -> Path:
    """Rebuild explicit input bytes solely from a pinned READY archive."""
    manifest = verify_archive(store, manifest_hash)
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    headers = [f for f in manifest["files"] if f["kind"] == "provider-manifest"]
    if len(headers) != 1:
        raise ArchiveError("Archive must retain exactly one provider manifest")
    header_bytes = read_object(store, headers[0])
    header = json.loads(header_bytes)
    if digest(header) != manifest["snapshot_hash"]:
        raise ArchiveError("Retained provider snapshot identity differs")
    if header.get("response_index"):
        index_path = (target / header["response_index"]["file"]).resolve()
        if index_path.parent != target:
            raise ArchiveError("Recovered provider index escapes target")
        with index_path.open("wb") as stream:
            for f in manifest["files"]:
                if f["kind"] == "provider-response-index":
                    stream.write(read_object(store, f))
        with index_path.open("rb") as stream:
            if (
                hashlib.file_digest(stream, "sha256").hexdigest()
                != header["response_index"]["sha256"]
            ):
                raise ArchiveError("Recovered original provider index hash differs")
    for f in manifest["files"]:
        if f["kind"] != "provider-index":
            continue
        for line in read_object(store, f).splitlines():
            descriptor = json.loads(line)
            entry = descriptor["entry"]
            path = (target / entry["file"]).resolve()
            if path.parent != target:
                raise ArchiveError("Recovered provider response escapes target")
            body = read_object(store, descriptor["object"])
            if len(body) != entry["bytes"] or sha(body) != entry["sha256"]:
                raise ArchiveError("Recovered original response hash differs")
            path.write_bytes(body)
    (target / "manifest.json").write_bytes(header_bytes)
    # Recheck the complete explicit response descriptor population.
    for _entry in response_entries(target, header):
        pass
    return target


class DiskStage:
    def __init__(self, path: Path, snapshot_hash: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
          PRAGMA cache_size=-8192; PRAGMA temp_store=FILE;
          CREATE TABLE IF NOT EXISTS progress(name TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS input(kind TEXT,external TEXT,hash TEXT,raw TEXT,
            PRIMARY KEY(kind,external,hash));
          CREATE INDEX IF NOT EXISTS input_kind ON input(kind,external);
          CREATE INDEX IF NOT EXISTS input_history_owner
            ON input(kind,substr(external,1,instr(external,':')-1));
          CREATE TABLE IF NOT EXISTS record(k INTEGER PRIMARY KEY,kind TEXT,external TEXT,
            source_id TEXT UNIQUE,raw TEXT,hash TEXT,evidence TEXT,normalization_hash TEXT,
            UNIQUE(kind,external));
          CREATE INDEX IF NOT EXISTS record_occurrence_membership
            ON record(kind,json_extract(raw,'$.occurrence_no'));
          CREATE INDEX IF NOT EXISTS record_material_membership
            ON record(kind,json_extract(raw,'$.specimen_no'));
          CREATE TABLE IF NOT EXISTS alias(kind TEXT,value TEXT,target INTEGER,
            PRIMARY KEY(kind,value,target));
          CREATE TABLE IF NOT EXISTS direct(owner INTEGER,target INTEGER,PRIMARY KEY(owner,target));
          CREATE TABLE IF NOT EXISTS proof(
            owner INTEGER,target INTEGER,PRIMARY KEY(owner,target)) WITHOUT ROWID;
          CREATE TABLE IF NOT EXISTS occurrence(external TEXT PRIMARY KEY,raw TEXT);
          CREATE TABLE IF NOT EXISTS locator(
            source_id TEXT,hash TEXT,object_hash TEXT,ordinal INTEGER,
            PRIMARY KEY(source_id,hash));""")
        existing = self.get("snapshot_hash")
        if existing is not None and existing != snapshot_hash:
            raise ArchiveError("Staging artifact belongs to a different snapshot")
        self.set("snapshot_hash", snapshot_hash)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def get(self, name: str) -> str | None:
        row = self.db.execute("SELECT value FROM progress WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    def set(self, name: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO progress VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
            (name, value),
        )

    def stage(self, store: ArchiveStore, manifest_hash: str) -> None:
        completed = int(self.get("response_cursor") or "0")
        for ordinal, (entry, response) in enumerate(archived_responses(store, manifest_hash)):
            if ordinal < completed:
                continue
            kind = entry["kind"]
            with self.db:
                for raw in response["records"]:
                    if kind in {"histories", "latest", "originals"}:
                        external = identifier(raw["occurrence_no"], "occ")
                        if kind == "histories":
                            external += ":" + identification_key(raw)
                    elif kind in FIELDS:
                        _, field, prefix = FIELDS[kind]
                        external = (
                            str(raw[field]) if kind == "taxa" else identifier(raw[field], prefix)
                        )
                    else:
                        continue
                    self.db.execute(
                        "INSERT OR IGNORE INTO input VALUES(?,?,?,?)",
                        (kind, external, digest(raw), canonical_bytes(raw).decode()),
                    )
                self.set("response_cursor", str(ordinal + 1))

    def add(self, kind: str, external: str, raw: dict[str, Any], evidence: Any) -> None:
        content_hash = digest(raw)
        old = self.db.execute(
            "SELECT hash FROM record WHERE kind=? AND external=?", (kind, external)
        ).fetchone()
        if old is not None and old[0] != content_hash:
            raise ArchiveError(f"Conflicting source identity {kind}:{external}")
        self.db.execute(
            """INSERT OR IGNORE INTO record
          (kind,external,source_id,raw,hash,evidence) VALUES(?,?,?,?,?,?)""",
            (
                kind,
                external,
                str(record_id(kind, external)),
                canonical_bytes(raw).decode(),
                content_hash,
                canonical_bytes(json_value(evidence)).decode(),
            ),
        )

    def prepare_records(self, header: dict[str, Any], batch_size: int = 256) -> dict[str, int]:
        if self.get("records_ready"):
            return self.counts()
        for response_kind, (kind, _, _) in FIELDS.items():
            cursor = self.db.execute(
                "SELECT DISTINCT external FROM input WHERE kind=? ORDER BY external",
                (response_kind,),
            )
            for item in cursor:
                views = [
                    json.loads(r[0])
                    for r in self.db.execute(
                        "SELECT raw FROM input WHERE kind=? AND external=? ORDER BY hash",
                        (response_kind, item[0]),
                    )
                ]
                raw = views[0]
                if kind == "collection" and header["scope"]["mode"] in {"canary", "full-florida"}:
                    if not is_florida_context(raw):
                        raise ArchiveError("Non-Florida collection in pinned Florida scope")
                if len(views) > 1:
                    if kind != "opinion":
                        raise ArchiveError(f"Conflicting repeated provider {kind} {item[0]}")
                    contextual = {"orig_no", "taxon_name", "child_name", "opinion_type"}
                    common = {k: v for k, v in raw.items() if k not in contextual}
                    if any(
                        {k: v for k, v in view.items() if k not in contextual} != common
                        for view in views
                    ):
                        raise ArchiveError("Conflicting substantive provider opinion")
                    raw = {**common, "export_views": sorted(views, key=digest)}
                normalizer = NORMALIZERS.get(kind)
                self.add(kind, item[0], raw, asdict(normalizer(raw)) if normalizer else raw)
        self.db.commit()
        cursor = self.db.execute(
            "SELECT DISTINCT external FROM input WHERE kind='latest' ORDER BY external"
        )
        while items := cursor.fetchmany(batch_size):
            ids = [r[0] for r in items]
            placeholders = ",".join("?" for _ in ids)
            latest = [
                json.loads(r[0])
                for r in self.db.execute(
                    f"SELECT raw FROM input WHERE kind='latest' AND external IN ({placeholders})",
                    ids,
                )
            ]
            originals = [
                json.loads(r[0])
                for r in self.db.execute(
                    "SELECT raw FROM input WHERE kind='originals' "
                    f"AND external IN ({placeholders})",
                    ids,
                )
            ]
            histories = [
                json.loads(r[0])
                for r in self.db.execute(
                    "SELECT raw FROM input WHERE kind='histories' "
                    f"AND substr(external,1,instr(external,':')-1) IN ({placeholders})",
                    ids,
                )
            ]
            for occurrence in normalize_occurrences(histories, latest, originals):
                members = [
                    r[0]
                    for r in self.db.execute(
                        """SELECT external FROM record INDEXED BY record_occurrence_membership
                  WHERE kind='material' AND json_extract(raw,'$.occurrence_no') IN (?,?)
                  ORDER BY external""",
                        (occurrence.id, "occ:" + occurrence.id),
                    )
                ]
                evidence = {
                    "occurrence_id": occurrence.id,
                    "collection_id": occurrence.collection_id,
                    "history_complete": occurrence.complete_history,
                    "original_identification": occurrence.original.raw,
                    "latest_identification": occurrence.latest.raw,
                    "identification_history": [i.raw for i in occurrence.identifications],
                    "material_membership": members,
                }
                self.add("occurrence", occurrence.id, occurrence.latest.raw, evidence)
                for ident in occurrence.identifications:
                    self.add("identification", f"{occurrence.id}:{ident.id}", ident.raw, ident.raw)
                self.db.execute(
                    "INSERT OR REPLACE INTO occurrence VALUES(?,?)",
                    (occurrence.id, canonical_bytes(asdict(occurrence)).decode()),
                )
            self.db.commit()
        counts = self.counts()
        latest_count = self.db.execute("SELECT count(*) FROM input WHERE kind='latest'").fetchone()[
            0
        ]
        original_count = self.db.execute(
            "SELECT count(*) FROM input WHERE kind='originals'"
        ).fetchone()[0]
        history_occ_count = self.db.execute("""SELECT count(
          DISTINCT substr(external,1,instr(external,':')-1))
          FROM input WHERE kind='histories'""").fetchone()[0]
        if (
            counts.get("occurrence") != latest_count
            or latest_count != original_count
            or latest_count != history_occ_count
        ):
            raise ArchiveError("Incomplete or conflicting provider identification populations")
        scope = header["scope"]
        if scope.get("occurrence_ids") and latest_count != len(scope["occurrence_ids"]):
            raise ArchiveError("Incomplete pinned occurrence population")
        if scope.get("mode") == "global" or header.get("counts_before") is not None:
            before, after = header.get("counts_before"), header.get("counts_after")
            if not before or before != after:
                raise ArchiveError("Missing/changed global provider completeness controls")
            if set(before) != {"occurrence", "identification", *(v[0] for v in FIELDS.values())}:
                raise ArchiveError("Global completeness controls must cover every retained kind")
            for kind, total in before.items():
                if counts.get(kind, 0) != total:
                    raise ArchiveError(
                        f"Incomplete global provider {kind}: {counts.get(kind, 0)} != {total}"
                    )
            if not scope.get("complete_scope") or not counts.get("occurrence"):
                raise ArchiveError(
                    "Global publication requires a complete nonempty occurrence scope"
                )
        self.set("records_ready", "1")
        self.db.commit()
        return counts

    def counts(self) -> dict[str, int]:
        return {
            r[0]: r[1] for r in self.db.execute("SELECT kind,count(*) FROM record GROUP BY kind")
        }

    def prepare_edges(self) -> None:
        if self.get("edges_ready"):
            return
        for r in self.db.execute("SELECT k,kind,raw FROM record ORDER BY k"):
            raw = json.loads(r["raw"])
            if r["kind"] in {"taxon", "opinion"}:
                fields = (
                    ("orig_no", "taxon_no")
                    if r["kind"] == "taxon"
                    else ("orig_no", "child_spelling_no")
                )
                for view in raw.get("export_views", [raw]):
                    for field in fields:
                        if value := optional_identifier(view.get(field), "txn"):
                            self.db.execute(
                                "INSERT OR IGNORE INTO alias VALUES(?,?,?)",
                                (r["kind"], value, r["k"]),
                            )
            if r["kind"] == "interval":
                self.db.execute(
                    "INSERT OR IGNORE INTO alias VALUES('interval',?,?)",
                    (raw["interval_name"], r["k"]),
                )
        self.db.commit()

        def link(owner: int, kind: str, external: str) -> None:
            target = self.db.execute(
                "SELECT k FROM record WHERE kind=? AND external=?", (kind, external)
            ).fetchone()
            if target is None:
                raise ArchiveError(f"Missing typed dependency {kind}:{external}")
            self.db.execute("INSERT OR IGNORE INTO direct VALUES(?,?)", (owner, target[0]))

        for r in self.db.execute("SELECT * FROM record ORDER BY k"):
            k, kind, external = r["k"], r["kind"], r["external"]
            raw = json.loads(r["raw"])
            if kind != "reference" and (ref := optional_identifier(raw.get("reference_no"), "ref")):
                link(k, "reference", ref)
            if kind == "collection":
                for field in ("early_interval", "late_interval"):
                    if name := raw.get(field):
                        targets = self.db.execute(
                            "SELECT target FROM alias WHERE kind='interval' AND value=?", (name,)
                        ).fetchall()
                        if not targets:
                            raise ArchiveError("Missing provider interval dependency")
                        self.db.executemany(
                            "INSERT OR IGNORE INTO direct VALUES(?,?)", ((k, t[0]) for t in targets)
                        )
            if kind == "interval" and raw.get("scale_no"):
                link(k, "timescale", identifier(raw["scale_no"], "tsc"))
            if kind in {"identification", "material"}:
                for field in ("identified_no", "accepted_no"):
                    if value := optional_identifier(raw.get(field), "txn"):
                        self.db.execute(
                            """INSERT OR IGNORE INTO direct SELECT ?,target FROM alias
                          WHERE kind IN ('taxon','opinion') AND value=?""",
                            (k, value),
                        )
            if kind == "occurrence":
                evidence = json.loads(r["evidence"])
                link(k, "collection", evidence["collection_id"])
                for ident in evidence["identification_history"]:
                    link(k, "identification", external + ":" + identification_key(ident))
                for material in evidence["material_membership"]:
                    link(k, "material", material)
            if kind == "material":
                owner = self.db.execute(
                    "SELECT k FROM record WHERE kind='occurrence' AND external=?",
                    (identifier(raw["occurrence_no"], "occ"),),
                ).fetchone()
                if owner is None:
                    raise ArchiveError("Material outside selected occurrence population")
                self.db.execute("INSERT OR IGNORE INTO direct VALUES(?,?)", (owner[0], k))
                self.db.execute(
                    """INSERT OR IGNORE INTO direct SELECT ?,k FROM record
                  INDEXED BY record_material_membership
                  WHERE kind='measurement' AND json_extract(raw,'$.specimen_no') IN (?,?)""",
                    (k, external, "spm:" + external),
                )
            if kind == "measurement":
                if (
                    self.db.execute(
                        "SELECT 1 FROM record WHERE kind='material' AND external=?",
                        (identifier(raw["specimen_no"], "spm"),),
                    ).fetchone()
                    is None
                ):
                    raise ArchiveError("Measurement missing material dependency")
        self.set("edges_ready", "1")
        self.db.commit()

    def normalize(self, batch_size: int = 256) -> Iterator[int]:
        cursor = int(self.get("normalization_cursor") or "0")
        while batch := self.db.execute(
            "SELECT * FROM record WHERE k>? ORDER BY k LIMIT ?", (cursor, batch_size)
        ).fetchall():
            with self.db:
                for row in batch:
                    deps = self.db.execute(
                        """WITH RECURSIVE closure(target) AS (
                      SELECT target FROM direct WHERE owner=? AND target<>?
                      UNION SELECT d.target FROM direct d JOIN closure c ON d.owner=c.target
                        WHERE d.target<>?) SELECT target FROM closure""",
                        (row["k"], row["k"], row["k"]),
                    ).fetchmany(50001)
                    if len(deps) > 50000:
                        raise ArchiveError(
                            "Pathological proof fanout exceeds explicit per-record bound"
                        )
                    self.db.executemany(
                        "INSERT OR IGNORE INTO proof VALUES(?,?)", ((row["k"], d[0]) for d in deps)
                    )
                    frame = [
                        tuple(r)
                        for r in self.db.execute(
                            """SELECT r.source_id,r.hash FROM proof p
                      JOIN record r ON r.k=p.target WHERE p.owner=? ORDER BY r.source_id,r.hash""",
                            (row["k"],),
                        )
                    ]
                    payload = {
                        "record_type": row["kind"],
                        "external_id": row["external"],
                        "evidence": json.loads(row["evidence"]),
                        "dependencies": frame,
                    }
                    norm = digest({"adapter": ADAPTER_VERSION, "payload": payload})
                    self.db.execute(
                        "UPDATE record SET normalization_hash=? WHERE k=?", (norm, row["k"])
                    )
                cursor = batch[-1]["k"]
                self.set("normalization_cursor", str(cursor))
            yield cursor

    def raw_records(self) -> Iterator[dict[str, Any]]:
        for r in self.db.execute("SELECT source_id,hash,raw FROM record ORDER BY source_id"):
            yield {"source_record_id": r[0], "content_hash": r[1], "raw": json.loads(r[2])}

    def verified_normalization(self, row: sqlite3.Row) -> dict[str, Any]:
        """Recheck cached scientific bytes and complete proof before bulk copying."""
        frame = self.db.execute(
            """SELECT r.source_id,r.hash FROM proof p JOIN record r ON r.k=p.target
              WHERE p.owner=? ORDER BY r.source_id,r.hash""",
            (row["k"],),
        ).fetchmany(50001)
        if len(frame) > 50000:
            raise ArchiveError("Staged normalization exceeds complete proof fanout bound")
        payload = {
            "record_type": row["kind"],
            "external_id": row["external"],
            "evidence": json.loads(row["evidence"]),
            "dependencies": [tuple(r) for r in frame],
        }
        if digest(json.loads(row["raw"])) != row["hash"]:
            raise ArchiveError("Cached staged raw evidence hash differs")
        if digest({"adapter": ADAPTER_VERSION, "payload": payload}) != row["normalization_hash"]:
            raise ArchiveError("Cached staged normalization hash differs")
        return payload
