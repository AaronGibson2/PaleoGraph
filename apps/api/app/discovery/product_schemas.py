"""Bounded user-facing evidence contracts; museum material and occurrences stay distinct."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.discovery.schemas import CatalogItem, EntityDetail, LocalitySummary

SourceSelection = Literal["ufvp", "pbdb", "all"]
SourceCode = Literal["ufvp", "pbdb"]


class EvidenceCounts(BaseModel):
    museum_material: int = 0
    published_occurrences: int = 0


class EvidenceItem(CatalogItem):
    source: SourceCode
    source_dataset_id: UUID
    source_name: str
    source_license: str | None
    source_policy_version: str


class EvidencePage(BaseModel):
    items: list[EvidenceItem]
    total: int
    counts: EvidenceCounts
    next_cursor: str | None
    limit: int


class Identification(BaseModel):
    identified_name: str | None = None
    accepted_name: str | None = None
    identified_no: str | None = None
    accepted_no: str | None = None
    genus_reso: str | None = None
    species_reso: str | None = None
    reference_no: str | None = None


class ModernPosition(BaseModel):
    longitude: str | None
    latitude: str | None
    status: str
    basis: str | None
    precision: str | None


class DeterminedDate(BaseModel):
    value: str | None
    error: str | None
    unit: str | None
    method: str | None


class ProviderAge(BaseModel):
    older_ma: float | None
    younger_ma: float | None
    policy: str
    early_interval: str | None
    late_interval: str | None
    determined_dates: dict[str, DeterminedDate]


class MaterialLabel(BaseModel):
    catalog_label: str | None
    source_record_id: UUID


class OccurrenceEvidence(BaseModel):
    external_id: str
    original_identification: Identification
    latest_identification: Identification
    modern_position: ModernPosition
    provider_age: ProviderAge
    material_evidence_count: int
    materials: list[MaterialLabel]
    materials_has_more: bool
    content_hash: str
    normalization_hash: str
    license: str = "CC0 1.0"


class ReferenceItem(BaseModel):
    id: UUID
    external_id: str
    title: str | None
    doi: str | None
    published_year: str | None
    authors: str | None
    publication: str | None
    role: Literal["identification", "collection", "taxonomic opinion", "material", "reference"]
    evidence_source_record_id: UUID
    license: str = "CC0 1.0"


class ReferencePage(BaseModel):
    items: list[ReferenceItem]
    total: int
    next_cursor: str | None
    limit: int


class ProductDetail(EntityDetail):
    occurrence: OccurrenceEvidence | None = None
    reference: ReferenceItem | None = None


class CollectionContext(BaseModel):
    external_id: str
    source_record_id: UUID
    content_hash: str
    provider_age: ProviderAge
    modern_position: ModernPosition


class ProductLocalitySummary(LocalitySummary):
    collection_context: CollectionContext | None = None
