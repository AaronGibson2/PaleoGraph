"""PBDB-specific normalization. Provider calibration is never a UFVP interpretation."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

PROVIDER = "The Paleobiology Database"
SERVICE = "https://paleobiodb.org/data1.2/"
DATASET = "pbdb:public:florida:v1"
ADAPTER_VERSION = "pbdb-adapter-v1"
POLICY_VERSION = "pbdb-provider-envelope-v1"
LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/"


def is_florida_context(raw: dict[str, Any]) -> bool:
    return (
        str(raw.get("cc", "")).strip().upper() == "US"
        and str(raw.get("state", "")).strip().casefold() == "florida"
    )


def decode_response(
    raw: bytes, parameters: dict[str, Any], *, history: bool = False
) -> dict[str, Any]:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result and result[key] != value:
                raise ValueError(f"Conflicting duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError(f"Nonfinite JSON value: {value}")

    response = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(response, dict) or not isinstance(response.get("records"), list):
        raise ValueError("Invalid PBDB response schema")
    if response.get("errors") or response.get("warnings"):
        raise ValueError("PBDB response contains errors or warnings")
    if response.get("data_provider") != PROVIDER:
        raise ValueError("Changed PBDB provider")
    if (
        response.get("data_license") != "Creative Commons CC0"
        or response.get("license_url") != LICENSE
    ):
        raise ValueError("Changed or missing PBDB license")
    if any(not isinstance(row, dict) for row in response["records"]):
        raise ValueError("Invalid PBDB record schema")
    if history:
        if parameters.get("all_idents") or parameters.get("idtype") != "all":
            raise ValueError("Unsafe all_idents or non-history request")
        if str(parameters.get("limit")) != "all":
            raise ValueError("History completeness requires an uncapped fixed-ID export")
        if not parameters.get("occ_id"):
            raise ValueError("History export requires fixed occurrence IDs")
    if parameters.get("rowcount") == "yes":
        found, returned = response.get("records_found"), response.get("records_returned")
        if (
            isinstance(found, bool)
            or not isinstance(found, int)
            or isinstance(returned, bool)
            or not isinstance(returned, int)
        ):
            raise ValueError("Missing PBDB count metadata")
        if returned != len(response["records"]):
            raise ValueError("PBDB row count mismatch")
        if found < returned or returned < 0:
            raise ValueError("Invalid PBDB count metadata")
        if str(parameters.get("limit")) == "all" and found != returned:
            raise ValueError("Incomplete PBDB export count")
    return response


@dataclass(frozen=True)
class Snapshot:
    manifest: dict[str, Any]
    responses: tuple[dict[str, Any], ...]
    hash: str
    path: Path

    @classmethod
    def load(cls, path: Path) -> "Snapshot":
        path = path.resolve()
        manifest = json.loads((path / "manifest.json").read_bytes())
        if manifest.get("format") != ADAPTER_VERSION or manifest.get("scope", {}).get(
            "mode"
        ) not in {"canary", "full-florida"}:
            raise ValueError("Unsupported PBDB snapshot contract/scope")
        full = manifest["scope"]["mode"] == "full-florida"
        if manifest["scope"].get("complete_scope") is not full:
            raise ValueError("PBDB scope/completeness declaration disagrees")
        if (
            manifest.get("provider_dataset") != DATASET
            or manifest["scope"].get("cc") != "US"
            or manifest["scope"].get("state") != "Florida"
        ):
            raise ValueError("Changed PBDB dataset/scope")
        kinds = {entry["kind"] for entry in manifest["responses"]}
        if not {"histories", "latest", "originals", "collections", "materials"} <= kinds:
            raise ValueError("Missing bounded export completeness controls")
        operations = {
            "histories": "occs/list",
            "latest": "occs/list",
            "originals": "occs/list",
            "selection": "occs/list",
            "census-occurrences": "occs/list",
            "census-occurrences-final": "occs/list",
            "census-collections": "colls/list",
            "census-collections-final": "colls/list",
            "collections": "colls/list",
            "materials": "specs/list",
            "measurements": "specs/measurements",
            "taxa": "taxa/list",
            "taxon-resolution": "taxa/list",
            "opinions": "taxa/opinions",
            "intervals": "intervals/list",
            "timescales": "timescales/list",
            "references": "refs/list",
        }
        responses = []
        for entry in manifest["responses"]:
            file = (path / entry["file"]).resolve()
            if file.parent != path or not entry["url"].startswith(SERVICE):
                raise ValueError("Invalid retained snapshot path/provider")
            if (
                entry["kind"] not in operations
                or entry["url"].split("?", 1)[0] != SERVICE + operations[entry["kind"]] + ".json"
            ):
                raise ValueError("Wrong PBDB endpoint for retained response kind")
            params = entry["parameters"]
            if entry["kind"].startswith("census-"):
                if full and entry["kind"].endswith("-final") and entry.get("reused_from"):
                    raise ValueError("Final Florida census must be freshly retrieved")
                allowed = {
                    "vocab",
                    "extids",
                    "datainfo",
                    "rowcount",
                    "strict",
                    "cc",
                    "state",
                    "order",
                    "limit",
                    "idtype",
                }
                if (
                    params.get("cc") != "US"
                    or params.get("state") != "Florida"
                    or params.get("order") != "id"
                    or set(params) - allowed
                    or ("occurrences" in entry["kind"] and params.get("idtype") != "latest")
                ):
                    raise ValueError("Changed public Florida census selector")
            if parse_qs(urlparse(entry["url"]).query) != {
                key: [str(value)] for key, value in params.items()
            }:
                raise ValueError("Retained PBDB URL/parameters disagree")
            if any(
                params.get(key) != value
                for key, value in {
                    "rowcount": "yes",
                    "datainfo": "yes",
                    "vocab": "pbdb",
                    "extids": "yes",
                    "strict": "yes",
                }.items()
            ):
                raise ValueError("Missing explicit PBDB response contract controls")
            if entry["kind"] != "selection" and str(params.get("limit")) != "all":
                raise ValueError("Capped retained dependency export")
            expected_idtype = {"histories": "all", "latest": "latest", "originals": "orig"}.get(
                entry["kind"]
            )
            if expected_idtype and params.get("idtype") != expected_idtype:
                raise ValueError("Wrong identification control selector")
            if entry["kind"] in {"taxon-resolution", "taxa", "opinions"}:
                selector = "taxon_id" if entry["kind"] == "opinions" else "id"
                if (
                    params.get("rel") != "exact"
                    or not params.get(selector)
                    or params.get("base_id")
                ):
                    raise ValueError("Unsafe retained PBDB taxonomic scope")
                if entry["kind"] == "taxa" and params.get("variant") != "all":
                    raise ValueError("Incomplete retained PBDB name-variant scope")
            raw = file.read_bytes()
            if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise ValueError("Retained PBDB response hash mismatch")
            response = decode_response(
                raw, entry["parameters"], history=entry["kind"] == "histories"
            )
            responses.append({"kind": entry["kind"], "response": response})
        snapshot = cls(manifest, tuple(responses), digest(manifest), path)
        if full:
            snapshot.validate_census()
        return snapshot

    def validate_census(self) -> None:
        for population, field, prefix in (
            ("occurrences", "occurrence_no", "occ"),
            ("collections", "collection_no", "col"),
        ):
            key = "occurrence_ids" if prefix == "occ" else "collection_ids"
            expected = {identifier(value, prefix) for value in self.manifest["scope"][key]}
            for suffix in ("", "-final"):
                kind = f"census-{population}{suffix}"
                if sum(item["kind"] == kind for item in self.responses) != 1:
                    raise ValueError("Missing full Florida census controls")
                rows = self.records(kind)
                ids = [identifier(row[field], prefix) for row in rows]
                if not ids or len(ids) != len(set(ids)) or set(ids) != expected:
                    raise ValueError("Changed, duplicate or incomplete Florida census population")
        collections = {
            identifier(row["collection_no"], "col") for row in self.records("collections")
        }
        if collections != set(self.manifest["scope"]["collection_ids"]):
            raise ValueError("Incomplete full Florida collection context")

    def records(self, kind: str) -> list[dict[str, Any]]:
        return [
            row
            for item in self.responses
            if item["kind"] == kind
            for row in item["response"]["records"]
        ]

    def occurrences(self) -> list["OccurrenceRecord"]:
        occurrences = normalize_occurrences(
            self.records("histories"), self.records("latest"), self.records("originals")
        )
        wanted = {identifier(value, "occ") for value in self.manifest["scope"]["occurrence_ids"]}
        ceiling = 50000 if self.manifest["scope"]["mode"] == "full-florida" else 1012
        if not 1 <= len(wanted) <= ceiling:
            raise ValueError("PBDB snapshot exceeds bounded canary occurrence scope")
        for kind in ("histories", "latest", "originals"):
            requested = [
                identifier(value, "occ")
                for entry in self.manifest["responses"]
                if entry["kind"] == kind
                for value in str(entry["parameters"].get("occ_id", "")).split(",")
            ]
            if set(requested) != wanted or len(requested) != len(wanted):
                raise ValueError("Overlapping or incomplete fixed-ID history request scope")
        if {record.id for record in occurrences} != wanted:
            raise ValueError("Incomplete canary occurrence population")
        return occurrences


def stable_id(kind: str, value: str) -> UUID:
    return UUID(bytes=hashlib.sha256(f"{DATASET}|{kind}|{value}".encode()).digest()[:16], version=4)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def identifier(value: Any, kind: str) -> str:
    text = str(value or "")
    if ":" in text:
        prefix, text = text.split(":", 1)
        if prefix != kind and not (kind == "txn" and prefix == "var"):
            raise ValueError(f"Expected {kind} identifier")
    if not text.isascii() or not text.isdigit() or int(text) <= 0:
        raise ValueError(f"Invalid {kind} identifier")
    return str(int(text))


def optional_identifier(value: Any, kind: str) -> str | None:
    return None if value in (None, "", "0", 0) else identifier(value, kind)


def decimal_value(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a scientific numeric value")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Invalid scientific numeric value") from error
    if not number.is_finite():
        raise ValueError("Nonfinite scientific numeric value")
    return number


@dataclass(frozen=True)
class DeterminedDate:
    value: Decimal | None
    error: Decimal | None
    unit: str | None
    method: str | None


@dataclass(frozen=True)
class PositionEvidence:
    latitude: Decimal | None
    longitude: Decimal | None
    basis: str | None
    precision: str | None
    status: str
    geometry: None = None


@dataclass(frozen=True)
class CollectionRecord:
    id: str
    name: str
    older_ma: Decimal | None
    younger_ma: Decimal | None
    dates: dict[str, DeterminedDate]
    position: PositionEvidence
    raw: dict[str, Any]


@dataclass(frozen=True)
class IdentificationRecord:
    id: str
    name: str
    accepted_name: str | None
    identified_id: str | None
    accepted_id: str | None
    reference_id: str | None
    is_latest: bool
    raw: dict[str, Any]


@dataclass(frozen=True)
class MaterialRecord:
    id: str
    occurrence_id: str
    collection_id: str | None
    reidentification_id: str | None
    catalog_label: str | None
    recorded_measured_count: str | int | None
    reference_id: str | None
    raw: dict[str, Any]
    canonical_specimen_id: None = None


@dataclass(frozen=True)
class MeasurementRecord:
    id: str
    material_id: str
    measurement_type: str | None
    values: dict[str, Decimal | None]
    unit: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class OpinionRecord:
    id: str
    child_identifier: str | None
    original_concept_identifier: str | None
    parent_identifier: str | None
    relationship: str | None
    reference_id: str | None
    raw: dict[str, Any]
    evidence_kind: str = "taxonomic-opinion"


@dataclass(frozen=True)
class ReferenceRecord:
    id: str
    title: str | None
    doi: str | None
    published_year: str | None
    authors: dict[str, Any]
    raw: dict[str, Any]


@dataclass(frozen=True)
class TaxonNameRecord:
    concept_identifier: str | None
    name_variant_identifier: str
    accepted_identifier: str | None
    parent_identifier: str | None
    name: str | None
    rank: str | None
    reference_id: str | None
    raw: dict[str, Any]


def normalize_taxon_name(raw: dict[str, Any]) -> TaxonNameRecord:
    identifier(raw.get("taxon_no"), "txn")
    for field in ("orig_no", "accepted_no", "parent_no"):
        optional_identifier(raw.get(field), "txn")
    return TaxonNameRecord(
        raw.get("orig_no"),
        str(raw["taxon_no"]),
        raw.get("accepted_no"),
        raw.get("parent_no"),
        raw.get("taxon_name"),
        raw.get("taxon_rank"),
        optional_identifier(raw.get("reference_no"), "ref"),
        dict(raw),
    )


def normalize_material(raw: dict[str, Any]) -> MaterialRecord:
    return MaterialRecord(
        identifier(raw.get("specimen_no"), "spm"),
        identifier(raw.get("occurrence_no"), "occ"),
        optional_identifier(raw.get("collection_no"), "col"),
        optional_identifier(raw.get("reid_no"), "rei"),
        raw.get("specimen_id"),
        raw.get("n_measured"),
        optional_identifier(raw.get("reference_no"), "ref"),
        dict(raw),
    )


def normalize_measurement(raw: dict[str, Any]) -> MeasurementRecord:
    return MeasurementRecord(
        identifier(raw.get("measurement_no"), "mea"),
        identifier(raw.get("specimen_no"), "spm"),
        raw.get("measurement_type"),
        {
            key: decimal_value(raw.get(key))
            for key in ("average", "median", "min", "max", "error", "stddev")
        },
        raw.get("unit"),
        dict(raw),
    )


def normalize_opinion(raw: dict[str, Any]) -> OpinionRecord:
    for key in ("orig_no", "child_spelling_no", "parent_no"):
        optional_identifier(raw.get(key), "txn")
    return OpinionRecord(
        identifier(raw.get("opinion_no"), "opn"),
        raw.get("child_spelling_no"),
        raw.get("orig_no"),
        raw.get("parent_no"),
        raw.get("status"),
        optional_identifier(raw.get("reference_no"), "ref"),
        dict(raw),
    )


def normalize_reference(raw: dict[str, Any]) -> ReferenceRecord:
    return ReferenceRecord(
        identifier(raw.get("reference_no"), "ref"),
        raw.get("reftitle"),
        raw.get("doi"),
        str(raw["pubyr"]) if raw.get("pubyr") else None,
        {key: value for key, value in raw.items() if key.startswith("author")},
        dict(raw),
    )


@dataclass(frozen=True)
class OccurrenceRecord:
    id: str
    collection_id: str
    identifications: tuple[IdentificationRecord, ...]
    complete_history: bool

    @property
    def latest(self) -> IdentificationRecord:
        return next(ident for ident in self.identifications if ident.is_latest)

    @property
    def original(self) -> IdentificationRecord:
        return next(ident for ident in self.identifications if ident.id == "original")


def identification_key(raw: dict[str, Any]) -> str:
    return optional_identifier(raw.get("reid_no"), "rei") or "original"


def normalize_occurrences(
    histories: list[dict[str, Any]], latest: list[dict[str, Any]], originals: list[dict[str, Any]]
) -> list[OccurrenceRecord]:
    latest_by_id = {identifier(row.get("occurrence_no"), "occ"): row for row in latest}
    originals_by_id = {identifier(row.get("occurrence_no"), "occ"): row for row in originals}
    if len(latest_by_id) != len(latest) or len(originals_by_id) != len(originals):
        raise ValueError("Duplicate identification history controls")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in histories:
        grouped.setdefault(identifier(row.get("occurrence_no"), "occ"), []).append(row)
    if grouped.keys() != latest_by_id.keys() or grouped.keys() != originals_by_id.keys():
        raise ValueError("Incomplete identification history population")
    result = []
    for occurrence_id, rows in sorted(grouped.items(), key=lambda item: int(item[0])):
        current = latest_by_id[occurrence_id]
        original = originals_by_id[occurrence_id]
        keys = [identification_key(row) for row in rows]
        if len(set(keys)) != len(keys) or keys.count("original") != 1:
            raise ValueError("Duplicate or missing original identification history")
        for control in (current, original):
            matching = [
                row for row in rows if identification_key(row) == identification_key(control)
            ]
            if not matching or matching[0] != control:
                raise ValueError("Incomplete or changed identification history controls")
        collection_id = identifier(current.get("collection_no"), "col")
        if any(identifier(row.get("collection_no"), "col") != collection_id for row in rows):
            raise ValueError("Inconsistent collection in identification history")
        identifications = tuple(
            IdentificationRecord(
                identification_key(row),
                str(row.get("identified_name") or "Identification not supplied"),
                row.get("accepted_name"),
                optional_identifier(row.get("identified_no"), "txn"),
                optional_identifier(row.get("accepted_no"), "txn"),
                optional_identifier(row.get("reference_no"), "ref"),
                identification_key(row) == identification_key(current),
                dict(row),
            )
            for row in sorted(
                rows,
                key=lambda row: (identification_key(row) != "original", identification_key(row)),
            )
        )
        result.append(OccurrenceRecord(occurrence_id, collection_id, identifications, True))
    return result


def normalize_collection(raw: dict[str, Any]) -> CollectionRecord:
    older, younger = decimal_value(raw.get("max_ma")), decimal_value(raw.get("min_ma"))
    if any(value is not None and value < 0 for value in (older, younger)):
        raise ValueError("Negative provider envelope")
    if older is not None and younger is not None and older < younger:
        raise ValueError("Reversed provider envelope")
    latitude, longitude = decimal_value(raw.get("lat")), decimal_value(raw.get("lng"))
    status = "datum-unverified"
    if latitude is None or longitude is None:
        status = "missing"
    elif not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        status = "out-of-range"
    dates = {
        prefix: DeterminedDate(
            decimal_value(raw.get(f"{prefix}_ma_value")),
            decimal_value(raw.get(f"{prefix}_ma_error")),
            raw.get(f"{prefix}_ma_unit"),
            raw.get(f"{prefix}_ma_method"),
        )
        for prefix in ("direct", "max", "min")
    }
    if any(date.error is not None and date.error < 0 for date in dates.values()):
        raise ValueError("Negative determined-date error")
    return CollectionRecord(
        identifier(raw.get("collection_no"), "col"),
        str(raw.get("collection_name") or "Collection name not supplied"),
        older,
        younger,
        dates,
        PositionEvidence(
            latitude, longitude, raw.get("latlng_basis"), raw.get("latlng_precision"), status
        ),
        dict(raw),
    )
