from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.discovery import associations, queries
from app.discovery.schemas import (
    AssociationPage,
    AssociationQuery,
    CatalogPage,
    ContextQuery,
    EntityDetail,
    EntityKind,
    GraphPage,
    LineagePage,
    LineageQuery,
    LocalitySummary,
    PlacePage,
    PlaceQuery,
    SearchPage,
)

router = APIRouter(tags=["discovery"])
Database = Annotated[Session, Depends(get_session)]
Context = Annotated[ContextQuery, Query()]
AssociationContext = Annotated[AssociationQuery, Query()]


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


@router.get("/localities", response_model=AssociationPage)
def localities(query: AssociationContext, session: Database) -> AssociationPage:
    return associations.localities(session, query)


@router.get("/localities/{identifier}", response_model=LocalitySummary)
def locality(identifier: UUID, query: Context, session: Database) -> LocalitySummary:
    return associations.locality_summary(session, identifier, query)


@router.get("/localities/{identifier}/taxa", response_model=AssociationPage)
def fauna(identifier: UUID, query: AssociationContext, session: Database) -> AssociationPage:
    if query.locality_id and query.locality_id != identifier:
        from fastapi import HTTPException

        raise HTTPException(422, "Conflicting locality context")
    return associations.fauna(session, query.model_copy(update={"locality_id": identifier}))


@router.get("/localities/{identifier}/specimens", response_model=CatalogPage)
def specimens(identifier: UUID, query: Context, session: Database) -> CatalogPage:
    if query.locality_id and query.locality_id != identifier:
        from fastapi import HTTPException

        raise HTTPException(422, "Conflicting locality context")
    return queries.catalog(session, query.model_copy(update={"locality_id": identifier}))


@router.get("/taxa/{identifier}/localities", response_model=AssociationPage)
def taxon_localities(
    identifier: UUID, query: AssociationContext, session: Database
) -> AssociationPage:
    if query.taxon_id and query.taxon_id != identifier:
        from fastapi import HTTPException

        raise HTTPException(422, "Conflicting taxon context")
    return associations.localities(session, query.model_copy(update={"taxon_id": identifier}))


@router.get("/lineage", response_model=LineagePage)
def lineage(query: Annotated[LineageQuery, Query()], session: Database) -> LineagePage:
    return associations.lineage(session, query, query.focus)
