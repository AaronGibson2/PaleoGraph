"""Official UFVP Darwin Core Archive boundary. No source calls from Explore."""

import csv
import hashlib
import io
import json
import math
import re
import shutil
import time
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen
from uuid import UUID

DATASET_ID = "2fba9985-ac30-46cb-99bf-91ccde0d8d2f"
RESOURCE_URL = "https://ipt.floridamuseum.ufl.edu/ipt/resource?r=ufvp"
IPT = "https://ipt.floridamuseum.ufl.edu/ipt"
LICENSE = "https://creativecommons.org/licenses/by-nc/4.0/"
IMPORTER_VERSION = "ufvp-v1"
DWCA = "{http://rs.tdwg.org/dwc/text/}"


def stable_id(kind: str, key: str) -> UUID:
    """Opaque stable v4-shaped IDs, scoped to this adapter, never catalog triplets."""
    return UUID(
        bytes=hashlib.sha256(f"ufvp:{DATASET_ID}:{kind}:{key}".encode()).digest()[:16], version=4
    )


def content_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True)
class Metadata:
    dataset_id: str
    title: str
    publisher: str
    version: str
    published_at: datetime
    license: str
    citation: str | None
    rights_holder: str
    creator: str

    def snapshot(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "title": self.title,
            "publisher": self.publisher,
            "version": self.version,
            "published_at": self.published_at.isoformat(),
            "license": self.license,
            "citation": self.citation,
            "rights_holder": self.rights_holder,
            "creator": self.creator,
        }


def parse_metadata(eml: bytes) -> Metadata:
    root = ET.fromstring(eml)
    dataset = root.find("dataset")
    if dataset is None:
        raise ValueError("Missing EML dataset")
    package = root.attrib.get("packageId", "")
    if not package.startswith(f"{DATASET_ID}/v"):
        raise ValueError("Not the official UFVP dataset")
    rights = dataset.find("intellectualRights")
    urls = [] if rights is None else [link.attrib.get("url", "") for link in rights.iter("ulink")]
    if not any("creativecommons.org/licenses/by-nc/4.0" in url for url in urls):
        raise ValueError("Unverified or changed source license; review before importing")
    publisher = dataset.findtext("creator/organizationName", "").strip()
    if publisher != "Florida Museum of Natural History":
        raise ValueError("Unverified UFVP publisher")
    return Metadata(
        DATASET_ID,
        dataset.findtext("title", "").strip(),
        publisher,
        package.split("/v", 1)[1],
        datetime.fromisoformat(dataset.findtext("pubDate", "").strip()).replace(tzinfo=UTC),
        LICENSE,
        dataset.findtext("bibliographicCitation"),
        publisher,
        " ".join(
            filter(
                None,
                [
                    dataset.findtext("creator/individualName/givenName"),
                    dataset.findtext("creator/individualName/surName"),
                ],
            )
        ),
    )


def fetch_archive(raw_dir: Path, version: str | None = None) -> Path:
    """Fetch metadata first, verify rights, pin the version, retain immutable hashed bytes."""

    def fetch(url: str) -> bytes:
        for attempt in range(3):
            try:
                with urlopen(url, timeout=60) as response:  # noqa: S310 (fixed official host)
                    return bytes(response.read())
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")

    if version is not None and not re.fullmatch(r"\d+\.\d+", version):
        raise ValueError("Version must be the official numeric IPT version")
    eml = fetch(f"{IPT}/eml.do?r=ufvp" + (f"&v={version}" if version else ""))
    metadata = parse_metadata(eml)
    payload = fetch(f"{IPT}/archive.do?r=ufvp&v={metadata.version}")
    digest = hashlib.sha256(payload).hexdigest()
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"ufvp-v{metadata.version}-{digest}.zip"
    if not target.exists():
        with target.open("xb") as stream:
            stream.write(payload)
    with zipfile.ZipFile(target) as archive:
        if parse_metadata(archive.read("eml.xml")) != metadata:
            raise ValueError("Archive metadata differs from the verified pinned metadata")
    return target


class Archive:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.digest = file_hash(path)
        with zipfile.ZipFile(path) as archive:
            self.metadata = parse_metadata(archive.read("eml.xml"))
            self.definition = ET.fromstring(archive.read("meta.xml"))
        core = self.definition.find(f"{DWCA}core")
        if core is None or core.attrib.get("rowType") != "http://rs.tdwg.org/dwc/terms/Occurrence":
            raise ValueError("Unsupported archive core")
        if (
            core.attrib.get("fieldsTerminatedBy") != r"\t"
            or core.attrib.get("fieldsEnclosedBy") != ""
            or core.attrib.get("encoding", "").upper() != "UTF-8"
        ):
            raise ValueError("Changed archive dialect; review required")
        location = core.findtext(f"{DWCA}files/{DWCA}location")
        identifier = core.find(f"{DWCA}id")
        if not location or identifier is None:
            raise ValueError("Missing archive core file or ID")
        self.location = location
        self.header_lines = int(core.attrib.get("ignoreHeaderLines", "0"))
        self.fields = {
            int(field.attrib["index"]): field.attrib["term"].rsplit("/", 1)[-1]
            for field in core.findall(f"{DWCA}field")
        }
        self.fields[int(identifier.attrib["index"])] = "id"

    def retain(self, raw_dir: Path) -> Path:
        raw_dir.mkdir(parents=True, exist_ok=True)
        target = raw_dir / f"ufvp-v{self.metadata.version}-{self.digest}.zip"
        if self.path.resolve() != target.resolve():
            if target.exists():
                if file_hash(target) != self.digest:
                    raise ValueError("Retained snapshot hash mismatch")
            else:
                with self.path.open("rb") as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
        return target

    def rows(self) -> Iterator[dict[str, str]]:
        with zipfile.ZipFile(self.path) as archive:
            with io.TextIOWrapper(
                archive.open(self.location), encoding="utf-8", newline=""
            ) as stream:
                reader = csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
                for _ in range(self.header_lines):
                    next(reader)
                for values in reader:
                    if len(values) <= max(self.fields):
                        raise ValueError("Malformed core row; snapshot cannot be complete")
                    yield {name: values[index] for index, name in self.fields.items()}


def text_value(raw: dict[str, str], key: str) -> str | None:
    return raw.get(key, "").strip() or None


def number(raw: dict[str, str], key: str) -> float | None:
    try:
        value = float(raw.get(key, ""))
        return value if math.isfinite(value) else None
    except ValueError:
        return None


GEOLOGICAL_FIELDS = (
    "earliestEraOrLowestErathem",
    "earliestPeriodOrLowestSystem",
    "earliestEpochOrLowestSeries",
    "earliestAgeOrLowestStage",
    "latestEraOrHighestErathem",
    "latestPeriodOrHighestSystem",
    "latestEpochOrHighestSeries",
    "latestAgeOrHighestStage",
    "lowestBiostratigraphicZone",
    "highestBiostratigraphicZone",
    "group",
    "formation",
    "member",
)


@dataclass(frozen=True)
class NormalizedRecord:
    source_id: str
    raw: dict[str, str]
    hash: str
    name: str
    latitude: float | None
    longitude: float | None
    coordinate_status: str
    withheld: bool
    generalized: bool
    uncertainty: float | None
    precision: float | None
    geology: dict[str, str]
    modified_at: datetime | None
    warnings: tuple[str, ...]


def normalize(raw: dict[str, str]) -> NormalizedRecord:
    identifier = raw.get("id", "")
    if not identifier or identifier != identifier.strip():
        raise ValueError("Missing or whitespace-ambiguous core identifier")
    if text_value(raw, "basisOfRecord") not in {"FossilSpecimen", "PreservedSpecimen"}:
        raise ValueError("Record does not assert preserved physical material")
    name = text_value(raw, "scientificName")
    # Missing identification is valid material, not an invented scientific name.
    name = name or "Identification not supplied"
    # Conservative handling: any explicit withholding suppresses the position.
    withheld = bool(text_value(raw, "informationWithheld"))
    generalized = bool(text_value(raw, "dataGeneralizations"))
    latitude, longitude = number(raw, "decimalLatitude"), number(raw, "decimalLongitude")
    datum = (text_value(raw, "geodeticDatum") or "").casefold().replace(" ", "")
    if withheld:
        status = "withheld"
    elif latitude is None or longitude is None:
        status = "missing or nonnumeric coordinates"
    elif not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        status = "out-of-range coordinates"
    elif datum not in {"wgs84", "wgs1984", "epsg:4326"}:
        status = "unsupported or unspecified datum"
    else:
        status = "published WGS84 coordinates"
    if status != "published WGS84 coordinates":
        latitude = longitude = None
    warnings: list[str] = []
    if not text_value(raw, "scientificName"):
        warnings.append("missing scientific name; navigation placeholder only")
    uncertainty = number(raw, "coordinateUncertaintyInMeters")
    precision = number(raw, "coordinatePrecision")
    if text_value(raw, "coordinateUncertaintyInMeters") and uncertainty is None:
        warnings.append("unparsed coordinate uncertainty retained verbatim")
    if uncertainty is not None and uncertainty < 0:
        warnings.append("negative coordinate uncertainty ignored")
        uncertainty = None
    if precision is not None and precision < 0:
        warnings.append("negative coordinate precision ignored")
        precision = None
    modified = None
    if value := text_value(raw, "modified"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            # UFVP timestamps have no zone; preserve them verbatim rather than inventing UTC.
            if parsed.tzinfo is not None:
                modified = parsed.astimezone(UTC)
            else:
                warnings.append("source modified timestamp has no time zone; retained verbatim")
        except ValueError:
            warnings.append("unparsed modified timestamp retained verbatim")
    geology = {key: raw[key] for key in GEOLOGICAL_FIELDS if text_value(raw, key)}
    return NormalizedRecord(
        identifier,
        raw,
        content_hash(raw),
        name,
        latitude,
        longitude,
        status,
        withheld,
        generalized,
        uncertainty,
        precision,
        geology,
        modified,
        tuple(warnings),
    )
