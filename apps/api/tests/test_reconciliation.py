"""Additional evidence at normalization, planning and persisted reconciliation seams."""

import pytest


def test_complete_explicit_material_key_keeps_suffix_and_original_text():
    from app.reconciliation import MaterialKey, normalize_identifier

    result = normalize_identifier(label="  uf : vp : 123A  ")
    assert result.key == MaterialKey("UF", "VP", "123A")
    assert result.original["label"] == "  uf : vp : 123A  "
    assert result.state == "complete"


def test_bare_uf_label_does_not_invent_vp_collection():
    from app.reconciliation import normalize_identifier

    result = normalize_identifier(label="UF 18928")
    assert result.key is None
    assert (result.institution, result.collection, result.catalog) == ("UF", None, "18928")
    assert result.state == "partial"


def test_identifier_lists_ranges_and_malformed_labels_never_become_material_keys():
    from app.reconciliation import normalize_identifier

    for catalog, state in [
        ("123-125", "ambiguous"),
        ("123,124", "ambiguous"),
        ("123/124", "ambiguous"),
        ("??", "malformed"),
    ]:
        result = normalize_identifier(institution="UF", collection="VP", catalog=catalog)
        assert result.key is None
        assert result.state == state
        assert result.original["catalog"] == catalog


def test_exact_triplet_matches_one_material_and_ignores_other_institution():
    from uuid import UUID

    from app.reconciliation import Target, match_identifier, normalize_identifier

    target = Target(UUID(int=1), UUID(int=2), "a" * 64, "UF", "VP", "123A")
    other = Target(UUID(int=3), UUID(int=4), "b" * 64, "AMNH", "VP", "123A")
    decision = match_identifier(normalize_identifier(label="UF VP 123A"), [target, other])
    assert decision.status == "deterministic"
    assert decision.targets == (target,)
    assert (
        match_identifier(normalize_identifier(label="MCZ VP 123A"), [target, other]).targets == ()
    )


def test_missing_collection_and_nonunique_complete_keys_remain_candidates_or_ambiguous():
    from uuid import UUID

    from app.reconciliation import Target, match_identifier, normalize_identifier

    vp = Target(UUID(int=1), UUID(int=2), "a" * 64, "UF", "VP", "123")
    fgs = Target(UUID(int=3), UUID(int=4), "b" * 64, "UF", "UF/FGS", "123")
    duplicate = Target(UUID(int=5), UUID(int=6), "c" * 64, "UF", "VP", "123")
    partial = normalize_identifier(label="UF 123")
    assert match_identifier(partial, [vp]).status == "candidate"
    assert match_identifier(partial, [vp, fgs]).status == "ambiguous"
    assert (
        match_identifier(normalize_identifier(label="UF VP 123"), [vp, duplicate]).status
        == "ambiguous"
    )
    assert match_identifier(normalize_identifier(label="UF 000123"), [vp]).targets == ()


def test_repository_abbreviations_are_not_guessed_into_institution_collection_keys():
    from app.reconciliation import normalize_identifier

    for label in ("F:AM 53357", "FLMNH 123", "UFVP 123", "Amer. Mus. 5663"):
        result = normalize_identifier(label=label)
        assert result.key is None
        assert result.original["label"] == label


def test_conflicting_explicit_label_and_structured_components_withhold_identity():
    from app.reconciliation import normalize_identifier

    result = normalize_identifier(
        label="UF VP 123", institution="UF", collection="UF/FGS", catalog="123"
    )
    assert result.key is None
    assert result.state == "ambiguous"
    assert result.reason == "conflicting-explicit-components"


def test_multiple_evidence_witnesses_of_one_specimen_do_not_make_identity_ambiguous():
    from uuid import UUID

    from app.reconciliation import Target, match_identifier, normalize_identifier

    witnesses = [
        Target(UUID(int=1), UUID(int=2), "a" * 64, "UF", "VP", "123"),
        Target(UUID(int=1), UUID(int=3), "b" * 64, "UF", "VP", "123"),
    ]
    decision = match_identifier(normalize_identifier(label="UF VP 123"), witnesses)
    assert decision.status == "deterministic"
    assert decision.targets == tuple(witnesses)


@pytest.mark.integration
def test_preview_keeps_exact_material_identity_despite_context_conflicts(db_session, tmp_path):
    from test_pbdb import modified_snapshot
    from test_ufvp import fixture_rows, make_archive

    from app.ingestion.import_pbdb import DATASET_UUID, ingest_snapshot
    from app.ingestion.import_ufvp import ingest
    from app.reconciliation import preview_reconciliation

    def edit(response):
        for row in response["records"]:
            row.pop("specimen_id", None)
        response["records"][0]["specimen_id"] = "UF VP 18928"

    snapshot = modified_snapshot(tmp_path, "materials", edit)
    ingest_snapshot(db_session, snapshot)
    rows = fixture_rows()
    rows[0].update(
        catalogNumber="18928",
        institutionCode="UF",
        collectionCode="VP",
        scientificName="Different identification",
    )
    result = ingest(db_session, make_archive(tmp_path, rows), raw_dir=tmp_path / "retained")
    preview = preview_reconciliation(db_session, DATASET_UUID, result.source_dataset_id)
    matched = [item for item in preview.items if item.decision.status == "deterministic"]
    assert len(matched) == 1
    assert matched[0].identifier.key.catalog == "18928"
    assert matched[0].diagnostics[0]["taxonomic_disagreement"] is True
    assert matched[0].diagnostics[0]["locality_disagreement"] is True
    assert matched[0].diagnostics[0]["temporal_disagreement"] is True
    assert matched[0].references
    assert preview.counts["deterministic_material_records"] == 1
    # Design C removes this duplicate source cache; authenticated normalized
    # evidence must retain exactly the same proposals and context diagnostics.
    from sqlalchemy import text

    db_session.execute(
        text("UPDATE source_record SET raw_payload=NULL WHERE source_dataset_id=:id"),
        {"id": DATASET_UUID},
    )
    cold = preview_reconciliation(db_session, DATASET_UUID, result.source_dataset_id)
    assert cold.input_digest == preview.input_digest
    assert cold.counts == preview.counts


@pytest.mark.integration
def test_reconciliation_publishes_provenance_and_replays_without_duplicates(db_session, tmp_path):
    from test_pbdb import modified_snapshot
    from test_ufvp import fixture_rows, make_archive

    from app.discovery.multi_source import source_counts
    from app.ingestion.import_pbdb import DATASET_UUID, ingest_snapshot
    from app.ingestion.import_ufvp import CANONICAL_DATASET_ID, ingest
    from app.reconciliation import preview_reconciliation, reconcile, reconciliation_records

    def edit(response):
        response["records"][0]["specimen_id"] = "UF 18928"

    ingest_snapshot(db_session, modified_snapshot(tmp_path, "materials", edit))
    rows = fixture_rows()
    rows[0].update(catalogNumber="18928", institutionCode="UF", collectionCode="VP")
    ingest(db_session, make_archive(tmp_path, rows), raw_dir=tmp_path / "retained")
    before = source_counts(db_session)
    plan = preview_reconciliation(db_session, DATASET_UUID, CANONICAL_DATASET_ID)
    first = reconcile(
        db_session, DATASET_UUID, CANONICAL_DATASET_ID, expected_input_digest=plan.input_digest
    )
    records = reconciliation_records(db_session, DATASET_UUID, CANONICAL_DATASET_ID)
    assert first["inserted_assessments"] == plan.counts["material_records"]
    assert any(item["edges"] for item in records)
    assert all(
        edge["relationship_type"] == "candidate_same_specimen"
        for item in records
        for edge in item["edges"]
    )
    assert all(item["content_hash"] and item["normalization_hash"] for item in records)
    assert (
        reconcile(
            db_session, DATASET_UUID, CANONICAL_DATASET_ID, expected_input_digest=plan.input_digest
        )["inserted_edges"]
        == 0
    )
    assert reconciliation_records(db_session, DATASET_UUID, CANONICAL_DATASET_ID) == records
    assert source_counts(db_session) == before


@pytest.mark.integration
def test_changed_source_invalidates_current_edges_and_stale_dry_run_cannot_publish(
    db_session, tmp_path
):
    from test_pbdb import modified_snapshot
    from test_ufvp import fixture_rows, make_archive

    from app.ingestion.import_pbdb import DATASET_UUID, ingest_snapshot
    from app.ingestion.import_ufvp import CANONICAL_DATASET_ID, ingest
    from app.reconciliation import (
        preview_reconciliation,
        rebuild_reconciliation,
        reconcile,
        reconciliation_records,
    )

    def edit(response):
        response["records"][0]["specimen_id"] = "UF VP 18928"

    ingest_snapshot(db_session, modified_snapshot(tmp_path, "materials", edit))
    rows = fixture_rows()
    rows[0].update(catalogNumber="18928", institutionCode="UF", collectionCode="VP")
    ingest(db_session, make_archive(tmp_path, rows), raw_dir=tmp_path / "retained")
    plan = preview_reconciliation(db_session, DATASET_UUID, CANONICAL_DATASET_ID)
    reconcile(
        db_session, DATASET_UUID, CANONICAL_DATASET_ID, expected_input_digest=plan.input_digest
    )
    initial = reconciliation_records(db_session, DATASET_UUID, CANONICAL_DATASET_ID)
    with pytest.raises(ValueError, match="Source state changed"):
        rebuild_reconciliation(
            db_session, DATASET_UUID, CANONICAL_DATASET_ID, expected_input_digest="0" * 64
        )
    assert reconciliation_records(db_session, DATASET_UUID, CANONICAL_DATASET_ID) == initial
    rows[0]["catalogNumber"] = "9999999"
    changed = ingest(db_session, make_archive(tmp_path, rows), raw_dir=tmp_path / "retained")
    assert changed.status == "completed", changed.error_summary
    from sqlalchemy import text

    db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert reconciliation_records(db_session, DATASET_UUID, CANONICAL_DATASET_ID) == []
    with pytest.raises(ValueError, match="Source state changed"):
        reconcile(
            db_session, DATASET_UUID, CANONICAL_DATASET_ID, expected_input_digest=plan.input_digest
        )
    assert (
        reconciliation_records(db_session, DATASET_UUID, CANONICAL_DATASET_ID, include_history=True)
        == initial
    )


@pytest.mark.integration
def test_multiple_occurrences_reference_one_material_and_review_survives_rebuild(
    db_session, tmp_path
):
    import json
    from pathlib import Path

    from test_pbdb import modified_snapshot
    from test_ufvp import fixture_rows, make_archive

    from app.discovery.multi_source import source_counts
    from app.ingestion.import_pbdb import DATASET_UUID, ingest_snapshot
    from app.ingestion.import_ufvp import CANONICAL_DATASET_ID, ingest
    from app.reconciliation import (
        preview_reconciliation,
        rebuild_reconciliation,
        reconcile,
        reconciliation_records,
        review_edge,
    )

    other = json.loads((Path(__file__).parent / "fixtures/pbdb/001-latest.json").read_bytes())[
        "records"
    ][0]

    def edit(response):
        for index, row in enumerate(response["records"]):
            row.pop("specimen_id", None)
            if index < 2:
                row["specimen_id"] = "UF VP 18928"
            if index == 1:
                row["occurrence_no"] = other["occurrence_no"]
                row["collection_no"] = other["collection_no"]
                row.pop("reid_no", None)

    ingest_snapshot(db_session, modified_snapshot(tmp_path, "materials", edit))
    rows = fixture_rows()
    rows[0].update(catalogNumber="18928", institutionCode="UF", collectionCode="VP")
    ingest(db_session, make_archive(tmp_path, rows), raw_dir=tmp_path / "retained")
    before = source_counts(db_session)
    plan = preview_reconciliation(db_session, DATASET_UUID, CANONICAL_DATASET_ID)
    assert plan.counts["deterministic_material_records"] == 2
    reconcile(
        db_session, DATASET_UUID, CANONICAL_DATASET_ID, expected_input_digest=plan.input_digest
    )
    records = reconciliation_records(db_session, DATASET_UUID, CANONICAL_DATASET_ID)
    linked = [item for item in records if item["status"] == "deterministic"]
    assert len({item["occurrence_id"] for item in linked}) == 2
    assert len({edge["target_specimen_id"] for item in linked for edge in item["edges"]}) == 1
    edge = linked[0]["edges"][0]
    assert edge["relationship_type"] == "material_identifier_matches"
    review_edge(
        db_session,
        edge["id"],
        decision="unresolved",
        reviewer="fixture reviewer",
        reason="retain original source labels",
    )
    rebuild_reconciliation(
        db_session, DATASET_UUID, CANONICAL_DATASET_ID, expected_input_digest=plan.input_digest
    )
    rebuilt = reconciliation_records(db_session, DATASET_UUID, CANONICAL_DATASET_ID)
    assert {e["id"] for item in rebuilt for e in item["edges"]} == {
        e["id"] for item in records for e in item["edges"]
    }
    reviewed = [e for item in rebuilt for e in item["edges"] if e["id"] == edge["id"]][0]
    assert reviewed["review_decision"] == "unresolved"
    assert reviewed["review_reason"] == "retain original source labels"
    assert source_counts(db_session) == before
