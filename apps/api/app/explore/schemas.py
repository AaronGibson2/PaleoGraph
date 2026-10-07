from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExploreQuery(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    older_ma: float | None = Field(default=None, ge=0, le=10000)
    younger_ma: float | None = Field(default=None, ge=0, le=10000)
    limit: int = Field(default=200, ge=1, le=1000)

    @model_validator(mode="after")
    def ordered_bounds(self) -> Self:
        if self.south > self.north:
            raise ValueError("south must be less than or equal to north")
        if (self.older_ma is None) != (self.younger_ma is None):
            raise ValueError("Provide both older_ma and younger_ma, or neither")
        if self.older_ma is not None and self.younger_ma is not None:
            if self.older_ma < self.younger_ma:
                raise ValueError("older_ma must be greater than or equal to younger_ma")
        return self


class MapOccurrence(BaseModel):
    id: UUID
    scientific_name: str
    locality_name: str
    longitude: float
    latitude: float
    older_ma: float | None
    younger_ma: float | None
    location_is_generalized: bool
    is_synthetic: bool
    catalog_label: str | None = None
    source_age_label: str | None = None


class MapResponse(BaseModel):
    items: list[MapOccurrence]
    returned: int
    truncated: bool
    limit: int


class Evidence(BaseModel):
    source_record_id: str
    source_name: str
    source_url: str | None
    dataset_id: UUID
    dataset_title: str
    dataset_url: str | None
    publisher: str | None
    citation: str | None
    license: str | None
    rights_holder: str | None
    dataset_version: str | None
    ingestion_run_id: UUID
    ingested_at: datetime
    is_current: bool
    is_synthetic: bool
    information_withheld: str | None
    data_generalizations: str | None


class SpecimenDetail(BaseModel):
    id: UUID
    institution: str | None
    institution_code: str | None
    collection_code: str | None
    catalog_number: str | None
    occurrence_identifier: str | None
    material_entity_identifier: str | None
    other_identifiers: dict[str, object] | None
    preparations: str | None
    individual_count: str | None


class OccurrenceDetail(BaseModel):
    """Canonical source numeric bounds, independent of label interpretation.
    Null/partial values remain unknown; source_values retains exact public geology.
    Collecting eventDate is not the geological age of the fossil.
    """

    id: UUID
    taxon_id: UUID
    scientific_name: str
    rank: str | None
    collection_event_id: UUID
    collection_event_name: str
    context: str | None
    stratigraphy: str | None
    older_ma: float | None
    younger_ma: float | None
    early_interval_name: str | None
    late_interval_name: str | None
    locality_id: UUID | None
    locality_name: str | None
    latitude: float | None
    longitude: float | None
    coordinate_uncertainty_m: float | None
    location_is_generalized: bool
    location_is_withheld: bool
    notes: str | None
    evidence: list[Evidence]
    specimen: SpecimenDetail | None = None
    source_values: dict[str, str] = Field(default_factory=dict)


class DatasetStatus(BaseModel):
    published_occurrences: int = 0
    published_contexts: int = 0
    published_mapped_occurrences: int = 0
    pbdb_license: str | None = None
    pbdb_version: str | None = None
    title: str
    dataset_url: str
    license: str | None
    version: str | None
    current_records: int
    mapped_records: int
    latest_scope: str | None
    latest_status: str | None
    numeric_age_records: int
    creator: str | None
    browse_revision: str | None = None
