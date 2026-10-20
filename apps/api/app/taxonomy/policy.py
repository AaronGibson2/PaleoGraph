"""Pure, deterministic browse placement. No provider identities are rewritten."""

import json
import re
import unicodedata
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from uuid import UUID, uuid5

VERSION = "taxonomy-browse-v1"
NAMESPACE = UUID("098a01be-7418-41c1-8d46-ff3436e419d4")
RANKS = (
    "kingdom",
    "subkingdom",
    "phylum",
    "subphylum",
    "class",
    "subclass",
    "infraclass",
    "order",
    "suborder",
    "infraorder",
    "superfamily",
    "family",
    "subfamily",
    "tribe",
    "subtribe",
    "genus",
    "subgenus",
    "species",
    "subspecies",
)
QUALIFIED = re.compile(r"\b(cf|aff|sp|spp|indet|uncertain)\b|\?", re.I)


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


@dataclass(frozen=True)
class Term:
    name: str
    rank: str | None
    concept: str
    taxon_id: UUID | None = None
    canonical: bool = True
    provenance: dict[str, object] = dataclass_field(default_factory=dict, compare=True)

    @property
    def signature(self) -> tuple[str, str | None]:
        return normalized(self.name), self.rank.lower() if self.rank else None


@dataclass(frozen=True)
class Classification:
    taxon_id: UUID
    source: str
    terms: tuple[Term, ...]
    qualifiers: tuple[str, ...] = ()
    conflict: bool = False
    rooted: bool = False
    leaf_placement: str | None = None


def identity(scope: str, path: tuple[tuple[str, str | None], ...], isolation: str = "") -> UUID:
    return uuid5(NAMESPACE, json.dumps([VERSION, scope, path, isolation], ensure_ascii=False))


def complete_prefix(
    terms: tuple[Term, ...], supported: list[tuple[Term, ...]]
) -> tuple[tuple[Term, ...], bool]:
    """Only a unique explicit two-rank prefix can supply a missing upper path.

    Supplied names/ranks must agree in order with every overlapping rank. Added
    relationships already exist in retained source classification, and are marked
    as browse placement. A one-name match never authorizes this operation.
    """
    if len(terms) < 2 or terms[0].rank == "kingdom":
        return terms, False
    pair = tuple(t.signature for t in terms[:2])
    candidates: dict[tuple[tuple[tuple[str, str | None], str], ...], tuple[Term, ...]] = {}
    for path in supported:
        signatures = tuple(t.signature for t in path)
        for start in range(1, len(path) - 1):
            if signatures[start : start + 2] == pair:
                prefix = path[:start]
                candidates[
                    tuple((t.signature, t.concept if t.canonical else "") for t in prefix)
                ] = prefix
    if len(candidates) != 1:
        return terms, False
    prefix = next(iter(candidates.values()))
    return prefix + terms, True


def pbdb_classification(
    taxon_id: UUID, name: str, rank: str | None, raw: dict[str, object]
) -> Classification:
    """Use explicit classification fields, preserving entered/accepted disagreement."""
    terms = []
    leaf_position = RANKS.index(rank) if rank in RANKS else len(RANKS)
    for field in RANKS:
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        if value.startswith("NO_") and value.endswith("_SPECIFIED"):
            continue
        if RANKS.index(field) >= leaf_position:
            continue
        external = raw.get(field + "_no")
        terms.append(
            Term(
                value,
                field,
                str(external or "supplied:" + field + ":" + value),
                canonical=bool(external),
            )
        )
    accepted = raw.get("accepted_name")
    conflict = isinstance(accepted, str) and normalized(accepted) != normalized(name)
    qualifiers = tuple(
        str(raw[k])
        for k in ("genus_reso", "species_reso", "identification_qualifier")
        if raw.get(k)
    )
    if QUALIFIED.search(name):
        qualifiers += ("qualified source name",)
    canonical = raw.get("identified_no") or (raw.get("accepted_no") if not conflict else None)
    leaf = Term(
        name, rank, str(canonical or "identification:" + str(taxon_id)), taxon_id, bool(canonical)
    )
    return Classification(taxon_id, "pbdb", tuple(terms) + (leaf,), qualifiers, conflict)
