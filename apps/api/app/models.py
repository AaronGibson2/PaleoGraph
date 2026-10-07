"""Canonical concepts and their independently retained source evidence."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
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
    text,
)
from sqlalchemy import (
    Identity as DatabaseIdentity,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
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
specimen_evidence = Table(
    "specimen_evidence",
    Base.metadata,
    Column("specimen_id", ForeignKey("specimen.id"), primary_key=True),
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
    publication_archive_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_archive.id"))
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
        CheckConstraint("records_accepted >= 0", name="accepted_count"),
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
    records_accepted: Mapped[int] = mapped_column(server_default="0")
    importer_version: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    scope: Mapped[str | None] = mapped_column(Text)


class SourceRecord(Identity, Base):
    __tablename__ = "source_record"
    __table_args__ = (
        UniqueConstraint("source_dataset_id", "record_type", "source_record_id"),
        ForeignKeyConstraint(
            ["ingestion_run_id", "source_dataset_id"],
            ["ingestion_run.id", "ingestion_run.source_dataset_id"],
        ),
        CheckConstraint("last_seen_at >= first_seen_at", name="seen_order"),
        Index(
            "ix_source_record_current_catalog",
            "id",
            postgresql_include=["content_hash", "source_dataset_id"],
            postgresql_where=text("is_current"),
        ),
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
    run: Mapped[IngestionRun] = relationship(viewonly=True)


class SourceArchive(Identity, Base):
    """Provider-neutral, immutable verified source export and its deterministic manifest."""

    __tablename__ = "source_archive"
    provider: Mapped[str] = mapped_column(Text)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    manifest_hash: Mapped[str] = mapped_column(String(64), unique=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scope: Mapped[dict[str, object]] = mapped_column(JSONB)
    adapter_version: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(Text)
    rights: Mapped[str] = mapped_column(Text)
    storage_reference: Mapped[str] = mapped_column(Text)
    compression: Mapped[str] = mapped_column(Text, server_default="'gzip'")
    byte_size: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(Text)
    manifest: Mapped[dict[str, object]] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint("state IN ('writing','verifying','ready')", name="state"),
        CheckConstraint("byte_size >= 0 AND compression='gzip'", name="format"),
    )


class SourceArchiveObject(Base):
    __tablename__ = "source_archive_object"
    id: Mapped[int] = mapped_column(BigInteger, DatabaseIdentity(), primary_key=True)
    archive_id: Mapped[UUID] = mapped_column(ForeignKey("source_archive.id"), index=True)
    object_hash: Mapped[str] = mapped_column(String(64))
    original_hash: Mapped[str] = mapped_column(String(64))
    compressed_bytes: Mapped[int] = mapped_column(BigInteger)
    original_bytes: Mapped[int] = mapped_column(BigInteger)
    record_count: Mapped[int] = mapped_column()
    kind: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("archive_id", "object_hash"),
        CheckConstraint(
            "compressed_bytes >= 0 AND original_bytes >= 0 AND record_count >= 0",
            name="sizes",
        ),
    )


class GlobalIngestionJob(Identity, Base):
    """Durable disposable/production run checkpoints; never a published scientific revision."""

    __tablename__ = "global_ingestion_job"
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("source_dataset.id"))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    archive_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_archive.id"))
    state: Mapped[str] = mapped_column(Text)
    staging_schema: Mapped[str] = mapped_column(Text, unique=True)
    checkpoint: Mapped[dict[str, object]] = mapped_column(JSONB)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("dataset_id", "snapshot_hash"),
        CheckConstraint(
            "state IN ('archiving','staging','normalizing','validated',"
            "'publishing','ready','failed')",
            name="state",
        ),
    )


class SourceProofEdge(Base):
    """Full flattened version proof; original UUID/SHA identities remain on the nodes."""

    __tablename__ = "source_proof_edge"
    normalization_key: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("normalized_source_revision.normalization_key"), primary_key=True
    )
    revision_key: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("source_record_revision.revision_key"), primary_key=True, index=True
    )


class SourceNormalizationInvalid(Base):
    """Derived exact invalidity, refreshed at writes; avoids traversing proofs in each read."""

    __tablename__ = "source_normalization_invalid"
    source_record_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    normalization_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "content_hash", "normalization_hash"],
            [
                "normalized_source_revision.source_record_id",
                "normalized_source_revision.content_hash",
                "normalized_source_revision.normalization_hash",
            ],
            ondelete="CASCADE",
        ),
    )


class SourceRecordRevision(Base):
    """Immutable changed content; unchanged observations are tracked by the run snapshot."""

    __tablename__ = "source_record_revision"
    source_record_id: Mapped[UUID] = mapped_column(ForeignKey("source_record.id"), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    ingestion_run_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_run.id"))
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    revision_key: Mapped[int] = mapped_column(BigInteger, DatabaseIdentity(), unique=True)
    archive_object_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_archive_object.id"), index=True
    )
    archive_row: Mapped[int | None] = mapped_column()
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "raw_payload IS NOT NULL OR (archive_object_id IS NOT NULL "
            "AND archive_row IS NOT NULL AND archive_row >= 0)",
            name="raw_evidence_retained",
        ),
    )


class NormalizedSourceRevision(Base):
    """Retained source-specific normalization, including its exact dependency frame."""

    __tablename__ = "normalized_source_revision"
    source_record_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    normalization_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    adapter_version: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    ingestion_run_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_run.id"))
    normalization_key: Mapped[int] = mapped_column(BigInteger, DatabaseIdentity(), unique=True)
    frame_format: Mapped[str] = mapped_column(Text, server_default="'full'")
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
        ),
        CheckConstraint("frame_format IN ('full','compact')", name="frame_format"),
    )


class SourceNormalizationCurrent(Base):
    __tablename__ = "source_normalization_current"
    source_record_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    normalization_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "content_hash", "normalization_hash"],
            [
                "normalized_source_revision.source_record_id",
                "normalized_source_revision.content_hash",
                "normalized_source_revision.normalization_hash",
            ],
        ),
    )


class SourceRecordDependency(Base):
    """Versioned typed record dependencies, never name-similarity relationships."""

    __tablename__ = "source_record_dependency"
    source_record_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    normalization_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    dependency_record_id: Mapped[UUID] = mapped_column(primary_key=True, index=True)
    dependency_content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "content_hash", "normalization_hash"],
            [
                "normalized_source_revision.source_record_id",
                "normalized_source_revision.content_hash",
                "normalized_source_revision.normalization_hash",
            ],
        ),
        ForeignKeyConstraint(
            ["dependency_record_id", "dependency_content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
        ),
    )


class ProviderAgeEvidence(Base):
    """Provider-calibrated context envelope, distinct from local interpretation/determination."""

    __tablename__ = "provider_age_evidence"
    source_record_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_version: Mapped[str] = mapped_column(Text, primary_key=True)
    older_ma: Mapped[Decimal | None] = mapped_column(Numeric())
    younger_ma: Mapped[Decimal | None] = mapped_column(Numeric())
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
        ),
        CheckConstraint(
            "older_ma >= 0 AND older_ma < 'Infinity'::numeric AND "
            "younger_ma >= 0 AND younger_ma < 'Infinity'::numeric AND "
            "older_ma >= younger_ma",
            name="bounds",
        ),
    )


class ResearchReference(Identity, Base):
    __tablename__ = "research_reference"
    source_record_id: Mapped[UUID] = mapped_column(ForeignKey("source_record.id"), unique=True)
    source_dataset_id: Mapped[UUID] = mapped_column(ForeignKey("source_dataset.id"))
    title: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(Text)
    published_year: Mapped[str | None] = mapped_column(Text)
    bibliography: Mapped[dict[str, object]] = mapped_column(JSONB)


class IdentificationEvidence(Base):
    __tablename__ = "identification_evidence"
    source_record_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    occurrence_id: Mapped[UUID] = mapped_column(ForeignKey("occurrence.id"), index=True)
    reference_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_reference.id"))
    taxon_id: Mapped[UUID] = mapped_column(ForeignKey("taxon.id"))
    provider_identification_id: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)
    __table_args__ = (
        Index("ix_identification_reference_occurrence", "reference_id", "occurrence_id"),
        ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
        ),
    )


class MaterialEvidence(Base):
    __tablename__ = "material_evidence"
    source_record_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    occurrence_id: Mapped[UUID | None] = mapped_column(ForeignKey("occurrence.id"), index=True)
    reference_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_reference.id"))
    catalog_label: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
        ),
    )


class ReconciliationGeneration(Base):
    """Atomic current-frame pointer; neither scientific dataset is republished."""

    __tablename__ = "reconciliation_generation"
    subject_dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_dataset.id"), primary_key=True
    )
    target_dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_dataset.id"), primary_key=True
    )
    policy_version: Mapped[str] = mapped_column(Text, primary_key=True)
    input_digest: Mapped[str] = mapped_column(String(64))
    source_state: Mapped[dict[str, object]] = mapped_column(JSONB)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint("subject_dataset_id <> target_dataset_id", name="independent_sources"),
    )


class ReconciliationAssessment(Identity, Base):
    """Versioned outcome, including unresolved and ambiguous material evidence."""

    __tablename__ = "reconciliation_assessment"
    subject_dataset_id: Mapped[UUID] = mapped_column(ForeignKey("source_dataset.id"))
    target_dataset_id: Mapped[UUID] = mapped_column(ForeignKey("source_dataset.id"))
    source_record_id: Mapped[UUID] = mapped_column(index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    normalization_hash: Mapped[str] = mapped_column(String(64))
    occurrence_id: Mapped[UUID | None] = mapped_column(ForeignKey("occurrence.id"))
    policy_version: Mapped[str] = mapped_column(Text)
    input_digest: Mapped[str] = mapped_column(String(64))
    creation_method: Mapped[str] = mapped_column(Text, server_default="automatic")
    status: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    normalized_identifier: Mapped[dict[str, object]] = mapped_column(JSONB)
    original_values: Mapped[dict[str, object]] = mapped_column(JSONB)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB)
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "content_hash", "normalization_hash"],
            [
                "normalized_source_revision.source_record_id",
                "normalized_source_revision.content_hash",
                "normalized_source_revision.normalization_hash",
            ],
        ),
        UniqueConstraint(
            "source_record_id",
            "content_hash",
            "normalization_hash",
            "target_dataset_id",
            "policy_version",
            "input_digest",
            name="uq_reconciliation_assessment_frame",
        ),
        CheckConstraint("subject_dataset_id <> target_dataset_id", name="independent_sources"),
        CheckConstraint(
            "status IN ('deterministic','candidate','ambiguous',"
            "'conflict','unresolved','rejected')",
            name="status",
        ),
        CheckConstraint("creation_method IN ('automatic','manual')", name="creation_method"),
        Index(
            "ix_reconciliation_assessment_generation",
            "subject_dataset_id",
            "target_dataset_id",
            "policy_version",
            "input_digest",
        ),
    )


class ReconciliationEdge(Identity, Base):
    """Material evidence references material; never a generic same_as merge."""

    __tablename__ = "reconciliation_edge"
    assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("reconciliation_assessment.id", ondelete="CASCADE"), index=True
    )
    target_specimen_id: Mapped[UUID] = mapped_column(index=True)
    target_source_record_id: Mapped[UUID] = mapped_column(index=True)
    target_content_hash: Mapped[str] = mapped_column(String(64))
    relationship_type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    diagnostics: Mapped[dict[str, object]] = mapped_column(JSONB)
    supporting_reference_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_reference.id")
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["target_specimen_id", "target_source_record_id"],
            ["specimen_evidence.specimen_id", "specimen_evidence.source_record_id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["target_source_record_id", "target_content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
        ),
        UniqueConstraint(
            "assessment_id",
            "target_specimen_id",
            "target_source_record_id",
            "target_content_hash",
            name="uq_reconciliation_edge_proof",
        ),
        CheckConstraint(
            "relationship_type IN ('material_identifier_matches','candidate_same_specimen')",
            name="type",
        ),
        CheckConstraint(
            "(relationship_type='material_identifier_matches' AND status='deterministic') OR "
            "(relationship_type='candidate_same_specimen' AND status IN ('candidate','ambiguous'))",
            name="type_status",
        ),
    )


class ReconciliationReview(Base):
    """Review annotations survive automatic rebuild; acceptance never rewrites a source."""

    __tablename__ = "reconciliation_review"
    edge_id: Mapped[UUID] = mapped_column(ForeignKey("reconciliation_edge.id"), primary_key=True)
    decision: Mapped[str] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint("decision IN ('accept','reject','unresolved')", name="decision"),
        CheckConstraint("btrim(reviewer) <> '' AND btrim(reason) <> ''", name="provenance"),
    )


class CollectionReferenceEvidence(Base):
    __tablename__ = "collection_reference_evidence"
    source_record_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    collection_event_id: Mapped[UUID] = mapped_column(ForeignKey("collection_event.id"))
    reference_id: Mapped[UUID] = mapped_column(ForeignKey("research_reference.id"))
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
        ),
    )


class OpinionReferenceEvidence(Base):
    __tablename__ = "opinion_reference_evidence"
    source_record_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    reference_id: Mapped[UUID] = mapped_column(ForeignKey("research_reference.id"))
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
        ),
    )


class Institution(Identity, Base):
    __tablename__ = "institution"
    name: Mapped[str] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)


class Collection(Identity, Base):
    __tablename__ = "collection"
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institution.id"))
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    institution: Mapped[Institution] = relationship()


class Specimen(Identity, Base):
    __tablename__ = "specimen"
    __table_args__ = (
        Index(
            "ix_specimen_reconciliation_key",
            "institution_code",
            "catalog_number",
            "collection_code",
        ),
    )
    collection_id: Mapped[UUID | None] = mapped_column(ForeignKey("collection.id"))
    institution_code: Mapped[str | None] = mapped_column(Text)
    collection_code: Mapped[str | None] = mapped_column(Text)
    catalog_number: Mapped[str | None] = mapped_column(Text)
    occurrence_identifier: Mapped[str | None] = mapped_column(Text)
    material_entity_identifier: Mapped[str | None] = mapped_column(Text)
    other_identifiers: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    preparations: Mapped[str | None] = mapped_column(Text)
    individual_count: Mapped[str | None] = mapped_column(Text)
    collection: Mapped[Collection | None] = relationship()
    source_records: Mapped[list[SourceRecord]] = relationship(secondary=specimen_evidence)


class Taxon(Identity, Base):
    __tablename__ = "taxon"
    scientific_name: Mapped[str] = mapped_column(Text)
    rank: Mapped[str | None] = mapped_column(String(50))
    source_dataset_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_dataset.id"))
    parent_taxon_id: Mapped[UUID | None] = mapped_column(ForeignKey("taxon.id"), index=True)
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
    specimen_id: Mapped[UUID | None] = mapped_column(ForeignKey("specimen.id"), index=True)
    specimen: Mapped[Specimen | None] = relationship()
    taxon: Mapped[Taxon] = relationship()
    collection_event: Mapped[CollectionEvent] = relationship()
    source_records: Mapped[list[SourceRecord]] = relationship(secondary=occurrence_evidence)


class GeologicalInterval(Base):
    """Pinned reference calibration, never an observed specimen age."""

    __tablename__ = "geological_interval"
    __table_args__ = (CheckConstraint("older_ma >= younger_ma AND younger_ma >= 0", name="bounds"),)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    rank: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("geological_interval.id"))
    older_ma: Mapped[Decimal] = mapped_column(Numeric())
    younger_ma: Mapped[Decimal] = mapped_column(Numeric())
    color: Mapped[str] = mapped_column(String(7))
    reference: Mapped[dict[str, object]] = mapped_column(JSONB)


class AgeInterpretation(Base):
    """Immutable interpretation of one retained source content revision."""

    __tablename__ = "age_interpretation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "content_hash"],
            ["source_record_revision.source_record_id", "source_record_revision.content_hash"],
        ),
        CheckConstraint("status IN ('mapped', 'ambiguous', 'unmapped', 'absent')", name="status"),
        CheckConstraint("older_ma >= younger_ma AND younger_ma >= 0", name="bounds"),
        CheckConstraint(
            "(status = 'mapped' AND interval_id IS NOT NULL AND older_ma IS NOT NULL "
            "AND younger_ma IS NOT NULL) OR (status <> 'mapped' AND interval_id IS NULL "
            "AND older_ma IS NULL AND younger_ma IS NULL)",
            name="mapping",
        ),
    )
    source_record_id: Mapped[UUID] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_version: Mapped[str] = mapped_column(Text, primary_key=True)
    interval_id: Mapped[str | None] = mapped_column(ForeignKey("geological_interval.id"))
    source_field: Mapped[str | None] = mapped_column(Text)
    source_label: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    rule: Mapped[str] = mapped_column(Text)
    older_ma: Mapped[Decimal | None] = mapped_column(Numeric())
    younger_ma: Mapped[Decimal | None] = mapped_column(Numeric())
    interpreted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TaxonPath(Base):
    __tablename__ = "taxon_path"
    taxon_id: Mapped[UUID] = mapped_column(ForeignKey("taxon.id"), primary_key=True)
    ancestor_id: Mapped[UUID] = mapped_column(ForeignKey("taxon.id"), primary_key=True, index=True)


class ContextTerm(Base):
    """An exact source assertion, not an inferred geological relationship."""

    __tablename__ = "context_term"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_dataset_id: Mapped[UUID] = mapped_column(ForeignKey("source_dataset.id"))
    field: Mapped[str] = mapped_column(Text)
    namespace: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        Index(
            "ix_context_term_search",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )


class CatalogEntry(Base):
    """Rebuildable public discovery projection with actual canonical foreign keys."""

    __tablename__ = "catalog_entry"
    occurrence_id: Mapped[UUID] = mapped_column(ForeignKey("occurrence.id"), primary_key=True)
    specimen_id: Mapped[UUID | None] = mapped_column(ForeignKey("specimen.id"), index=True)
    taxon_id: Mapped[UUID] = mapped_column(ForeignKey("taxon.id"), index=True)
    locality_id: Mapped[UUID | None] = mapped_column(ForeignKey("locality.id"), index=True)
    collection_id: Mapped[UUID | None] = mapped_column(ForeignKey("collection.id"), index=True)
    institution_id: Mapped[UUID | None] = mapped_column(ForeignKey("institution.id"), index=True)
    source_record_id: Mapped[UUID] = mapped_column(ForeignKey("source_record.id"), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(Text)
    evidence_kind: Mapped[str] = mapped_column(Text, server_default="material")
    material_evidence_count: Mapped[int] = mapped_column(server_default="0")
    normalization_hash: Mapped[str | None] = mapped_column(String(64))
    interpretation_policy_version: Mapped[str | None] = mapped_column(
        Text, server_default="ufvp-geology-v1:ics-2026-06"
    )
    provider_age_source_record_id: Mapped[UUID | None] = mapped_column()
    provider_age_content_hash: Mapped[str | None] = mapped_column(String(64))
    provider_age_policy_version: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    scientific_name: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text)
    search_vector: Mapped[object] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple'::regconfig, search_text)", persisted=True)
    )
    older_ma: Mapped[Decimal | None] = mapped_column(Numeric())
    younger_ma: Mapped[Decimal | None] = mapped_column(Numeric())
    age_basis: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        Index(
            "ix_catalog_occurrence_product_page",
            "occurrence_id",
            postgresql_include=[
                "source_record_id",
                "content_hash",
                "normalization_hash",
                "policy_version",
            ],
            postgresql_where=text("evidence_kind='occurrence'"),
        ),
        ForeignKeyConstraint(
            ["source_record_id", "content_hash", "interpretation_policy_version"],
            [
                "age_interpretation.source_record_id",
                "age_interpretation.content_hash",
                "age_interpretation.policy_version",
            ],
        ),
        ForeignKeyConstraint(
            ["source_record_id", "content_hash", "normalization_hash"],
            [
                "normalized_source_revision.source_record_id",
                "normalized_source_revision.content_hash",
                "normalized_source_revision.normalization_hash",
            ],
        ),
        ForeignKeyConstraint(
            [
                "provider_age_source_record_id",
                "provider_age_content_hash",
                "provider_age_policy_version",
            ],
            [
                "provider_age_evidence.source_record_id",
                "provider_age_evidence.content_hash",
                "provider_age_evidence.policy_version",
            ],
        ),
        CheckConstraint(
            "(evidence_kind = 'material' AND specimen_id IS NOT NULL) OR "
            "(evidence_kind = 'occurrence' AND specimen_id IS NULL)",
            name="evidence_kind",
        ),
        CheckConstraint("material_evidence_count >= 0", name="material_evidence_count"),
        CheckConstraint(
            "interpretation_policy_version IS NULL OR "
            "interpretation_policy_version = policy_version",
            name="interpretation_policy",
        ),
        CheckConstraint(
            "provider_age_policy_version IS NULL OR provider_age_policy_version = policy_version",
            name="provider_policy",
        ),
        CheckConstraint(
            "num_nonnulls(provider_age_source_record_id,provider_age_content_hash,"
            "provider_age_policy_version) IN (0,3)",
            name="provider_age_key",
        ),
        CheckConstraint(
            "interpretation_policy_version IS NULL OR provider_age_policy_version IS NULL",
            name="age_evidence_boundary",
        ),
        CheckConstraint(
            "(evidence_kind = 'material' AND interpretation_policy_version IS NOT NULL) OR "
            "(evidence_kind = 'occurrence' AND normalization_hash IS NOT NULL AND "
            "provider_age_policy_version IS NOT NULL)",
            name="age_proof",
        ),
        Index("ix_catalog_entry_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_catalog_entry_search_text",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
        Index("ix_catalog_entry_label", "label", postgresql_ops={"label": "text_pattern_ops"}),
        Index("ix_catalog_entry_age", "older_ma", "younger_ma"),
        Index(
            "ix_catalog_entry_locality_page",
            "locality_id",
            "occurrence_id",
            postgresql_include=["source_record_id", "content_hash", "policy_version"],
        ),
    )


class CatalogTerm(Base):
    __tablename__ = "catalog_term"
    occurrence_id: Mapped[UUID] = mapped_column(
        ForeignKey("catalog_entry.occurrence_id"), primary_key=True
    )
    term_id: Mapped[UUID] = mapped_column(
        ForeignKey("context_term.id"), primary_key=True, index=True
    )


class ClassificationLink(Base):
    """Rebuildable source-rank links. This is a projection, not a phylogenetic entity."""

    __tablename__ = "classification_link"
    taxon_id: Mapped[UUID] = mapped_column(
        ForeignKey("taxon.id", ondelete="CASCADE"), primary_key=True
    )
    parent_taxon_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("taxon.id", ondelete="SET NULL"), index=True
    )
    __table_args__ = (
        CheckConstraint("taxon_id <> parent_taxon_id", name="ck_classification_no_self_parent"),
    )


class BrowseProjectionState(Base):
    """One transactional generation for disposable browse summaries, not source facts."""

    __tablename__ = "browse_projection_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    input_revision: Mapped[int] = mapped_column(BigInteger, server_default="0")
    built_revision: Mapped[int | None] = mapped_column(BigInteger)
    projection_version: Mapped[str | None] = mapped_column(Text)
    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)


class OccurrenceBrowseState(Base):
    """Versioned derived occurrence eligibility, invalidated by the shared input counter."""

    __tablename__ = "occurrence_browse_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    built_revision: Mapped[int] = mapped_column(BigInteger)
    projection_version: Mapped[str] = mapped_column(Text)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)


class OccurrenceBrowseMember(Base):
    """Disposable eligible membership; retained normalized evidence remains authoritative."""

    __tablename__ = "occurrence_browse_member"
    occurrence_id: Mapped[UUID] = mapped_column(
        ForeignKey("catalog_entry.occurrence_id", ondelete="CASCADE"), primary_key=True
    )
    source_record_id: Mapped[UUID] = mapped_column()
    content_hash: Mapped[str] = mapped_column(String(64))
    normalization_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "content_hash", "normalization_hash"],
            [
                "normalized_source_revision.source_record_id",
                "normalized_source_revision.content_hash",
                "normalized_source_revision.normalization_hash",
            ],
        ),
    )


class LocalityBrowseSummary(Base):
    """Exact unconstrained locality aggregates; identity/geography remain live."""

    __tablename__ = "locality_browse_summary"
    locality_id: Mapped[UUID] = mapped_column(ForeignKey("locality.id"), primary_key=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)


class TaxonBrowseSummary(Base):
    """Global source-membership aggregates with exact distinct-specimen correction."""

    __tablename__ = "taxon_browse_summary"
    id: Mapped[UUID] = mapped_column(ForeignKey("taxon.id"), primary_key=True)
    assertion_count: Mapped[int] = mapped_column(BigInteger)
    specimen_count: Mapped[int] = mapped_column(BigInteger)
    source_taxon_count: Mapped[int] = mapped_column(BigInteger)
    older_ma: Mapped[Decimal | None] = mapped_column(Numeric())
    younger_ma: Mapped[Decimal | None] = mapped_column(Numeric())
    known_age_count: Mapped[int] = mapped_column(BigInteger)
    unknown_age_count: Mapped[int] = mapped_column(BigInteger)
