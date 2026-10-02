from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import ErrorResponse
from app.explore.queries import map_occurrences, occurrence_detail
from app.explore.schemas import (
    ExploreQuery,
    MapResponse,
    OccurrenceDetail,
    TimeConfiguration,
    TimeWindow,
)

router = APIRouter(
    tags=["explore"], responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}
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


@router.get("/time-intervals", response_model=TimeConfiguration)
def time_intervals() -> TimeConfiguration:
    # Numeric demonstration windows, not a claim about formal interval boundaries.
    return TimeConfiguration(
        version="demo-windows-v1",
        max_ma=12,
        windows=[
            TimeWindow(label="12–5 Ma", older_ma=12, younger_ma=5),
            TimeWindow(label="5–2 Ma", older_ma=5, younger_ma=2),
            TimeWindow(label="2–0.1 Ma", older_ma=2, younger_ma=0.1),
            TimeWindow(label="0.1–0 Ma", older_ma=0.1, younger_ma=0),
        ],
    )
