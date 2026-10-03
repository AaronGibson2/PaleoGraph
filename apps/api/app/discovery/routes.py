from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.discovery import queries
from app.discovery.schemas import (
    CatalogPage,
    ContextQuery,
    EntityDetail,
    EntityKind,
    GraphPage,
    PlacePage,
    PlaceQuery,
    SearchPage,
)

router = APIRouter(tags=["discovery"])
Database = Annotated[Session, Depends(get_session)]
Context = Annotated[ContextQuery, Query()]


@router.get("/catalog", response_model=CatalogPage)
def catalog(query: Context, session: Database) -> CatalogPage:
    return queries.catalog(session, query)


@router.get("/search", response_model=SearchPage)
def search(query: Context, session: Database) -> SearchPage:
    return queries.search(session, query)


@router.get("/map/places", response_model=PlacePage)
def places(query: Annotated[PlaceQuery, Query()], session: Database) -> PlacePage:
    return queries.places(session, query)


@router.get("/entities/{kind}/{identifier}", response_model=EntityDetail)
def entity(kind: EntityKind, identifier: UUID, query: Context, session: Database) -> EntityDetail:
    return queries.detail(session, kind, identifier, query)


@router.get("/graph/{kind}/{identifier}", response_model=GraphPage)
def graph(kind: EntityKind, identifier: UUID, query: Context, session: Database) -> GraphPage:
    return queries.graph(session, kind, identifier, query)
