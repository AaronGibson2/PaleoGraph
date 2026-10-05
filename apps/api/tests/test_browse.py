"""Disposable summaries: exact semantics, lifecycle and bounded actual read paths."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from test_ufvp import fixture_rows, make_archive

from app.discovery import associations, browse
from app.discovery.queries import catalog
from app.discovery.schemas import ContextQuery
from app.ingestion.import_ufvp import ingest
from app.models import Collection, Institution

pytestmark = pytest.mark.integration


@pytest.fixture
def projected(db_session: Session, tmp_path: Path) -> Session:
    run = ingest(db_session, make_archive(tmp_path, fixture_rows()), raw_dir=tmp_path / "retained")
    assert run.status == "completed"
    browse.rebuild(db_session)
    assert browse.ready(db_session)
    return db_session


def statements_for(session: Session, operation):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    bind = session.get_bind()
    event.listen(bind, "before_cursor_execute", capture)
    try:
        result = operation()
    finally:
        event.remove(bind, "before_cursor_execute", capture)
    return result, statements


def test_projected_summary_read_paths_do_not_reaggregate_material(projected: Session) -> None:
    site = catalog(projected, ContextQuery()).items[0].locality_id
    _, sql = statements_for(
        projected,
        lambda: associations.locality_summary(projected, site, ContextQuery(locality_id=site)),
    )
    assert len(sql) <= 3  # identity and bounded generation/payload lookup
    assert sum("catalog_entry" in statement for statement in sql) == 1  # identity evidence only
    assert any("locality_browse_summary" in statement for statement in sql)
    _, sql = statements_for(projected, lambda: associations.lineage(projected, ContextQuery()))
    assert not any("catalog_entry" in statement for statement in sql)
    assert any("taxon_browse_summary" in statement for statement in sql)
    assert len(sql) <= 4  # generation, branch page, optional breadcrumbs, classification batch


def test_all_fixture_summaries_match_live_derivation(
    projected: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sites = projected.scalars(text("SELECT locality_id FROM locality_browse_summary")).all()
    nodes = projected.scalars(text("SELECT id FROM taxon_browse_summary")).all()
    for site in sites:
        actual = associations.locality_summary(projected, site, ContextQuery())
        with monkeypatch.context() as patch:
            patch.setattr(browse, "ready", lambda session: False)
            patch.setattr(browse, "locality_payload", lambda *args: None)
            expected = associations.locality_summary(projected, site, ContextQuery())
        assert actual.model_dump(mode="json") == expected.model_dump(mode="json")
    for node in [None, *nodes]:
        query = ContextQuery(limit=2)
        while True:
            actual = associations.lineage(projected, query, node)
            with monkeypatch.context() as patch:
                patch.setattr(browse, "ready", lambda session: False)
                expected = associations.lineage(projected, query, node)
            assert actual.model_dump(mode="json") == expected.model_dump(mode="json")
            if not actual.next_cursor:
                break
            query = query.model_copy(update={"cursor": actual.next_cursor})


def test_rebuild_is_idempotent_and_explicitly_versioned(projected: Session) -> None:
    before = browse.revision(projected)
    state = projected.execute(text("SELECT * FROM browse_projection_state")).mappings().one()
    snapshots = projected.execute(
        text("SELECT * FROM locality_browse_summary ORDER BY locality_id")
    ).all()
    result = browse.rebuild(projected)
    assert result["projection_version"] == browse.VERSION == state["projection_version"]
    assert result["input_revision"] == state["input_revision"]
    assert browse.revision(projected) == before
    assert (
        projected.execute(text("SELECT * FROM locality_browse_summary ORDER BY locality_id")).all()
        == snapshots
    )


def test_source_changes_invalidate_without_losing_canonical_guards(projected: Session) -> None:
    item = catalog(projected, ContextQuery()).items[0]
    before = browse.revision(projected)
    projected.execute(
        text("""UPDATE source_record SET is_current=false WHERE id=
        (SELECT source_record_id FROM catalog_entry WHERE occurrence_id=:id)"""),
        {"id": item.id},
    )
    assert not browse.ready(projected)
    assert browse.revision(projected) != before
    root = associations.lineage(projected, ContextQuery()).items[0]
    assert root.assertion_count == 7
    browse.rebuild(projected)
    assert browse.ready(projected)
    assert associations.lineage(projected, ContextQuery()).items[0].assertion_count == 7


def test_exact_specimens_across_identifications_and_null_ages(projected: Session) -> None:
    items = catalog(projected, ContextQuery()).items
    other = next(item for item in items if item.taxon_id != items[0].taxon_id)
    projected.execute(
        text("UPDATE catalog_entry SET specimen_id=:specimen WHERE occurrence_id=:id"),
        {"specimen": items[0].specimen_id, "id": other.id},
    )
    projected.execute(
        text("""UPDATE catalog_entry SET older_ma=NULL,younger_ma=NULL,
        age_basis='unresolved' WHERE occurrence_id=:id"""),
        {"id": other.id},
    )
    assert not browse.ready(projected)
    browse.rebuild(projected)
    root = associations.lineage(projected, ContextQuery()).items[0]
    assert root.assertion_count == 8 and root.specimen_count == 7
    assert root.known_age_count + root.unknown_age_count == 8
    assert root.unknown_age_count > 0


def test_generation_is_rechecked_in_the_actual_read_snapshot(
    projected: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = catalog(projected, ContextQuery()).items[0]
    original = browse.ready

    def changed_after_check(session):
        was_ready = original(session)
        session.execute(
            text("""UPDATE source_record SET is_current=false WHERE id=
            (SELECT source_record_id FROM catalog_entry WHERE occurrence_id=:id)"""),
            {"id": item.id},
        )
        return was_ready

    monkeypatch.setattr(browse, "ready", changed_after_check)
    assert associations.lineage(projected, ContextQuery()).items[0].assertion_count == 7


def test_generalized_withheld_and_multiple_custody_keep_live_semantics(
    projected: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = catalog(projected, ContextQuery()).items
    site = items[0].locality_id
    institution = Institution(id=uuid4(), name="Second fixture institution", code="TEST-SECOND")
    collection = Collection(
        id=uuid4(),
        institution_id=institution.id,
        name="Second fixture collection",
        code="TEST-SECOND",
    )
    projected.add(institution)
    projected.flush()
    projected.add(collection)
    projected.flush()
    projected.execute(
        text("UPDATE catalog_entry SET locality_id=:site WHERE occurrence_id=ANY(:ids)"),
        {"site": site, "ids": [item.id for item in items[:3]]},
    )
    projected.execute(
        text("""UPDATE catalog_entry SET collection_id=:collection,
        institution_id=:institution WHERE occurrence_id=:id"""),
        {"id": items[0].id, "collection": collection.id, "institution": institution.id},
    )
    for withheld in (False, True):
        projected.execute(
            text("""UPDATE locality SET location_is_generalized=true,
            location_is_withheld=:withheld,
            geom=CASE WHEN :withheld THEN NULL ELSE geom END WHERE id=:site"""),
            {"site": site, "withheld": withheld},
        )
        browse.rebuild(projected)
        actual = associations.locality_summary(projected, site, ContextQuery())
        with monkeypatch.context() as patch:
            patch.setattr(browse, "locality_payload", lambda *args: None)
            expected = associations.locality_summary(projected, site, ContextQuery())
        assert actual.model_dump(mode="json") == expected.model_dump(mode="json")
        assert actual.properties["location_is_generalized"]
        assert actual.collection_count == actual.institution_count == 2
        if withheld:
            assert actual.properties["longitude"] is None
            assert "county" not in actual.properties["geography"]


@pytest.mark.parametrize(
    "query",
    [
        ContextQuery(older_ma=0.01, younger_ma=0),
        ContextQuery(q="Dasypus"),
        ContextQuery(at_lon=-82.19, at_lat=29.36),
        ContextQuery(west=-83, east=-81, south=28, north=30),
    ],
)
def test_filtered_context_never_uses_global_payload(
    projected: Session, query: ContextQuery
) -> None:
    site = catalog(projected, ContextQuery()).items[0].locality_id
    _, sql = statements_for(
        projected, lambda: associations.locality_summary(projected, site, query)
    )
    assert not any("locality_browse_summary" in statement for statement in sql)
    _, sql = statements_for(projected, lambda: associations.lineage(projected, query))
    assert not any("taxon_browse_summary" in statement for statement in sql)
    assert any("catalog_entry" in statement for statement in sql)


def test_locality_and_selected_taxon_constrain_lineage(projected: Session) -> None:
    item = catalog(projected, ContextQuery()).items[0]
    for query in (ContextQuery(locality_id=item.locality_id), ContextQuery(taxon_id=item.taxon_id)):
        page, sql = statements_for(
            projected, lambda query=query: associations.lineage(projected, query)
        )
        assert not any("taxon_browse_summary" in statement for statement in sql)
        assert page.items[0].assertion_count < 8


def test_unbuilt_or_incompatible_projection_falls_back(projected: Session) -> None:
    projected.execute(text("UPDATE browse_projection_state SET projection_version='future'"))
    assert not browse.ready(projected)
    assert associations.lineage(projected, ContextQuery()).items[0].assertion_count == 8
    projected.execute(text("UPDATE browse_projection_state SET built_revision=NULL"))
    assert not browse.ready(projected)
    browse.rebuild(projected)
    assert browse.ready(projected)


def test_failed_rebuild_rolls_back_entire_replacement(projected: Session) -> None:
    before = browse.revision(projected)
    old = projected.execute(
        text("SELECT * FROM locality_browse_summary ORDER BY locality_id")
    ).all()

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("INSERT INTO taxon_browse_summary"):
            raise RuntimeError("Intentional browse build failure")

    bind = projected.get_bind()
    event.listen(bind, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="Intentional browse build failure"):
            browse.rebuild(projected)
    finally:
        event.remove(bind, "before_cursor_execute", fail)
    assert browse.revision(projected) == before
    assert (
        projected.execute(text("SELECT * FROM locality_browse_summary ORDER BY locality_id")).all()
        == old
    )
    assert catalog(projected, ContextQuery()).total == 8


def test_ingestion_refresh_and_failed_build_readiness(
    projected: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = browse.revision(projected)
    rows = fixture_rows()
    changed = {**rows[0], "earliestEpochOrLowestSeries": "Miocene, late"}
    run = ingest(projected, make_archive(tmp_path, [changed]), raw_dir=tmp_path / "again")
    assert run.status == "completed" and browse.ready(projected)
    assert browse.revision(projected) != before
    old = projected.execute(
        text("SELECT * FROM locality_browse_summary ORDER BY locality_id")
    ).all()

    def fail(session):
        session.execute(text("DELETE FROM locality_browse_summary"))
        raise RuntimeError("Intentional browse refresh failure")

    monkeypatch.setattr(browse, "rebuild", fail)
    run = ingest(projected, make_archive(tmp_path, rows), raw_dir=tmp_path / "failed")
    assert run.status == "failed" and "browse refresh failure" in run.error_summary
    assert not browse.ready(projected)
    assert (
        projected.execute(text("SELECT * FROM locality_browse_summary ORDER BY locality_id")).all()
        == old
    )
    assert projected.scalar(text("SELECT count(*) FROM source_record WHERE is_current")) == 8
    # The changed source survives the failed refresh, but its old catalog hash is
    # excluded. This is safer than claiming the retained projection is current.
    assert catalog(projected, ContextQuery()).total == 7
