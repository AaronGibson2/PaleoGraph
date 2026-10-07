from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityKind = Literal[
    "specimen", "occurrence", "reference", "taxon", "locality", "collection", "institution", "term"
]


class ContextQuery(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    source: Literal["ufvp", "pbdb", "all"] = "ufvp"
    reference_id: UUID | None = None
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
    source: Literal["ufvp", "pbdb"] | None = None
    kind: EntityKind
    id: UUID
    label: str
    subtitle: str | None = None
    classification: list[str] = Field(default_factory=list)
    classification_path_ids: list[UUID] = Field(
        default_factory=list,
        description="Source classification membership, identification/self first then "
        "nearest parents; not phylogeny",
    )


class AssociationQuery(ContextQuery):
    order: Literal["count", "name", "hierarchy"] = "count"


class LineageQuery(ContextQuery):
    focus: UUID | None = None


class PlaceQuery(ContextQuery):
    limit: int = Field(default=1500, ge=1, le=5000)


class CatalogItem(BaseModel):
    """Effective envelope; age_basis distinguishes complete source bounds from
    separately derived reference bounds. source_age_label is trimmed evidence,
    not the normalized interval name; exact wording remains in occurrence detail.
    """

    id: UUID
    specimen_id: UUID | None
    evidence_kind: Literal["material", "occurrence"] = "material"
    material_evidence_count: int = 0
    label: str
    scientific_name: str
    taxon_id: UUID
    classification_path_ids: list[UUID] = Field(default_factory=list)
    locality_id: UUID | None
    locality_name: str | None
    longitude: float | None
    latitude: float | None
    older_ma: float | None = Field(
        description="Older effective envelope bound in Ma, not a measured specimen date"
    )
    younger_ma: float | None = Field(
        description="Younger effective envelope bound in Ma; zero means present, null unknown"
    )
    age_basis: str = Field(
        description="source-numeric, derived-interval, absent, ambiguous, or unmapped"
    )
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
    museum_material: int = 0
    published_occurrences: int = 0
    id: UUID
    longitude: float
    latitude: float
    record_count: int
    locality_count: int
    interpreted_count: int = Field(
        description="Legacy name: assertions with complete effective numeric envelopes, "
        "including source numeric ages"
    )
    location_is_generalized: bool


class PlacePage(BaseModel):
    museum_material: int = 0
    published_occurrences: int = 0
    unmapped_published_occurrences: int = 0
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
    """Outer envelope of complete material bounds in context, not biological duration.
    Known counts include both source numeric and derived intervals; incomplete
    assertions contribute to unknown counts and never to either envelope endpoint.
    """

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
    """Material aggregate under the active context, not source-supplied locality age.
    source_terms are source evidence; interpreted_intervals retain age_basis for
    complete source bounds, interpreted label envelopes, and unresolved groups.
    """

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
