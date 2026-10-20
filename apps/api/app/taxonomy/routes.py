from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.taxonomy import queries
from app.taxonomy.schemas import (
    BranchChildrenPage,
    ConceptPage,
    TaxonomyDetail,
    TaxonomyPage,
    TaxonomyQuery,
)

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])
Database = Annotated[Session, Depends(get_session)]
Context = Annotated[TaxonomyQuery, Query()]


@router.get("/roots", response_model=TaxonomyPage)
def roots(query: Context, session: Database) -> TaxonomyPage:
    return queries.listing(session, query)


@router.get("/search", response_model=TaxonomyPage)
def search(query: Context, session: Database) -> TaxonomyPage:
    return queries.listing(session, query, search=True)


@router.get("/nodes/{identifier}", response_model=TaxonomyDetail)
def node(identifier: UUID, query: Context, session: Database) -> TaxonomyDetail:
    return queries.detail(session, identifier, query)


@router.get("/nodes/{identifier}/children", response_model=TaxonomyPage)
def children(identifier: UUID, query: Context, session: Database) -> TaxonomyPage:
    return queries.listing(session, query, parent=identifier)


@router.get("/nodes/{identifier}/ancestors", response_model=TaxonomyPage)
def ancestors(identifier: UUID, query: Context, session: Database) -> TaxonomyPage:
    return queries.ancestor_page(session, identifier, query)


@router.get("/nodes/{identifier}/concepts", response_model=ConceptPage)
def concepts(identifier: UUID, query: Context, session: Database) -> ConceptPage:
    return queries.concept_page(session, identifier, query)


@router.get("/nodes/{identifier}/branch-children", response_model=BranchChildrenPage)
def branch(identifier: UUID, query: Context, session: Database) -> BranchChildrenPage:
    return queries.branch_children(session, identifier, query)
