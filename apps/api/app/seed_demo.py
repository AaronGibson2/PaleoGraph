"""Synthetic development fixtures only. No source downloads or scientific claims."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from geoalchemy2 import WKTElement
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base, create_db_engine
from app.models import (
    CollectionEvent,
    IngestionRun,
    Locality,
    Occurrence,
    Source,
    SourceDataset,
    SourceRecord,
    Taxon,
    event_evidence,
    locality_evidence,
    occurrence_evidence,
    taxon_evidence,
)

STAMP = datetime(2026, 1, 1, tzinfo=UTC)
TAXA = ["Mammuthus", "Equus", "Tapirus", "Alligator", "Carcharhinus", "Trichechus"]
# Invented positions and contexts, not fossil locality coordinates.
POINTS = [
    (-87.1, 30.7),
    (-86.1, 30.6),
    (-85.3, 30.5),
    (-84.5, 30.4),
    (-83.6, 30.2),
    (-82.7, 30.1),
    (-81.8, 30.0),
    (-82.5, 29.6),
    (-82.0, 29.3),
    (-81.4, 29.0),
    (-82.3, 28.6),
    (-81.8, 28.4),
    (-81.2, 28.1),
    (-82.0, 27.8),
    (-81.5, 27.5),
    (-80.8, 27.2),
    (-81.5, 26.8),
    (-80.6, 26.5),
    None,
    None,
]
AGES: list[tuple[str | None, str | None]] = [
    ("0.08", "0.01"),
    ("1.2", "0.2"),
    ("2.5", "1.8"),
    ("4.5", "3"),
    ("8", "6"),
    ("11.8", "10"),
    (None, None),
    ("2", None),
]


def demo_id(group: int, number: int) -> UUID:
    """Fixed RFC 4122 version-4 fixture IDs, not a production ID generator."""
    return UUID(f"de000000-0000-4000-8000-{group:04x}{number:08x}")


def add_row(session: Session, model: type[Base], **values: object) -> None:
    session.execute(insert(model).values(**values).on_conflict_do_nothing())


def reset_demo(session: Session) -> None:
    """Delete only reserved fixtures; foreign keys protect non-demo dependants."""
    records = [demo_id(7, i) for i in range(40)]
    for table in (occurrence_evidence, event_evidence, locality_evidence, taxon_evidence):
        session.execute(delete(table).where(table.c.source_record_id.in_(records)))
    for model, group, count in (
        (Occurrence, 6, 40),
        (CollectionEvent, 5, 40),
        (Locality, 4, 20),
        (Taxon, 3, 6),
        (SourceRecord, 7, 40),
        (IngestionRun, 8, 2),
        (SourceDataset, 2, 2),
        (Source, 1, 2),
    ):
        session.execute(
            delete(model).where(model.id.in_([demo_id(group, i) for i in range(count)]))
        )


def seed_demo(session: Session, *, reset: bool = False) -> None:
    # Serialize concurrent seed/reset commands; the caller owns the transaction.
    session.execute(text("SELECT pg_advisory_xact_lock(72460102)"))
    existing = session.scalars(
        select(SourceDataset).where(SourceDataset.id.in_([demo_id(2, 0), demo_id(2, 1)]))
    )
    if any(not dataset.is_synthetic for dataset in existing):
        raise ValueError(
            "Reserved fixture IDs belong to a non-synthetic dataset; refusing to modify it"
        )
    if reset:
        reset_demo(session)
    for i, title in enumerate(("Synthetic field notebook", "Synthetic teaching collection")):
        add_row(session, Source, id=demo_id(1, i), name=f"PaleoGraph demo — {title}")
        add_row(
            session,
            SourceDataset,
            id=demo_id(2, i),
            source_id=demo_id(1, i),
            external_dataset_id=f"demo-florida-{i}",
            title=title,
            publisher="PaleoGraph development fixtures",
            version="demo-v1",
            citation="Synthetic Florida exploration scenarios (demo-v1). "
            "Not scientific observations.",
            retrieved_at=STAMP,
            is_synthetic=True,
        )
        add_row(
            session,
            IngestionRun,
            id=demo_id(8, i),
            source_dataset_id=demo_id(2, i),
            started_at=STAMP,
            completed_at=STAMP,
            status="completed",
            records_read=20,
            records_inserted=20,
            source_version="demo-v1",
        )
    for i, name in enumerate(TAXA):
        add_row(session, Taxon, id=demo_id(3, i), scientific_name=name, rank="genus")
    for i, point in enumerate(POINTS):
        add_row(
            session,
            Locality,
            id=demo_id(4, i),
            name=f"Demo locality {i + 1:02d}",
            description="Invented geographic context for interface development.",
            geom=WKTElement(f"POINT({point[0]} {point[1]})", srid=4326) if point else None,
            original_longitude=str(point[0]) if point else None,
            original_latitude=str(point[1]) if point else None,
            geodetic_datum="WGS84" if point else None,
            coordinate_uncertainty_m=5000 if i % 5 == 0 else None,
            location_is_generalized=i % 5 == 0,
            location_is_withheld=i == 19,
            information_withheld="Synthetic withheld-location example" if i == 19 else None,
        )
    for i in range(40):
        older, younger = AGES[i % len(AGES)]
        site, taxon, dataset = i // 2, i % len(TAXA), i % 2
        add_row(
            session,
            CollectionEvent,
            id=demo_id(5, i),
            locality_id=demo_id(4, site),
            name=f"Demo collecting context {i + 1:02d}",
            context="Synthetic occurrence assertion; no physical specimen "
            "or real collecting event.",
            stratigraphy=f"Invented teaching layer {i % 3 + 1}" if i % 4 else None,
            older_ma=Decimal(older) if older else None,
            younger_ma=Decimal(younger) if younger else None,
            early_interval_name="Unassigned demo interval",
            late_interval_name=None,
        )
        add_row(
            session,
            Occurrence,
            id=demo_id(6, i),
            taxon_id=demo_id(3, taxon),
            collection_event_id=demo_id(5, i),
            notes="Synthetic demo data. Taxon, age, and place associations are invented, "
            "not fossil evidence.",
        )
        payload = {
            "synthetic": True,
            "record": i,
            "name": TAXA[taxon],
            "older_ma": older,
            "younger_ma": younger,
        }
        add_row(
            session,
            SourceRecord,
            id=demo_id(7, i),
            source_dataset_id=demo_id(2, dataset),
            ingestion_run_id=demo_id(8, dataset),
            source_record_id=f"DEMO-{i + 1:03d}",
            record_type="occurrence_assertion",
            basis_of_record="Synthetic development scenario",
            raw_payload=payload,
            content_hash=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            first_seen_at=STAMP,
            last_seen_at=STAMP,
            ingested_at=STAMP,
            information_withheld="Synthetic withheld-location example" if site == 19 else None,
            data_generalizations="Synthetic generalized point" if site % 5 == 0 else None,
        )
        for table, key, entity_id in (
            (taxon_evidence, "taxon_id", demo_id(3, taxon)),
            (locality_evidence, "locality_id", demo_id(4, site)),
            (event_evidence, "collection_event_id", demo_id(5, i)),
            (occurrence_evidence, "occurrence_id", demo_id(6, i)),
        ):
            session.execute(
                insert(table)
                .values({key: entity_id, "source_record_id": demo_id(7, i)})
                .on_conflict_do_nothing()
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="Replace only reserved synthetic fixtures"
    )
    args = parser.parse_args()
    engine = create_db_engine(Settings())
    try:
        with Session(engine) as session, session.begin():
            seed_demo(session, reset=args.reset)
        print(
            "Synthetic demo ready: 40 occurrences, 20 localities, 40 collection contexts, 6 taxa."
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
