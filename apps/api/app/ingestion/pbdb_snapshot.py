"""Bounded, retained public PBDB acquisition; no database access or interactive dependency."""

import argparse
import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from app.config import REPO_ROOT
from app.ingestion.metrics import peak_memory_bytes
from app.ingestion.pbdb import (
    ADAPTER_VERSION,
    DATASET,
    SERVICE,
    Snapshot,
    decode_response,
    digest,
    identifier,
    is_florida_context,
    optional_identifier,
)

OCCURRENCE_BLOCKS = "attr,class,classext,abund,coords,coll,loc,strat,methods,ident,rem,crmod"
COLLECTION_BLOCKS = "loc,paleoloc,strat,stratext,methods,ages,rem,crmod"
MAX_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 50000


class UnknownTaxon(ValueError):
    def __init__(self, number: str) -> None:
        self.concept = f"txn:{number}"
        super().__init__(f"Provider rejects resolved concept {self.concept}")


def http_get(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "PaleoGraph-PBDB-adapter/1.0 (retained public Florida scientific export)",
            "Accept": "application/json",
        },
    )
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:
                if not response.geturl().startswith(SERVICE):
                    raise ValueError("Changed PBDB response provider URL")
                if response.status != 200:
                    raise ValueError("Unexpected PBDB response status")
                data = bytes(response.read(MAX_BYTES + 1))
                if len(data) > MAX_BYTES:
                    raise ValueError("PBDB response exceeds retained canary size bound")
                return data
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise ValueError(f"PBDB HTTP {error.code}") from error
            retry = error.headers.get("Retry-After", "")
            delay = min(60, max(2**attempt, int(retry))) if retry.isdigit() else 2**attempt
            time.sleep(delay)
        except (URLError, TimeoutError) as error:
            if attempt == 2:
                raise ValueError("PBDB transport failed after bounded retries") from error
            time.sleep(2**attempt)
    raise RuntimeError("Unreachable retry state")


def chunks(values: Iterable[str], size: int = 100) -> Iterable[list[str]]:
    ordered = sorted(set(values), key=lambda value: (int(value.rsplit(":", 1)[-1]), value))
    for offset in range(0, len(ordered), size):
        yield ordered[offset : offset + size]


class CanaryAcquisition:
    def __init__(
        self,
        root: Path,
        *,
        transport: Callable[[str], bytes] = http_get,
        resume: Path | None = None,
    ) -> None:
        self.root = root.resolve()
        self.transport = transport
        self.entries: list[dict[str, Any]] = []
        self.responses: dict[str, list[dict[str, Any]]] = {}
        self.started = datetime.now(UTC).isoformat()
        self.retained: dict[str, tuple[dict[str, Any], Path]] = {}
        self.network_requests = 0
        self.routing_exceptions: list[dict[str, str]] = []
        self.failed_requests = 0
        if resume:
            retained_root = resume.resolve()
            journal = json.loads((retained_root / "acquisition-journal.json").read_bytes())
            for entry in journal["responses"]:
                path = (retained_root / entry["file"]).resolve()
                if path.parent != retained_root:
                    raise ValueError("Invalid resume response path")
                self.retained[entry["url"]] = (entry, path)
            if self.retained:
                self.started = min(entry["retrieved_at"] for entry, _ in self.retained.values())
        self.root.mkdir(parents=True, exist_ok=False)

    def request(
        self, kind: str, operation: str, *, fresh: bool = False, **parameters: Any
    ) -> list[dict[str, Any]]:
        parameters = {
            "vocab": "pbdb",
            "extids": "yes",
            "datainfo": "yes",
            "rowcount": "yes",
            "strict": "yes",
            **parameters,
        }
        url = SERVICE + operation + ".json?" + urlencode(parameters)
        cached = None if fresh else self.retained.get(url)
        if cached:
            metadata, retained_file = cached
            raw = retained_file.read_bytes()
            if (
                len(raw) != metadata["bytes"]
                or hashlib.sha256(raw).hexdigest() != metadata["sha256"]
            ):
                raise ValueError("Changed retained resume response bytes")
        else:
            self.network_requests += 1
            try:
                raw = self.transport(url)
            except Exception as error:
                cause = error.__cause__
                self.failed_requests += 1
                prefix = f"failed-{self.failed_requests:03d}"
                diagnostic: dict[str, Any] = {
                    "url": url,
                    "parameters": parameters,
                    "kind": kind,
                    "error": f"{type(error).__name__}: {error}",
                }
                unknown = None
                if isinstance(cause, HTTPError):
                    body = cause.read(MAX_BYTES + 1)
                    (self.root / f"{prefix}-http-response.bin").write_bytes(body)
                    diagnostic.update(
                        status=cause.code, bytes=len(body), sha256=hashlib.sha256(body).hexdigest()
                    )
                    if cause.code == 404 and kind in {"taxa", "opinions"}:
                        try:
                            failure = json.loads(body)
                            errors = failure.get("errors")
                            if (
                                failure.get("status_code") == 404
                                and isinstance(errors, list)
                                and len(errors) == 1
                            ):
                                unknown = re.fullmatch(r"Unknown taxon '(\d+)'", errors[0])
                        except (ValueError, TypeError, AttributeError):
                            pass
                (self.root / f"{prefix}-request.json").write_text(
                    json.dumps(diagnostic, indent=2) + "\n", encoding="utf8"
                )
                if unknown:
                    raise UnknownTaxon(unknown.group(1)) from error
                raise
        name = f"{len(self.entries):03d}-{kind}.json"
        (self.root / name).write_bytes(raw)
        entry = {
            "kind": kind,
            "file": name,
            "url": url,
            "parameters": parameters,
            "retrieved_at": cached[0]["retrieved_at"] if cached else datetime.now(UTC).isoformat(),
            "status": 200,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            **({"reused_from": str(cached[1])} if cached else {}),
        }
        self.entries.append(entry)
        (self.root / "acquisition-journal.json").write_text(
            json.dumps({"complete_scope": False, "responses": self.entries}, indent=2) + "\n",
            encoding="utf8",
        )
        response = decode_response(raw, parameters, history=kind == "histories")
        rows: list[dict[str, Any]] = response["records"]
        if len(rows) > MAX_RECORDS:
            raise ValueError("PBDB dependency export exceeds bounded canary record count")
        self.responses.setdefault(kind, []).extend(rows)
        if len(self.entries) % 25 == 0 or len(self.responses[kind]) == len(rows):
            print(
                json.dumps(
                    {
                        "stage": kind,
                        "requests": len(self.entries),
                        "rows": len(self.responses[kind]),
                        "retained_bytes": sum(item["bytes"] for item in self.entries),
                    }
                ),
                flush=True,
            )
        if not cached:
            time.sleep(0.2)
        return rows

    def export_ids(
        self,
        kind: str,
        operation: str,
        selector: str,
        ids: Iterable[str],
        *,
        show: str = "",
        **extra: Any,
    ) -> None:
        for group in chunks(ids):
            parameters: dict[str, Any] = {selector: ",".join(group), "limit": "all", **extra}
            if show:
                parameters["show"] = show
            self.request(kind, operation, **parameters)

    def export_taxonomy(self, taxon_ids: Iterable[str]) -> None:
        self.export_ids("taxon-resolution", "taxa/list", "id", taxon_ids, rel="exact")
        # Resolve concept IDs before variants: alias batches can differ in B flags.
        resolutions = self.responses.get("taxon-resolution", [])
        if not resolutions or any(
            not optional_identifier(row.get("orig_no"), "txn") for row in resolutions
        ):
            raise ValueError("Missing provider taxonomic concept resolution")
        concepts = {str(row["orig_no"]) for row in resolutions}
        selectors = {concept: concept for concept in concepts}
        aliases: dict[str, str] = {}
        for row in sorted(resolutions, key=lambda row: str(row.get("taxon_no", ""))):
            alias = str(row.get("taxon_no", ""))
            if alias.startswith("var:") and optional_identifier(alias, "txn"):
                aliases.setdefault(str(row["orig_no"]), alias)
        for kind, operation, selector, extra in (
            (
                "taxa",
                "taxa/list",
                "id",
                {"show": "attr,parent,classext,ref,crmod", "variant": "all"},
            ),
            ("opinions", "taxa/opinions", "taxon_id", {"show": "ref,crmod"}),
        ):
            for group in chunks(concepts):
                while True:
                    try:
                        request_parameters: dict[str, Any] = {
                            selector: ",".join(selectors[value] for value in group),
                            "limit": "all",
                            **({"variant": "all"} if kind == "taxa" else {}),
                            "rel": "exact",
                            "show": extra["show"],
                        }
                        rows = self.request(
                            kind,
                            operation,
                            **request_parameters,
                        )
                        break
                    except UnknownTaxon as error:
                        concept = error.concept
                        if (
                            concept not in group
                            or selectors[concept] != concept
                            or concept not in aliases
                        ):
                            raise
                        selectors[concept] = aliases[concept]
                        self.routing_exceptions.append(
                            {
                                "concept": concept,
                                "selector": aliases[concept],
                                "reason": "HTTP 404 Unknown taxon for provider-resolved concept",
                            }
                        )
                if kind == "taxa" and {str(row.get("orig_no")) for row in rows} != set(group):
                    raise ValueError("Missing or out-of-scope exact taxonomic concept")
                if kind == "opinions" and any(
                    row.get("orig_no") and str(row["orig_no"]) not in group for row in rows
                ):
                    raise ValueError("Out-of-scope exact opinion concept")

    def acquire(
        self,
        *,
        occurrence_ids: list[str] | None = None,
        limit: int = 200,
        full_florida: bool = False,
    ) -> Snapshot:
        fixed_ids = occurrence_ids is not None
        if not 1 <= limit <= 1000:
            raise ValueError("Canary selection must be 1..1000 occurrences")
        collection_ids: set[str] = set()
        if full_florida:
            if occurrence_ids is not None:
                raise ValueError("Full Florida acquisition cannot use a subset selector")
            rows = self.request(
                "census-occurrences",
                "occs/list",
                cc="US",
                state="Florida",
                order="id",
                limit="all",
                idtype="latest",
            )
            occurrence_ids = [identifier(row["occurrence_no"], "occ") for row in rows]
            if len(occurrence_ids) != len(set(occurrence_ids)):
                raise ValueError("Duplicate occurrence in Florida census")
            census = self.request(
                "census-collections",
                "colls/list",
                cc="US",
                state="Florida",
                order="id",
                limit="all",
            )
            collection_ids = {identifier(row["collection_no"], "col") for row in census}
            if len(collection_ids) != len(census):
                raise ValueError("Duplicate collection in Florida census")
            print(
                json.dumps(
                    {
                        "stage": "census",
                        "occurrences": len(rows),
                        "collections": len(census),
                        "profiled_occurrences": 18915,
                        "profiled_collections": 1118,
                    }
                ),
                flush=True,
            )
        elif occurrence_ids is None:
            rows = self.request(
                "selection",
                "occs/list",
                cc="US",
                state="Florida",
                base_name="Vertebrata",
                order="id",
                limit=limit,
            )
            occurrence_ids = [identifier(row["occurrence_no"], "occ") for row in rows]
            # Profiled Florida anchors cover history, uncertainty and explicit material.
            occurrence_ids.extend(
                ["44870", "45198", "148077", "181311", "256655", "187885", "188189", "187888"]
            )
            # Phase 4A's entered-date anchors exercise Ma, Ka and YBP independently.
            for collection_id in ("17341", "81108", "74361"):
                dated = self.request(
                    "selection", "occs/list", coll_id=collection_id, order="id", limit=1
                )
                if not dated:
                    raise ValueError("Missing profiled dated-collection canary anchor")
                occurrence_ids.append(identifier(dated[0]["occurrence_no"], "occ"))
        occurrence_ids = sorted({identifier(value, "occ") for value in occurrence_ids}, key=int)
        if not occurrence_ids or len(occurrence_ids) > (MAX_RECORDS if full_florida else 1012):
            raise ValueError("Invalid bounded canary population")
        for kind, idtype in (("histories", "all"), ("latest", "latest"), ("originals", "orig")):
            self.export_ids(
                kind, "occs/list", "occ_id", occurrence_ids, show=OCCURRENCE_BLOCKS, idtype=idtype
            )
        collections = collection_ids or {
            identifier(row["collection_no"], "col") for row in self.responses["histories"]
        }
        self.export_ids("collections", "colls/list", "coll_id", collections, show=COLLECTION_BLOCKS)
        contexts = self.responses["collections"]
        if {identifier(row["collection_no"], "col") for row in contexts} != collections:
            raise ValueError("Missing canary collection dependency")
        if any(not is_florida_context(row) for row in contexts):
            raise ValueError("Non-Florida collection in canary")
        self.export_ids("materials", "specs/list", "occ_id", occurrence_ids, show="crmod")
        material_ids = [
            identifier(row["specimen_no"], "spm") for row in self.responses.get("materials", [])
        ]
        self.export_ids("measurements", "specs/measurements", "spec_id", material_ids)
        taxon_ids = {
            str(row[key])
            for row in self.responses["histories"]
            for key in ("identified_no", "accepted_no")
            if optional_identifier(row.get(key), "txn")
        }
        self.export_taxonomy(taxon_ids)
        interval_names = {
            str(row[key])
            for row in contexts
            for key in ("early_interval", "late_interval")
            if row.get(key)
        }
        # Exact names are lookup selectors only; returned provider IDs retain their own namespace.
        if interval_names:
            self.request(
                "intervals", "intervals/list", name=",".join(sorted(interval_names)), limit="all"
            )
        scales = {
            identifier(row["scale_no"], "tsc")
            for row in self.responses.get("intervals", [])
            if row.get("scale_no")
        }
        self.export_ids("timescales", "timescales/list", "scale_id", scales)
        references = {
            value
            for rows in self.responses.values()
            for row in rows
            if (value := optional_identifier(row.get("reference_no"), "ref"))
        }
        self.export_ids("references", "refs/list", "ref_id", references, show="both,crmod")
        returned_refs = {
            identifier(row["reference_no"], "ref") for row in self.responses.get("references", [])
        }
        if returned_refs != references:
            raise ValueError("Missing canary reference dependency")
        if full_florida:
            self.request(
                "census-occurrences-final",
                "occs/list",
                fresh=True,
                cc="US",
                state="Florida",
                order="id",
                limit="all",
                idtype="latest",
            )
            self.request(
                "census-collections-final",
                "colls/list",
                fresh=True,
                cc="US",
                state="Florida",
                order="id",
                limit="all",
            )
        manifest = {
            "format": ADAPTER_VERSION,
            "provider_dataset": DATASET,
            "retrieval_started": self.started,
            "retrieval_completed": datetime.now(UTC).isoformat(),
            "scope": {
                "mode": "full-florida" if full_florida else "canary",
                "complete_scope": full_florida,
                "cc": "US",
                "state": "Florida",
                "occurrence_ids": occurrence_ids,
                **({"collection_ids": sorted(collections, key=int)} if full_florida else {}),
                "selection": "public cc=US state=Florida census; final population recheck"
                if full_florida
                else "fixed IDs"
                if fixed_ids
                else f"first {limit} Vertebrata occurrence IDs plus eight Phase 4A Florida anchors "
                "and first occurrence ID in dated collections 17341,81108,74361",
            },
            "responses": self.entries,
            "atomic_provider_snapshot": False,
            "network_requests_this_attempt": self.network_requests,
            "taxonomic_routing_exceptions": self.routing_exceptions,
        }
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf8"
        )
        snapshot = Snapshot.load(self.root)
        snapshot.occurrences()
        return snapshot


def acquire_canary(
    root: Path,
    *,
    limit: int = 200,
    occurrence_ids: list[str] | None = None,
    full_florida: bool = False,
    resume: Path | None = None,
) -> Snapshot:
    prefix = "pbdb-florida" if full_florida else "pbdb-canary"
    staging = root / f"{prefix}-pending-{uuid4()}"
    acquisition = CanaryAcquisition(staging, resume=resume)
    try:
        snapshot = acquisition.acquire(
            limit=limit, occurrence_ids=occurrence_ids, full_florida=full_florida
        )
    except Exception as error:
        (staging / "failed-acquisition.json").write_text(
            json.dumps(
                {
                    "status": "failed",
                    "complete_scope": False,
                    "error": f"{type(error).__name__}: {error}",
                    "responses": acquisition.entries,
                },
                indent=2,
            )
            + "\n",
            encoding="utf8",
        )
        raise
    retained = root / f"{prefix}-{digest(snapshot.manifest)}"
    staging.rename(retained)
    return Snapshot.load(retained)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--full-florida", action="store_true")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--occurrence-ids", help="Explicit comma-separated Florida canary IDs")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "data/raw")
    args = parser.parse_args()
    snapshot = acquire_canary(
        args.output,
        limit=args.limit,
        occurrence_ids=args.occurrence_ids.split(",") if args.occurrence_ids else None,
        full_florida=args.full_florida,
        resume=args.resume,
    )
    print(
        json.dumps(
            {
                "snapshot": str(snapshot.path),
                "hash": snapshot.hash,
                "occurrences": len(snapshot.occurrences()),
                "requests": len(snapshot.manifest["responses"]),
                "peak_memory_bytes": peak_memory_bytes(),
            }
        )
    )


if __name__ == "__main__":
    main()
