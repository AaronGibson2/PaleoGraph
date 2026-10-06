"""TIME-1: source evidence, pinned interpretation, and inclusive age overlap."""

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_ufvp import fixture_rows, make_archive

from app.discovery import associations, browse
from app.discovery.index import rebuild
from app.discovery.queries import catalog, detail, places, search
from app.discovery.schemas import ContextQuery, PlaceQuery
from app.discovery.timescale import POLICY_VERSION, interpret
from app.explore.queries import map_occurrences, occurrence_detail
from app.explore.schemas import ExploreQuery
from app.ingestion.import_ufvp import ingest
from app.ingestion.ufvp import normalize, stable_id
from app.models import CollectionEvent, Occurrence, SourceRecord


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"earliestAgeOrLowestStage": "Tortonian"}, (11.63, 7.246)),
        ({"earliestEpochOrLowestSeries": "  mIoCeNe,   LATE  "}, (11.63, 5.333)),
        ({"earliestEpochOrLowestSeries": "Early Miocene"}, (23.04, 15.98)),
        ({"earliestEpochOrLowestSeries": "Middle Pleistocene"}, (0.774, 0.129)),
        ({"earliestEpochOrLowestSeries": "Eocene"}, (56, 33.9)),
        ({"earliestAgeOrLowestStage": "Meghalayan"}, (0.0042, 0)),
    ],
)
def test_pinned_interpretation_does_not_mutate_source(raw, expected):
    saved = dict(raw)
    result = interpret(raw)
    assert raw == saved
    assert (result["older_ma"], result["younger_ma"]) == expected
    assert result["policy_version"] == POLICY_VERSION
    assert result["rule"] == "exact-validated-label"


@pytest.mark.parametrize(
    "label,status",
    [
        ("", "absent"),
        ("Middle Pliocene", "unmapped"),
        ("Blancan", "unmapped"),
        ("unrecognized", "unmapped"),
        ("Tortonian or Messinian", "ambiguous"),
        ("Tortonian(?)", "ambiguous"),
    ],
)
def test_finest_assertion_controls_without_false_fallback(label, status):
    raw = {"earliestAgeOrLowestStage": label}
    if label:
        raw.update(earliestEpochOrLowestSeries="Miocene", earliestPeriodOrLowestSystem="Neogene")
    result = interpret(raw)
    assert result["status"] == status
    assert result["older_ma"] is result["younger_ma"] is result["interval_id"] is None


@pytest.mark.parametrize(
    "query",
    [
        {"older_ma": 2},
        {"younger_ma": 0},
        {"older_ma": 1, "younger_ma": 2},
        {"older_ma": float("nan"), "younger_ma": 0},
        {"older_ma": float("inf"), "younger_ma": 0},
    ],
)
def test_open_or_invalid_filter_bounds_are_rejected(query):
    with pytest.raises(ValidationError):
        ContextQuery(**query)
    with pytest.raises(ValidationError):
        ExploreQuery(west=-180, east=180, south=-90, north=90, **query)


def test_stage_wording_survives_source_normalization():
    raw = {
        **fixture_rows()[0],
        "earliestAgeOrLowestStage": "  Tortonian  ",
        "latestAgeOrHighestStage": "Messinian",
    }
    assert normalize(raw).geology["earliestAgeOrLowestStage"] == "  Tortonian  "
    assert normalize(raw).geology["latestAgeOrHighestStage"] == "Messinian"


def test_summary_generation_is_bound_to_scientific_policy():
    assert POLICY_VERSION in browse.VERSION


@pytest.mark.integration
def test_source_wording_api_and_retained_revision(db_session: Session, tmp_path: Path):
    rows = fixture_rows()
    rows[0]["earliestEpochOrLowestSeries"] = "  Miocene,   late  "
    run = ingest(db_session, make_archive(tmp_path, rows), raw_dir=tmp_path / "retained")
    assert run.status == "completed"
    identifier = stable_id("occurrence", rows[0]["id"])
    response = occurrence_detail(db_session, identifier)
    assert response.source_values["earliestEpochOrLowestSeries"] == "  Miocene,   late  "
    assert response.older_ma is response.younger_ma is None
    interpretation = detail(
        db_session, "specimen", stable_id("specimen", rows[0]["id"]), ContextQuery()
    ).properties
    assert interpretation["status"] == "mapped"
    assert interpretation["source_label"] == "Miocene,   late"
    assert interpretation["older_ma"] == Decimal("11.63")
    assert interpretation["policy_version"] == POLICY_VERSION
    assert interpretation["interval"]["name"] == "Late Miocene"
    assert (
        db_session.scalar(
            text("""SELECT count(*) FROM source_record sr
        JOIN source_record_revision rev ON rev.source_record_id=sr.id
            AND rev.content_hash=sr.content_hash
        WHERE sr.raw_payload IS DISTINCT FROM rev.raw_payload""")
        )
        == 0
    )
    # Raw evidence includes stage fields even before a source adapter maps them.
    record = db_session.scalar(
        select(SourceRecord).where(SourceRecord.source_record_id == rows[0]["id"])
    )
    record.raw_payload = {**record.raw_payload, "earliestAgeOrLowestStage": "  Tortonian  "}
    db_session.flush()
    assert (
        occurrence_detail(db_session, identifier).source_values["earliestAgeOrLowestStage"]
        == "  Tortonian  "
    )


@pytest.mark.integration
def test_old_policy_catalog_is_not_served_as_active_interpretation(
    db_session: Session, tmp_path: Path
):
    ingest(db_session, make_archive(tmp_path, fixture_rows()), raw_dir=tmp_path / "retained")
    db_session.execute(
        text("""INSERT INTO age_interpretation
        SELECT source_record_id,content_hash,'test-obsolete-policy',interval_id,source_field,
        source_label,status,rule,older_ma,younger_ma,interpreted_at FROM age_interpretation""")
    )
    db_session.execute(
        text(
            "UPDATE catalog_entry SET policy_version='test-obsolete-policy', "
            "interpretation_policy_version='test-obsolete-policy'"
        )
    )
    assert catalog(db_session, ContextQuery()).total == 0
    old_token = browse.revision(db_session)
    rebuild(db_session)
    assert catalog(db_session, ContextQuery()).total == 8
    assert browse.revision(db_session) != old_token


@pytest.mark.integration
@pytest.mark.parametrize(
    "older,younger,expected_indices", [(5, 2, {0, 1, 7}), (0, 0, {1, 2}), (6, 5, {0, 6})]
)
def test_numeric_overlap_agrees_across_every_surface(
    db_session: Session, tmp_path: Path, older, younger, expected_indices
):
    rows = [
        {
            **fixture_rows()[0],
            "id": f"TIME-1-{i}",
            "catalogNumber": f"TIME-1-{i}",
            "earliestEpochOrLowestSeries": "unrecognized",
            "lowestBiostratigraphicZone": "Blancan",
        }
        for i in range(8)
    ]
    rows[7]["earliestEpochOrLowestSeries"] = "Miocene, late"
    run = ingest(db_session, make_archive(tmp_path, rows), raw_dir=tmp_path / "retained")
    assert run.status == "completed"
    bounds = [(10, 5), (2, 0), (0, 0), (None, None), (10, None), (None, 0), (7, 6), (3, 1)]
    for i, (source_older, source_younger) in enumerate(bounds):
        occurrence = db_session.get(Occurrence, stable_id("occurrence", rows[i]["id"]))
        event = db_session.get(CollectionEvent, occurrence.collection_event_id)
        event.older_ma, event.younger_ma = source_older, source_younger
    db_session.flush()
    rebuild(db_session)
    all_material = catalog(db_session, ContextQuery())
    site = all_material.items[0].locality_id
    assert all_material.total == 8
    summary = associations.locality_summary(db_session, site, ContextQuery())
    assert (summary.known_age_count, summary.unknown_age_count) == (5, 3)
    assert (summary.older_ma, summary.younger_ma) == (10, 0)
    # Source numeric envelope wins for discovery; label interpretation stays separate.
    last = detail(db_session, "specimen", stable_id("specimen", rows[7]["id"]), ContextQuery())
    assert last.properties["older_ma"] == Decimal("11.63")
    assert (
        next(
            item for item in all_material.items if item.id == stable_id("occurrence", rows[7]["id"])
        ).older_ma
        == 3
    )
    query = ContextQuery(older_ma=older, younger_ma=younger)
    expected = {stable_id("occurrence", rows[i]["id"]) for i in expected_indices}
    assert {item.id for item in catalog(db_session, query).items} == expected
    assert places(db_session, PlaceQuery(older_ma=older, younger_ma=younger)).total_records == len(
        expected
    )
    assert associations.locality_summary(db_session, site, query).assertion_count == len(expected)
    assert sum(
        item.assertion_count for item in associations.localities(db_session, query).items
    ) == len(expected)
    assert sum(item.assertion_count for item in associations.fauna(db_session, query).items) == len(
        expected
    )
    assert sum(
        item.assertion_count for item in associations.lineage(db_session, query).items
    ) == len(expected)
    assert {
        item.id
        for item in search(db_session, query.model_copy(update={"q": "TIME-1"})).items
        if item.kind == "specimen"
    } == {stable_id("specimen", rows[i]["id"]) for i in expected_indices}
    legacy = map_occurrences(
        db_session,
        ExploreQuery(west=-180, east=180, south=-90, north=90, older_ma=older, younger_ma=younger),
    )
    assert {item.id for item in legacy.items} == expected
