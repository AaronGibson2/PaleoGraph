from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.explore.schemas import (
    Evidence,
    ExploreQuery,
    MapOccurrence,
    MapResponse,
    OccurrenceDetail,
    SpecimenDetail,
)
from app.models import (
    Collection,
    CollectionEvent,
    Locality,
    Occurrence,
    SourceDataset,
    SourceRecord,
    Specimen,
    Taxon,
)


def age_overlap(older_ma: float, younger_ma: float) -> ColumnElement[bool]:
    """Inclusive overlap of fully known intervals. SQL NULL never means present."""
    return and_(
        CollectionEvent.older_ma.is_not(None),
        CollectionEvent.younger_ma.is_not(None),
        CollectionEvent.younger_ma <= older_ma,
        CollectionEvent.older_ma >= younger_ma,
    )


def viewport_filter(query: ExploreQuery) -> ColumnElement[bool]:
    def intersects(west: float, east: float) -> ColumnElement[bool]:
        return func.ST_Intersects(
            Locality.geom, func.ST_MakeEnvelope(west, query.south, east, query.north, 4326)
        )

    if query.west > query.east:
        return or_(intersects(query.west, 180), intersects(-180, query.east))
    return intersects(query.west, query.east)


def map_occurrences(session: Session, query: ExploreQuery) -> MapResponse:
    synthetic = Occurrence.source_records.any(SourceRecord.dataset.has(SourceDataset.is_synthetic))
    statement = (
        select(
            Occurrence.id,
            Taxon.scientific_name,
            Locality.name.label("locality_name"),
            func.ST_X(Locality.geom).label("longitude"),
            func.ST_Y(Locality.geom).label("latitude"),
            CollectionEvent.older_ma,
            CollectionEvent.younger_ma,
            Locality.location_is_generalized,
            synthetic.label("is_synthetic"),
            func.concat_ws(" · ", Specimen.collection_code, Specimen.catalog_number).label(
                "catalog_label"
            ),
            CollectionEvent.early_interval_name.label("source_age_label"),
        )
        .join(Occurrence.taxon)
        .join(Occurrence.collection_event)
        .join(CollectionEvent.locality)
        .outerjoin(Occurrence.specimen)
        .where(
            viewport_filter(query),
            Locality.location_is_withheld.is_(False),
            Occurrence.source_records.any(SourceRecord.is_current),
            synthetic if query.data_mode == "demo" else ~synthetic,
        )
        .order_by(Occurrence.id)
        .limit(query.limit + 1)
    )
    if query.older_ma is not None and query.younger_ma is not None:
        statement = statement.where(age_overlap(query.older_ma, query.younger_ma))
    rows = session.execute(statement).mappings().all()
    items = [MapOccurrence.model_validate(row) for row in rows[: query.limit]]
    return MapResponse(
        items=items, returned=len(items), truncated=len(rows) > query.limit, limit=query.limit
    )


def occurrence_detail(session: Session, occurrence_id: UUID) -> OccurrenceDetail | None:
    row = session.execute(
        select(Occurrence, func.ST_X(Locality.geom), func.ST_Y(Locality.geom))
        .join(Occurrence.collection_event)
        .outerjoin(CollectionEvent.locality)
        .where(Occurrence.id == occurrence_id)
        .options(
            joinedload(Occurrence.taxon),
            joinedload(Occurrence.specimen)
            .joinedload(Specimen.collection)
            .joinedload(Collection.institution),
            joinedload(Occurrence.collection_event).joinedload(CollectionEvent.locality),
            selectinload(Occurrence.source_records)
            .joinedload(SourceRecord.dataset)
            .joinedload(SourceDataset.source),
            selectinload(Occurrence.source_records).joinedload(SourceRecord.run),
        )
    ).first()
    if row is None:
        return None
    occurrence, longitude, latitude = row
    event = occurrence.collection_event
    locality = event.locality
    withheld = locality.location_is_withheld if locality else False
    specimen = occurrence.specimen
    source_values = {}
    if specimen and occurrence.source_records:
        raw = occurrence.source_records[0].raw_payload or {}
        # Explicit safe public fields, never return a raw row or withheld original coordinates.
        source_values = {
            key: str(raw[key])
            for key in (
                "scientificName",
                "identificationQualifier",
                "basisOfRecord",
                "eventDate",
                "recordedBy",
                "locationID",
                "country",
                "stateProvince",
                "county",
                "locality",
                "geodeticDatum",
                "coordinateUncertaintyInMeters",
                "earliestEraOrLowestErathem",
                "earliestPeriodOrLowestSystem",
                "earliestEpochOrLowestSeries",
                "lowestBiostratigraphicZone",
                "group",
                "formation",
                "member",
                "modified",
            )
            if raw.get(key)
        }
    return OccurrenceDetail(
        id=occurrence.id,
        taxon_id=occurrence.taxon_id,
        scientific_name=occurrence.taxon.scientific_name,
        rank=occurrence.taxon.rank,
        collection_event_id=event.id,
        collection_event_name=event.name,
        context=event.context,
        stratigraphy=event.stratigraphy,
        older_ma=event.older_ma,
        younger_ma=event.younger_ma,
        early_interval_name=event.early_interval_name,
        late_interval_name=event.late_interval_name,
        locality_id=event.locality_id,
        locality_name=locality.name if locality else None,
        longitude=None if withheld else longitude,
        latitude=None if withheld else latitude,
        coordinate_uncertainty_m=locality.coordinate_uncertainty_m if locality else None,
        location_is_generalized=locality.location_is_generalized if locality else False,
        location_is_withheld=withheld,
        notes=occurrence.notes,
        specimen=SpecimenDetail(
            id=specimen.id,
            institution=specimen.collection.institution.name if specimen.collection else None,
            institution_code=specimen.institution_code,
            collection_code=specimen.collection_code,
            catalog_number=specimen.catalog_number,
            occurrence_identifier=specimen.occurrence_identifier,
            material_entity_identifier=specimen.material_entity_identifier,
            other_identifiers=specimen.other_identifiers,
            preparations=specimen.preparations,
            individual_count=specimen.individual_count,
        )
        if specimen
        else None,
        source_values=source_values,
        evidence=[
            Evidence(
                source_record_id=record.source_record_id,
                source_name=record.dataset.source.name,
                source_url=record.source_url,
                dataset_id=record.source_dataset_id,
                dataset_title=record.dataset.title,
                dataset_url=record.dataset.dataset_url,
                publisher=record.dataset.publisher,
                citation=record.dataset.citation,
                license=record.license or record.dataset.license,
                rights_holder=record.rights_holder or record.dataset.rights_holder,
                dataset_version=record.run.source_version or record.dataset.version,
                ingestion_run_id=record.ingestion_run_id,
                ingested_at=record.ingested_at,
                is_current=record.is_current,
                is_synthetic=record.dataset.is_synthetic,
                information_withheld=record.information_withheld,
                data_generalizations=record.data_generalizations,
            )
            for record in sorted(
                occurrence.source_records, key=lambda record: record.source_record_id
            )
        ],
    )
