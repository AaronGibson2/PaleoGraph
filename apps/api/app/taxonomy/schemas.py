from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.discovery.schemas import ContextQuery


class TaxonomyQuery(ContextQuery):
    source: Literal["all", "ufvp", "pbdb"] = "all"
    offset: int = Field(default=0, ge=0, le=100000)


class EvidenceCounts(BaseModel):
    evidence_count: int = Field(
        default=0,
        description="Inclusive source assertions at this node or descendants; "
        "not organisms or pieces.",
    )
    direct_count: int = Field(
        default=0, description="Source assertions classified directly at this node."
    )
    ufvp_material_count: int = 0
    pbdb_occurrence_count: int = 0
    child_count: int = 0
    known_age_count: int = 0
    unknown_age_count: int = 0
    older_ma: float | None = None
    younger_ma: float | None = None
    derived_count: int = 0
    source_numeric_count: int = 0
    derived_older_ma: float | None = None
    derived_younger_ma: float | None = None
    source_older_ma: float | None = None
    source_younger_ma: float | None = None


class TaxonomyNode(BaseModel):
    id: UUID
    parent_id: UUID | None
    name: str
    rank: str | None
    placement: str
    identity_hint: str | None = None
    path: list[dict[str, Any]]
    sources: list[Literal["ufvp", "pbdb"]]
    counts: EvidenceCounts
    classification_path_ids: list[str] = Field(default_factory=list)
    unified: bool = False
    source_disagreement_note: str | None = None


class TaxonomyPage(BaseModel):
    items: list[TaxonomyNode]
    total: int
    next_offset: int | None = None
    version: str
    scope: str = "florida"


class BranchChildren(BaseModel):
    parent_id: UUID
    page: TaxonomyPage


class BranchChildrenPage(BaseModel):
    items: list[BranchChildren]
    next_offset: int | None = None
    version: str


class SourceConcept(BaseModel):
    source: Literal["ufvp", "pbdb"]
    concept_key: str
    taxon_id: UUID | None
    details: dict[str, Any]


class ConceptPage(BaseModel):
    items: list[SourceConcept]
    total: int
    next_offset: int | None = None
    version: str


class EvidencePreview(BaseModel):
    id: UUID
    occurrence_id: UUID
    kind: Literal["specimen", "occurrence"]
    source: Literal["ufvp", "pbdb"]
    label: str
    scientific_name: str
    locality_id: UUID | None
    locality_name: str | None
    older_ma: float | None
    younger_ma: float | None
    age_basis: str


class TaxonomyDetail(BaseModel):
    node: TaxonomyNode
    ancestors: list[TaxonomyNode]
    concepts: list[SourceConcept]
    concept_total: int
    evidence: list[EvidencePreview]
    version: str
