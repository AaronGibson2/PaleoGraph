"""Bounded Florida-identity PBDB parent closure and immutable offline replay.

This enriches source taxonomy in additive tables. It never writes occurrences,
Taxons, source revisions, reconciliations, or the existing Design C archives.
"""

import argparse
import json
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode

from sqlalchemy import insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.discovery.occurrence_browse import eligibility, query_parameters
from app.ingestion.archive import (
    ArchiveStore,
    LocalArchiveStore,
    canonical_bytes,
    publish_manifest,
    read_object,
    sha,
    verify_archive,
    write_object,
)
from app.ingestion.pbdb import PROVIDER, SERVICE, decode_response, digest
from app.ingestion.pbdb_snapshot import chunks, http_get
from app.models import (
    PbdbTaxonomyDependency,
    PbdbTaxonomyHead,
    PbdbTaxonomyRecord,
    PbdbTaxonomySnapshot,
)
from app.taxonomy.pbdb_hierarchy import actual_parent, provider_id

VERSION = "pbdb-florida-parent-closure-v1"
MAX_CONCEPTS = 50000
PAGE_SIZE = 1000
FIELDS = {
    "orig_no",
    "taxon_no",
    "taxon_name",
    "taxon_rank",
    "parent_no",
    "parent_name",
    "immpar_no",
    "immpar_name",
    "accepted_no",
    "accepted_name",
    "accepted_rank",
    "difference",
    "taxon_attr",
    "accepted_attr",
    "reference_no",
    "primary_reference",
    "created",
    "modified",
    "flags",
    "is_extant",
}


def seeds(session: Session) -> tuple[set[str], list[dict[str, Any]]]:
    """Deduplicate provider IDs before transport, never one request per occurrence."""
    raw = session.scalars(
        text(f"""SELECT nr.payload->'evidence'->'latest_identification'
      FROM catalog_entry ce JOIN normalized_source_revision nr
      ON nr.source_record_id=ce.source_record_id AND nr.content_hash=ce.content_hash
      AND nr.normalization_hash=ce.normalization_hash WHERE {eligibility("pbdb")}"""),
        query_parameters(),
    ).all()
    ids = {
        identity
        for row in raw
        for key in ("identified_no", "accepted_no")
        if (identity := provider_id((row or {}).get(key)))
    }
    retained = [
        dict(row)
        for row in session.execute(
            text("""SELECT id,content_hash,
      raw_payload raw FROM source_record WHERE record_type='taxon' ORDER BY id""")
        ).mappings()
    ]
    return ids, retained


class Acquisition:
    def __init__(
        self,
        store: ArchiveStore,
        checkpoint: Path,
        transport: Callable[[str], bytes] = http_get,
        delay: float = 0.2,
    ):
        self.store, self.checkpoint = store, checkpoint
        self.transport, self.delay = transport, delay
        checkpoint.mkdir(parents=True, exist_ok=True)
        self.files: dict[str, dict[str, Any]] = {}
        self.requests: dict[str, dict[str, Any]] = {}
        self.missing: set[str] = set()
        self.network_requests = 0

    def request(self, operation: str, ids: Iterable[str], **extra: Any) -> list[dict[str, Any]]:
        values = sorted(set(ids))
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for offset in range(0, MAX_CONCEPTS + PAGE_SIZE, PAGE_SIZE):
            parameters = {
                "taxon_id": ",".join(values),
                "vocab": "pbdb",
                "extids": "yes",
                "strict": "yes",
                "datainfo": "yes",
                "limit": PAGE_SIZE,
                "offset": offset,
                **extra,
            }
            url = SERVICE + operation + ".json?" + urlencode(parameters)
            key = sha(url.encode())
            cache = self.checkpoint / (key + ".json")
            if cache.exists():
                entry = json.loads(cache.read_bytes())
                raw = read_object(self.store, entry["object"])
            else:
                raw = self.transport(url)
                response = decode_response(raw, parameters)
                obj = write_object(
                    self.store, raw, kind="pbdb-taxonomy-response", records=len(response["records"])
                )
                entry = {
                    "url": url,
                    "parameters": parameters,
                    "object": obj,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                }
                cache.write_bytes(canonical_bytes(entry))
                self.network_requests += 1
                time.sleep(self.delay)
            response = decode_response(raw, parameters)
            rows = response["records"]
            if len(rows) > PAGE_SIZE:
                raise ValueError("PBDB ignored bounded page size")
            page_hash = digest(rows)
            if rows and page_hash in seen:
                raise ValueError("PBDB repeated a page; closure cannot be certified")
            seen.add(page_hash)
            self.files[entry["object"]["hash"]] = entry["object"]
            self.requests[key] = entry
            output.extend(
                {
                    **row,
                    "proof": {
                        "object": entry["object"]["hash"],
                        "ordinal": ordinal,
                        "row_hash": digest(row),
                        "request": key,
                    },
                }
                for ordinal, row in enumerate(rows)
            )
            if len(rows) < PAGE_SIZE:
                return output
        raise ValueError("PBDB paging exceeded Florida taxonomy bound")

    def taxa(self, ids: Iterable[str]) -> list[dict[str, Any]]:
        values = sorted(set(ids) - self.missing)
        if not values:
            return []
        try:
            return self.request("taxa/list", values, rel="exact", show="immparent,attr,ref,crmod")
        except ValueError as error:
            cause = error.__cause__
            if not isinstance(cause, HTTPError) or cause.code != 404:
                raise
            # A rejected selector fails the entire provider batch. Isolate it;
            # do not silently turn var: into txn: or vice versa.
            if len(values) == 1:
                body = cause.read(1024 * 1024)
                obj = write_object(self.store, body, kind="pbdb-taxonomy-rejection", records=0)
                self.files[obj["hash"]] = obj
                self.missing.add(values[0])
                return []
            middle = len(values) // 2
            return self.taxa(values[:middle]) + self.taxa(values[middle:])

    def acquire(self, referenced: set[str], retained: list[dict[str, Any]]) -> str:
        records: dict[str, dict[str, Any]] = {}
        retained_rows = []
        for revision in retained:
            raw = revision["raw"]
            if digest(raw) != revision["content_hash"]:
                raise ValueError("Retained PBDB taxonomy revision hash mismatch")
            variant = provider_id(raw.get("taxon_no"))
            if not variant:
                continue
            retained_rows.append(
                {
                    "source_record_id": str(revision["id"]),
                    "content_hash": revision["content_hash"],
                    "raw": raw,
                }
            )
            records[variant] = {key: value for key, value in raw.items() if key in FIELDS}
            records[variant]["proof"] = {
                "source_record_id": str(revision["id"]),
                "content_hash": revision["content_hash"],
            }
        for group in chunks(retained_rows_index(retained_rows), 500):
            rows = [retained_rows[int(index)] for index in group]
            obj = write_object(
                self.store,
                b"\n".join(canonical_bytes(row) for row in rows) + b"\n",
                kind="pbdb-retained-taxonomy",
                records=len(rows),
            )
            self.files[obj["hash"]] = obj
        pending, attempted = set(referenced), set()
        for round_number in range(512):
            if not pending:
                break
            groups = list(chunks({item for item in pending if item.startswith("txn:")}))
            groups += list(chunks({item for item in pending if item.startswith("var:")}))
            for group in groups:
                rows = self.taxa(group)
                for row in rows:
                    variant, concept = (
                        provider_id(row.get("taxon_no")),
                        provider_id(row.get("orig_no")),
                    )
                    if not variant or not concept or not row.get("taxon_name"):
                        raise ValueError("PBDB taxon response lacks identity/name")
                    payload = {
                        key: value for key, value in row.items() if key in FIELDS | {"proof"}
                    }
                    records[variant] = payload
                    alias = "txn:" + variant[4:]
                    if alias in group and alias != concept:
                        # PBDB can resolve a txn selector to an exact spelling
                        # whose orig_no differs. This mapping is witnessed by
                        # the unchanged exact request and returned variant ID.
                        records[alias] = {
                            **payload,
                            "selector_resolution": {
                                "requested": alias,
                                "orig_no": concept,
                                "taxon_no": variant,
                            },
                        }
                    # txn selectors mean the current variant; historical spelling
                    # rows must never overwrite a canonical current mapping.
                    if concept in group:
                        existing = records.get(concept)
                        if existing and existing["taxon_no"] != variant:
                            raise ValueError("Conflicting current PBDB variants")
                        records[concept] = payload
                print(
                    json.dumps(
                        {
                            "round": round_number,
                            "requests": len(self.requests),
                            "selectors": len(records),
                            "pending": len(pending),
                        }
                    ),
                    flush=True,
                )
            attempted |= pending
            # Explicit retained variant->orig mappings can recover rejected txn
            # selectors only by recording that source identity routing separately.
            for identity in self.missing:
                aliases = [row for row in records.values() if row.get("orig_no") == identity]
                if aliases and identity not in records:
                    choices = sorted(
                        aliases, key=lambda row: ("V" in row.get("flags", ""), row["taxon_no"])
                    )
                    records[identity] = {
                        **choices[0],
                        "routing": "retained explicit orig_no alias; "
                        "provider rejected current selector",
                    }
            targets = {
                target
                for row in records.values()
                for target in (actual_parent(row), provider_id(row.get("accepted_no")))
                if target
            }
            pending = (targets | referenced) - records.keys() - attempted
            if len(records) + len(pending) > MAX_CONCEPTS:
                raise ValueError("Florida ancestor closure exceeded concept bound")
        else:
            raise ValueError("PBDB parent frontier exceeded depth bound")
        concepts = {row["orig_no"] for row in records.values()}
        opinions: dict[str, list[dict[str, Any]]] = {}
        for group in chunks(concepts - self.missing):
            rows = self.request("taxa/opinions", group, op_type="class", show="basis,ref,crmod")
            for row in rows:
                opinions.setdefault(str(row.get("orig_no")), []).append(row)
            print(
                json.dumps({"stage": "classification-opinions", "requests": len(self.requests)}),
                flush=True,
            )
        for row in records.values():
            row["classification_opinions"] = opinions.get(row["orig_no"], [])
        # Parent absence on a species/family remains partial. For a supplied
        # broad unranked clade only, confirm the provider's graph boundary with
        # a separate exact-identity immediate-parent query; never guess by name.
        boundaries = {
            row["orig_no"]
            for row in records.values()
            if actual_parent(row) is None and row.get("taxon_rank") == "unranked clade"
        }
        for concept in sorted(boundaries):
            parents = self.request("taxa/list", [concept], rel="immpar", show="immparent")
            if not parents:
                entry_key, entry = next(
                    (key, value)
                    for key, value in self.requests.items()
                    if value["parameters"]["taxon_id"] == concept
                    and value["parameters"].get("rel") == "immpar"
                )
                for row in records.values():
                    if row["orig_no"] == concept:
                        row["terminal_boundary"] = {
                            "request": entry_key,
                            "object": entry["object"]["hash"],
                        }
        snapshot = digest(
            {"version": VERSION, "referenced": sorted(referenced), "records": records}
        )
        graph = write_object(
            self.store, canonical_bytes(records), kind="pbdb-taxonomy-graph", records=len(records)
        )
        self.files[graph["hash"]] = graph
        manifest = {
            "format": "paleograph-source-archive-v1",
            "provider": PROVIDER,
            "snapshot_hash": snapshot,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "scope": {"mode": "florida-taxonomy-ancestors", "referenced": sorted(referenced)},
            "adapter_version": VERSION,
            "policy_version": VERSION,
            "rights": {
                "license": "CC0",
                "url": "https://creativecommons.org/publicdomain/zero/1.0/",
            },
            "files": sorted(self.files.values(), key=lambda item: item["hash"]),
            "requests": self.requests,
            "unresolved_selectors": sorted(self.missing),
            "counts": {
                "raw_revisions": 0,
                "referenced_ids": len(referenced),
                "concepts": len(concepts),
                "selectors": len(records),
            },
            "migration": None,
        }
        manifest_hash = publish_manifest(self.store, manifest)
        (self.checkpoint / "complete.json").write_bytes(
            canonical_bytes({"manifest_hash": manifest_hash})
        )
        return manifest_hash


def retained_rows_index(rows: list[dict[str, Any]]) -> Iterable[str]:
    return (str(index) for index in range(len(rows)))


def replay(session: Session, store: ArchiveStore, manifest_hash: str) -> dict[str, Any]:
    """READY/hash verification precedes atomic source-graph + browse publication."""
    manifest = verify_archive(store, manifest_hash)
    if (
        manifest.get("adapter_version") != VERSION
        or manifest["scope"]["mode"] != "florida-taxonomy-ancestors"
    ):
        raise ValueError("Unsupported PBDB taxonomy archive scope/version")
    graph_files = [entry for entry in manifest["files"] if entry["kind"] == "pbdb-taxonomy-graph"]
    if len(graph_files) != 1:
        raise ValueError("PBDB taxonomy archive must contain exactly one graph")
    records = json.loads(read_object(store, graph_files[0]))
    snapshot = digest(
        {"version": VERSION, "referenced": manifest["scope"]["referenced"], "records": records}
    )
    if snapshot != manifest["snapshot_hash"]:
        raise ValueError("PBDB taxonomy graph identity mismatch")
    verify_proofs(store, manifest, records)
    from app.taxonomy.build import rebuild

    with session.begin_nested():
        session.execute(text("SELECT pg_advisory_xact_lock(74003001)"))
        session.execute(text("SELECT pg_advisory_xact_lock(74003501)"))
        exists = session.get(PbdbTaxonomySnapshot, snapshot)
        if not exists:
            session.add(
                PbdbTaxonomySnapshot(
                    hash=snapshot,
                    manifest_hash=manifest_hash,
                    storage_reference=store.reference,
                    manifest=manifest,
                )
            )
            session.flush()
            rows = [
                {
                    "snapshot_hash": snapshot,
                    "selector": selector,
                    "concept_id": row["orig_no"],
                    "payload": row,
                }
                for selector, row in sorted(records.items())
            ]
            for start in range(0, len(rows), 500):
                session.execute(insert(PbdbTaxonomyRecord), rows[start : start + 500])
            dependencies = [
                {
                    "snapshot_hash": snapshot,
                    "selector": selector,
                    "relationship": relationship,
                    "target": target,
                }
                for selector, row in sorted(records.items())
                for relationship, target in (
                    ("actual-parent", actual_parent(row)),
                    ("accepted-name", provider_id(row.get("accepted_no"))),
                )
                if target in records and target != selector
            ]
            for start in range(0, len(dependencies), 500):
                session.execute(insert(PbdbTaxonomyDependency), dependencies[start : start + 500])
        session.execute(
            pg_insert(PbdbTaxonomyHead)
            .values(scope="florida", snapshot_hash=snapshot)
            .on_conflict_do_update(index_elements=["scope"], set_={"snapshot_hash": snapshot})
        )
        result = rebuild(session)
    return {
        **result,
        "snapshot_hash": snapshot,
        "manifest_hash": manifest_hash,
        "source_graph_counts": manifest["counts"],
    }


def verify_proofs(
    store: ArchiveStore, manifest: dict[str, Any], records: dict[str, dict[str, Any]]
) -> None:
    """Verify graph fields against raw responses or retained immutable revisions."""
    objects = {entry["hash"]: entry for entry in manifest["files"]}
    responses: dict[str, list[dict[str, Any]]] = {}
    retained: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in manifest["files"]:
        if entry["kind"] == "pbdb-retained-taxonomy":
            for line in read_object(store, entry).splitlines():
                row = json.loads(line)
                if digest(row["raw"]) != row["content_hash"]:
                    raise ValueError("Retained taxonomy archive revision mismatch")
                retained[row["source_record_id"], row["content_hash"]] = row["raw"]

    def source(proof: dict[str, Any]) -> dict[str, Any]:
        if "object" in proof:
            key = proof["object"]
            if key not in responses:
                responses[key] = json.loads(read_object(store, objects[key]))["records"]
            raw_row: dict[str, Any] = responses[key][int(proof["ordinal"])]
            if digest(raw_row) != proof["row_hash"]:
                raise ValueError("PBDB taxonomy proof row hash mismatch")
            return raw_row
        result: dict[str, Any] = retained[proof["source_record_id"], proof["content_hash"]]
        return result

    for selector, row in records.items():
        if selector not in {row["orig_no"], row["taxon_no"]}:
            resolution = row.get("selector_resolution", {})
            request = manifest["requests"].get(row["proof"].get("request"), {})
            parameters = request.get("parameters", {})
            if (
                resolution.get("requested") != selector
                or resolution.get("orig_no") != row["orig_no"]
                or resolution.get("taxon_no") != row["taxon_no"]
                or selector not in parameters.get("taxon_id", "").split(",")
                or parameters.get("rel") != "exact"
                or selector != "txn:" + row["taxon_no"][4:]
            ):
                raise ValueError("PBDB selector resolution lacks exact-response proof")
        if boundary := row.get("terminal_boundary"):
            entry = manifest["requests"][boundary["request"]]
            if (
                entry["parameters"]["taxon_id"] != row["orig_no"]
                or entry["parameters"].get("rel") != "immpar"
                or entry["object"]["hash"] != boundary["object"]
                or json.loads(read_object(store, objects[boundary["object"]]))["records"]
            ):
                raise ValueError("PBDB terminal boundary proof mismatch")
        original = source(row["proof"])
        if {key: value for key, value in row.items() if key in FIELDS} != {
            key: value for key, value in original.items() if key in FIELDS
        }:
            raise ValueError("PBDB taxonomy graph disagrees with raw proof")
        for opinion in row.get("classification_opinions", []):
            if {key: value for key, value in opinion.items() if key != "proof"} != source(
                opinion["proof"]
            ):
                raise ValueError("PBDB classification opinion disagrees with raw proof")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--replay", help="Verified manifest hash; no network access")
    args = parser.parse_args()
    from app.config import Settings
    from app.db import create_db_engine

    engine = create_db_engine(Settings())
    store = LocalArchiveStore(args.archive)
    try:
        with Session(engine) as session:
            if args.replay:
                result = replay(session, store, args.replay)
                session.commit()
                print(json.dumps(result))
            else:
                ids, retained = seeds(session)
                session.rollback()
                manifest_hash = Acquisition(store, args.checkpoint).acquire(ids, retained)
                print(json.dumps({"manifest_hash": manifest_hash}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
