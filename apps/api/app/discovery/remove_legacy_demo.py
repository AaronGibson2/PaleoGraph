"""One-time guarded deletion of the exact retired Phase 2 fixture manifest. No seeding."""

import argparse
import json
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import create_db_engine
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


def reserved(group: int, number: int) -> UUID:
    return UUID(f"de000000-0000-4000-8000-{group:04x}{number:08x}")


def remove(session: Session, *, apply: bool = False) -> dict[str, object]:
    session.execute(text("SELECT pg_advisory_xact_lock(72460102)"))
    dataset_ids = [reserved(2, number) for number in range(2)]
    datasets = session.scalars(select(SourceDataset).where(SourceDataset.id.in_(dataset_ids))).all()
    if any(not dataset.is_synthetic for dataset in datasets):
        raise ValueError("Reserved dataset identity is no longer synthetic; refusing cleanup")
    records = [reserved(7, number) for number in range(40)]
    current = session.scalars(select(SourceRecord).where(SourceRecord.id.in_(records))).all()
    if any(record.source_dataset_id not in dataset_ids for record in current):
        raise ValueError("Reserved record has unexpected dataset; refusing cleanup")
    result: dict[str, object] = {
        "reserved_datasets": len(datasets),
        "reserved_records": len(current),
        "applied": apply,
    }
    if not apply:
        return result
    for table in (occurrence_evidence, event_evidence, locality_evidence, taxon_evidence):
        session.execute(delete(table).where(table.c.source_record_id.in_(records)))
    # Foreign keys deliberately abort the entire transaction if unrelated material depends
    # on this manifest. No cascade, name matching or geographic matching is permitted.
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
            delete(model).where(model.id.in_([reserved(group, i) for i in range(count)]))
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete the reviewed exact manifest")
    args = parser.parse_args()
    engine = create_db_engine(Settings())
    try:
        with Session(engine) as session, session.begin():
            print(json.dumps(remove(session, apply=args.apply)))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
