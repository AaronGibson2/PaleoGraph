from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.discovery.timescale import configuration
from app.errors import ErrorResponse
from app.explore.queries import map_occurrences, occurrence_detail
from app.explore.schemas import (
    DatasetStatus,
    ExploreQuery,
    MapResponse,
    OccurrenceDetail,
)
from app.ingestion.import_ufvp import CANONICAL_DATASET_ID
from app.ingestion.ufvp import RESOURCE_URL
from app.models import (
    CollectionEvent,
    IngestionRun,
    Locality,
    Occurrence,
    SourceDataset,
    SourceRecord,
)

router = APIRouter(
    tags=["explore"], responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}
)


@router.get("/datasets/ufvp", response_model=DatasetStatus)
def dataset_status(session: Annotated[Session, Depends(get_session)]) -> DatasetStatus:
    from app.discovery.browse import revision

    dataset = session.get(SourceDataset, CANONICAL_DATASET_ID)
    run = session.scalar(
        select(IngestionRun)
        .where(IngestionRun.source_dataset_id == CANONICAL_DATASET_ID)
        .order_by(IngestionRun.started_at.desc())
        .limit(1)
    )
    evidence = Occurrence.source_records.any(
        (SourceRecord.source_dataset_id == CANONICAL_DATASET_ID) & SourceRecord.is_current
    )
    counts = session.execute(
        select(
            func.count(Occurrence.id),
            func.count(Occurrence.id).filter(
                Locality.geom.is_not(None) & ~Locality.location_is_withheld
            ),
            func.count(Occurrence.id).filter(
                CollectionEvent.older_ma.is_not(None) & CollectionEvent.younger_ma.is_not(None)
            ),
        )
        .join(Occurrence.collection_event)
        .outerjoin(CollectionEvent.locality)
        .where(evidence)
    ).one()
    return DatasetStatus(
        title=dataset.title if dataset else "University of Florida Vertebrate Paleontology",
        dataset_url=RESOURCE_URL,
        license=dataset.license if dataset else None,
        version=dataset.version if dataset else None,
        current_records=counts[0],
        mapped_records=counts[1],
        numeric_age_records=counts[2],
        browse_revision=revision(session),
        latest_scope=run.scope if run else None,
        latest_status=run.status if run else None,
        creator=str(run.snapshot.get("creator"))
        if run and run.snapshot and run.snapshot.get("creator")
        else None,
    )


@router.get("/map/occurrences", response_model=MapResponse)
def get_occurrences(
    query: Annotated[ExploreQuery, Query()], session: Annotated[Session, Depends(get_session)]
) -> MapResponse:
    return map_occurrences(session, query)


@router.get(
    "/occurrences/{occurrence_id}",
    response_model=OccurrenceDetail,
    responses={404: {"model": ErrorResponse}},
)
def get_occurrence(
    occurrence_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> OccurrenceDetail:
    detail = occurrence_detail(session, occurrence_id)
    if detail is None:
        raise HTTPException(404, "Occurrence not found")
    return detail


@router.get("/time-intervals")
def time_intervals() -> dict[str, Any]:
    return configuration()
