from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityKind = Literal["specimen", "taxon", "locality", "collection", "institution", "term"]


class ContextQuery(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    taxon_id: UUID | None = None
    locality_id: UUID | None = None
    collection_id: UUID | None = None
    institution_id: UUID | None = None
    term_id: UUID | None = None
    older_ma: float | None = Field(default=None, ge=0, le=10000)
    younger_ma: float | None = Field(default=None, ge=0, le=10000)
    at_lon: float | None = Field(default=None, ge=-180, le=180)
    at_lat: float | None = Field(default=None, ge=-90, le=90)
    west: float | None = Field(default=None, ge=-180, le=180)
    east: float | None = Field(default=None, ge=-180, le=180)
    south: float | None = Field(default=None, ge=-90, le=90)
    north: float | None = Field(default=None, ge=-90, le=90)
    q: str = Field(default="", max_length=160)
    limit: int = Field(default=30, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_pairs(self) -> Self:
        if (self.older_ma is None) != (self.younger_ma is None):
            raise ValueError("Provide both age bounds")
        if self.older_ma is not None and self.younger_ma is not None:
            if self.older_ma < self.younger_ma:
                raise ValueError("Older age must be greater than or equal to younger age")
        if (self.at_lon is None) != (self.at_lat is None):
            raise ValueError("Provide both place coordinates")
        bounds = (self.west, self.east, self.south, self.north)
        if any(value is not None for value in bounds) and any(value is None for value in bounds):
            raise ValueError("Provide all four viewport bounds")
        if self.south is not None and self.north is not None and self.south > self.north:
            raise ValueError("South must not exceed north")
        return self


class EntityRef(BaseModel):
    kind: EntityKind
    id: UUID
    label: str
    subtitle: str | None = None
    classification: list[str] = Field(default_factory=list)


class AssociationQuery(ContextQuery):
    order: Literal["count", "name", "hierarchy"] = "count"


class LineageQuery(ContextQuery):
    focus: UUID | None = None


class PlaceQuery(ContextQuery):
    limit: int = Field(default=1500, ge=1, le=5000)


class CatalogItem(BaseModel):
    id: UUID
    specimen_id: UUID
    label: str
    scientific_name: str
    taxon_id: UUID
    locality_id: UUID | None
    locality_name: str | None
    longitude: float | None
    latitude: float | None
    older_ma: float | None
    younger_ma: float | None
    age_basis: str
    source_age_label: str | None


class CatalogPage(BaseModel):
    items: list[CatalogItem]
    total: int
    next_cursor: str | None
    limit: int


class SearchPage(BaseModel):
    items: list[EntityRef]
    total: int
    next_cursor: str | None
    limit: int


class Place(BaseModel):
    id: UUID
    longitude: float
    latitude: float
    record_count: int
    locality_count: int
    interpreted_count: int
    location_is_generalized: bool


class PlacePage(BaseModel):
    items: list[Place]
    total_records: int
    total_places: int
    unmapped_records: int
    next_cursor: str | None
    limit: int


class EntityDetail(BaseModel):
    entity: EntityRef
    material_count: int
    mapped_count: int
    related: list[EntityRef]
    related_has_more: bool
    properties: dict[str, Any]
    research_note: str


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str


class GraphPage(BaseModel):
    root: EntityRef
    nodes: list[EntityRef]
    edges: list[GraphEdge]
    total_neighbors: int
    next_cursor: str | None
    limit: int


class AssociationItem(EntityRef):
    assertion_count: int
    specimen_count: int
    source_taxon_count: int
    older_ma: float | None
    younger_ma: float | None
    known_age_count: int
    unknown_age_count: int


class AssociationPage(BaseModel):
    items: list[AssociationItem]
    total: int
    next_cursor: str | None
    limit: int


class LocalitySummary(BaseModel):
    entity: EntityRef
    assertion_count: int
    specimen_count: int
    source_taxon_count: int
    collection_count: int
    institution_count: int
    known_age_count: int
    unknown_age_count: int
    older_ma: float | None
    younger_ma: float | None
    properties: dict[str, Any]
    source_terms: list[dict[str, Any]]
    interpreted_intervals: list[dict[str, Any]]
    custody: list[dict[str, Any]]
    related_localities: list[EntityRef]


class LineageItem(AssociationItem):
    parent_id: UUID | None
    has_children: bool
    is_source_identification: bool


class LineagePage(BaseModel):
    items: list[LineageItem]
    focus: EntityRef | None
    focal: LineageItem | None = None
    breadcrumbs: list[EntityRef]
    total: int
    next_cursor: str | None
    limit: int
    relationship: str = "source-classification membership; not ancestry"
