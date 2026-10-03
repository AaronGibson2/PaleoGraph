"""One attributed reference and deterministic, conservative source-label interpretation."""

import json
import re
from functools import cache
from typing import Any

from app.config import REPO_ROOT

POLICY_VERSION = "ufvp-geology-v1:ics-2026-06"
AGE_FIELDS = (
    "earliestAgeOrLowestStage",
    "earliestEpochOrLowestSeries",
    "earliestPeriodOrLowestSystem",
    "earliestEraOrLowestErathem",
)
NALMA = frozenset(
    {
        "Arikareean",
        "Barstovian",
        "Blancan",
        "Clarendonian",
        "Hemphillian",
        "Hemingfordian",
        "Irvingtonian",
        "Rancholabrean",
        "Whitneyan",
        "Chadronian",
        "Orellan",
        "Duchesnean",
        "Uintan",
        "Bridgerian",
        "Wasatchian",
        "Clarkforkian",
        "Tiffanian",
        "Torrejonian",
        "Puercan",
    }
)


@cache
def reference() -> dict[str, Any]:
    with (REPO_ROOT / "docs/source-data/ics-2026-06.json").open(encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


@cache
def intervals() -> dict[str, dict[str, Any]]:
    data = reference()
    units = {item["id"]: {**item} for item in data["units"]}
    for composition in data["validated_subepoch_compositions"]:
        units[composition["id"]] = {
            **composition,
            "color": units[composition["parent"]]["color"],
        }
    return units


def interval_key(identifier: str) -> str:
    return f"ics:2026-06:{identifier}"


def configuration() -> dict[str, Any]:
    data = reference()
    return {
        "version": data["version"],
        "kind": "international_chronostratigraphic_chart",
        "max_ma": 4567,
        "source_url": data["source_url"],
        "license_url": data["license_url"],
        "attribution": "International Commission on Stratigraphy / CGMW; CC BY 4.0. "
        "Adapted by PaleoGraph; two documented PDF corrections. No endorsement.",
        "units": [
            {
                **unit,
                "id": interval_key(unit["id"]),
                "parent": interval_key(unit["parent"]) if unit["parent"] else None,
            }
            for unit in intervals().values()
        ],
    }


def normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


@cache
def aliases() -> dict[str, str]:
    result: dict[str, str] = {}
    for identifier, unit in intervals().items():
        for name in [unit["name"], *unit.get("aliases", [])]:
            result[normalize_label(name)] = identifier
        if unit["rank"] == "Subepoch":
            modifier, epoch = unit["name"].split(" ", 1)
            result[normalize_label(f"{epoch}, {modifier}")] = identifier
    # Explicit stage equivalences for the three formal Holocene subdivisions.
    for modifier, stage in (
        ("early", "Greenlandian"),
        ("middle", "Northgrippian"),
        ("late", "Meghalayan"),
    ):
        result[f"holocene, {modifier}"] = stage
        result[f"{modifier} holocene"] = stage
    return result


def interpret(raw: dict[str, Any]) -> dict[str, Any]:
    field = next((field for field in AGE_FIELDS if str(raw.get(field) or "").strip()), None)
    label = str(raw[field]).strip() if field else None
    result: dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "source_field": field,
        "source_label": label,
        "interval_id": None,
        "older_ma": None,
        "younger_ma": None,
        "status": "absent" if not label else "unmapped",
        "rule": "no-supported-assertion",
    }
    if not label:
        return result
    normalized = normalize_label(label)
    # Qualifiers are deliberately rejected before alias lookup. No broad-field fallback.
    if re.search(r"\?|\bor\b|\band\b|mixed|uncertain|approx|\bcf\b|\baff\b|[/()]", normalized):
        return {**result, "status": "ambiguous", "rule": "qualified-or-alternative-label"}
    identifier = aliases().get(normalized)
    if identifier is None:
        return result
    unit = intervals()[identifier]
    return {
        **result,
        "status": "mapped",
        "rule": "exact-validated-label",
        "interval_id": interval_key(identifier),
        "older_ma": unit["older_ma"],
        "younger_ma": unit["younger_ma"],
    }
