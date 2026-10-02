"""Canonical concepts and their source evidence; no specimen model in Phase 2."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Identity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# Explicit link tables preserve many-to-many evidence with real foreign keys.
taxon_evidence = Table(
    "taxon_evidence",
    Base.metadata,
    Column("taxon_id", ForeignKey("taxon.id"), primary_key=True),
    Column("source_record_id", ForeignKey("source_record.id"), primary_key=True),
)
locality_evidence = Table(
    "locality_evidence",
    Base.metadata,
    Column("locality_id", ForeignKey("locality.id"), primary_key=True),
    Column("source_record_id", ForeignKey("source_record.id"), primary_key=True),
)
event_evidence = Table(
    "collection_event_evidence",
    Base.metadata,
    Column("collection_event_id", ForeignKey("collection_event.id"), primary_key=True),
    Column("source_record_id", ForeignKey("source_record.id"), primary_key=True),
)
occurrence_evidence = Table(
    "occurrence_evidence",
    Base.metadata,
    Column("occurrence_id", ForeignKey("occurrence.id"), primary_key=True),
    Column("source_record_id", ForeignKey("source_record.id"), primary_key=True),
)


class Source(Identity, Base):
    __tablename__ = "source"
    name: Mapped[str] = mapped_column(String(200), unique=True)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    api_url: Mapped[str | None] = mapped_column(Text)


class SourceDataset(Identity, Base):
    __tablename__ = "source_dataset"
    __table_args__ = (UniqueConstraint("source_id", "external_dataset_id"),)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("source.id"))
    external_dataset_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    dataset_url: Mapped[str | None] = mapped_column(Text)
    citation: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text)
    rights_holder: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, server_default="false")
    source: Mapped[Source] = relationship()


class IngestionRun(Identity, Base):
    __tablename__ = "ingestion_run"
    __table_args__ = (
        UniqueConstraint("id", "source_dataset_id"),
        CheckConstraint("status IN ('running', 'completed', 'failed', 'partial')", name="status"),
        CheckConstraint(
            "records_read >= 0 AND records_inserted >= 0 AND records_updated >= 0 "
            "AND records_skipped >= 0 AND records_failed >= 0",
            name="counts",
        ),
    )
    source_dataset_id: Mapped[UUID] = mapped_column(ForeignKey("source_dataset.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    records_read: Mapped[int] = mapped_column(server_default="0")
    records_inserted: Mapped[int] = mapped_column(server_default="0")
    records_updated: Mapped[int] = mapped_column(server_default="0")
    records_skipped: Mapped[int] = mapped_column(server_default="0")
    records_failed: Mapped[int] = mapped_column(server_default="0")
    source_version: Mapped[str | None] = mapped_column(Text)
    error_summary: Mapped[str | None] = mapped_column(Text)


class SourceRecord(Identity, Base):
    __tablename__ = "source_record"
    __table_args__ = (
        UniqueConstraint("source_dataset_id", "record_type", "source_record_id"),
        ForeignKeyConstraint(
            ["ingestion_run_id", "source_dataset_id"],
            ["ingestion_run.id", "ingestion_run.source_dataset_id"],
        ),
        CheckConstraint("last_seen_at >= first_seen_at", name="seen_order"),
    )
    source_dataset_id: Mapped[UUID] = mapped_column(ForeignKey("source_dataset.id"))
    ingestion_run_id: Mapped[UUID] = mapped_column()
    source_record_id: Mapped[str] = mapped_column(Text)
    record_type: Mapped[str] = mapped_column(String(50))
    source_url: Mapped[str | None] = mapped_column(Text)
    basis_of_record: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text)
    rights_holder: Mapped[str | None] = mapped_column(Text)
    access_rights: Mapped[str | None] = mapped_column(Text)
    information_withheld: Mapped[str | None] = mapped_column(Text)
    data_generalizations: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    source_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default="true")
    dataset: Mapped[SourceDataset] = relationship()


class Taxon(Identity, Base):
    __tablename__ = "taxon"
    scientific_name: Mapped[str] = mapped_column(Text)
    rank: Mapped[str | None] = mapped_column(String(50))
    source_records: Mapped[list[SourceRecord]] = relationship(secondary=taxon_evidence)


class Locality(Identity, Base):
    __tablename__ = "locality"
    __table_args__ = (
        CheckConstraint(
            "geom IS NULL OR (NOT ST_IsEmpty(geom) AND ST_X(geom) BETWEEN -180 AND 180 "
            "AND ST_Y(geom) BETWEEN -90 AND 90)",
            name="valid_point",
        ),
        CheckConstraint("NOT location_is_withheld OR geom IS NULL", name="withheld_point"),
        CheckConstraint(
            "coordinate_uncertainty_m >= 0 AND coordinate_uncertainty_m < 'Infinity'::float8",
            name="uncertainty",
        ),
        CheckConstraint(
            "coordinate_precision >= 0 AND coordinate_precision < 'Infinity'::float8",
            name="precision",
        ),
        Index("ix_locality_geom", "geom", postgresql_using="gist"),
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[WKBElement | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )
    # Verbatim source strings, not competing normalized coordinate columns.
    original_latitude: Mapped[str | None] = mapped_column(Text)
    original_longitude: Mapped[str | None] = mapped_column(Text)
    coordinate_uncertainty_m: Mapped[float | None] = mapped_column(Float)
    coordinate_precision: Mapped[float | None] = mapped_column(Float)
    geodetic_datum: Mapped[str | None] = mapped_column(Text)
    location_is_generalized: Mapped[bool] = mapped_column(Boolean, server_default="false")
    location_is_withheld: Mapped[bool] = mapped_column(Boolean, server_default="false")
    information_withheld: Mapped[str | None] = mapped_column(Text)
    source_records: Mapped[list[SourceRecord]] = relationship(secondary=locality_evidence)


class CollectionEvent(Identity, Base):
    __tablename__ = "collection_event"
    __table_args__ = (
        CheckConstraint("older_ma >= 0 AND older_ma < 'Infinity'::numeric", name="older_age"),
        CheckConstraint("younger_ma >= 0 AND younger_ma < 'Infinity'::numeric", name="younger_age"),
        CheckConstraint("older_ma >= younger_ma", name="age_order"),
    )
    locality_id: Mapped[UUID | None] = mapped_column(ForeignKey("locality.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text)
    stratigraphy: Mapped[str | None] = mapped_column(Text)
    older_ma: Mapped[Decimal | None] = mapped_column(Numeric())
    younger_ma: Mapped[Decimal | None] = mapped_column(Numeric())
    early_interval_name: Mapped[str | None] = mapped_column(Text)
    late_interval_name: Mapped[str | None] = mapped_column(Text)
    locality: Mapped[Locality | None] = relationship()
    source_records: Mapped[list[SourceRecord]] = relationship(secondary=event_evidence)


class Occurrence(Identity, Base):
    __tablename__ = "occurrence"
    taxon_id: Mapped[UUID] = mapped_column(ForeignKey("taxon.id"))
    collection_event_id: Mapped[UUID] = mapped_column(ForeignKey("collection_event.id"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    taxon: Mapped[Taxon] = relationship()
    collection_event: Mapped[CollectionEvent] = relationship()
    source_records: Mapped[list[SourceRecord]] = relationship(secondary=occurrence_evidence)
