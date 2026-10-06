"""PBDB source-boundary behavior, offline unless explicitly integration-marked."""

import hashlib
import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from app.ingestion.pbdb import (
    decode_response,
    identifier,
    normalize_collection,
    normalize_occurrences,
)

FIXTURE = Path(__file__).parent / "fixtures/pbdb"


@pytest.mark.integration
def test_successful_ingestion_and_replay_keep_browse_generation_ready(db_session):
    from app.discovery.browse import VERSION, revision
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.pbdb import Snapshot

    snapshot = Snapshot.load(FIXTURE)
    for _ in range(2):
        assert ingest_snapshot(db_session, snapshot)["status"] == "completed"
        assert revision(db_session).endswith(f":{VERSION}")


def test_normal_import_requires_full_scope_and_restore_verified_checkpoint(tmp_path):
    from app.ingestion.import_pbdb import validate_normal_checkpoint

    dump = tmp_path / "verified.dump"
    dump.write_bytes(b"isolated test checkpoint bytes")
    evidence = {
        "status": "verified",
        "label": "pre-4c",
        "path": str(dump),
        "sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
        "baseline": {
            "database_name": "paleograph",
            "migration": "0009_time_policy_cover",
            "occurrences": 462280,
            "specimens": 462280,
            "current_records": 462280,
            "revisions": 462280,
            "catalog": 462280,
        },
        "restore": {
            "migration": "0009_time_policy_cover",
            "occurrences": 462280,
            "specimens": 462280,
            "current_records": 462280,
            "revisions": 462280,
            "catalog": 462280,
        },
    }
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(json.dumps(evidence))
    validate_normal_checkpoint(
        "paleograph", "127.0.0.1", 5432, "paleograph", checkpoint, full_scope=True
    )
    for name, host, port, full in [
        ("paleograph", "remote.example", 5432, True),
        ("paleograph", "localhost", 5432, False),
        ("other", "localhost", 5432, True),
        ("paleograph", "localhost", 55432, True),
    ]:
        with pytest.raises(ValueError, match="checkpoint|full Florida|normal target"):
            validate_normal_checkpoint(name, host, port, "paleograph", checkpoint, full_scope=full)
    dump.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checkpoint"):
        validate_normal_checkpoint(
            "paleograph", "localhost", 5432, "paleograph", checkpoint, full_scope=True
        )


def test_provider_lowercase_florida_label_preserves_selected_scope_and_raw_text(tmp_path):
    from app.ingestion.import_pbdb import plan

    def edit(response):
        response["records"][0]["state"] = "florida"

    records, _ = plan(modified_snapshot(tmp_path, "collections", edit))
    assert len([key for key in records if key[0] == "occurrence"]) == 8
    assert records[("collection", "3535")]["raw"]["state"] == "florida"


def test_one_opinion_identity_retains_both_exact_concept_export_views(tmp_path):
    from app.ingestion.import_pbdb import plan

    views = []

    def edit(response):
        original = response["records"][0]
        alternate = {
            **original,
            "orig_no": "txn:82792",
            "taxon_name": "Calusacypraea",
            "opinion_type": "unsel",
        }
        views.extend([original.copy(), alternate])
        response["records"].append(alternate)
        response["records_found"] += 1
        response["records_returned"] += 1

    records, _ = plan(modified_snapshot(tmp_path, "opinions", edit))
    external = identifier(views[0]["opinion_no"], "opn")
    raw = records[("opinion", external)]["raw"]
    assert sorted(raw["export_views"], key=lambda row: row["orig_no"]) == sorted(
        views, key=lambda row: row["orig_no"]
    )
    assert "orig_no" not in raw
    assert raw["reference_no"] == views[0]["reference_no"]


def test_full_florida_acquisition_pins_and_rechecks_public_census(tmp_path):
    from urllib.parse import parse_qs, urlparse

    from app.ingestion.pbdb import Snapshot
    from app.ingestion.pbdb_snapshot import CanaryAcquisition

    fixture = Snapshot.load(FIXTURE)
    replies = {
        entry["url"]: (FIXTURE / entry["file"]).read_bytes()
        for entry in fixture.manifest["responses"]
    }
    census_calls = []

    def transport(url):
        params = parse_qs(urlparse(url).query)
        if params.get("cc") == ["US"] and params.get("state") == ["Florida"]:
            assert params["limit"] == ["all"] and "base_name" not in params
            kind = "latest" if "/occs/" in url else "collections"
            rows = fixture.records(kind)
            census_calls.append(kind)
            return json.dumps(
                {
                    "data_provider": "The Paleobiology Database",
                    "data_license": "Creative Commons CC0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "records_found": len(rows),
                    "records_returned": len(rows),
                    "records": rows,
                }
            ).encode()
        return replies[url]

    result = CanaryAcquisition(tmp_path / "full", transport=transport).acquire(full_florida=True)
    assert result.manifest["scope"]["mode"] == "full-florida"
    assert result.manifest["scope"]["complete_scope"] is True
    assert len(result.occurrences()) == 8
    assert set(result.manifest["scope"]["collection_ids"]) == {
        "3535",
        "3568",
        "13074",
        "17476",
        "18554",
        "18564",
        "18597",
    }
    assert census_calls == ["latest", "collections", "latest", "collections"]
    census_calls.clear()
    resumed = CanaryAcquisition(
        tmp_path / "resumed", transport=transport, resume=result.path
    ).acquire(full_florida=True)
    assert census_calls == ["latest", "collections"]
    assert all(
        "reused_from" not in entry
        for entry in resumed.manifest["responses"]
        if entry["kind"].endswith("-final")
    )


@pytest.mark.parametrize(
    "name,host,port,user,ci,allowed",
    [
        ("paleograph_test", "localhost", 55432, "paleograph_test", False, True),
        ("paleograph_pbdb_canary", "127.0.0.1", 58432, "paleograph_pbdb_canary", False, True),
        ("paleograph_test", "localhost", 5432, "paleograph_test", True, True),
        ("paleograph_test", "localhost", 5432, "paleograph_test", False, False),
        ("paleograph", "localhost", 5432, "paleograph", True, False),
        ("paleograph_test", "remote.example", 55432, "paleograph_test", True, False),
        ("paleograph_test", "localhost", 55432, "paleograph", True, False),
    ],
)
def test_database_target_guard_excludes_normal_and_remote_databases(
    name, host, port, user, ci, allowed
):
    from app.ingestion.import_pbdb import validate_disposable_target

    if allowed:
        validate_disposable_target(name, host, port, user, ci=ci)
    else:
        with pytest.raises(ValueError, match="disposable"):
            validate_disposable_target(name, host, port, user, ci=ci)


def test_observed_56247_metadata_with_56227_opinion_rows_is_rejected():
    response = {
        "data_provider": "The Paleobiology Database",
        "data_license": "Creative Commons CC0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "records_found": 56247,
        "records_returned": 56247,
        "records": [{"opinion_no": f"opn:{number + 1}"} for number in range(56227)],
    }
    with pytest.raises(ValueError, match="row count mismatch"):
        decode_response(json.dumps(response).encode(), {"rowcount": "yes", "limit": "all"})


def test_taxon_resolution_uses_returned_variant_only_for_provider_unknown_concept(tmp_path):
    import io
    from urllib.error import HTTPError
    from urllib.parse import parse_qs, urlparse

    from app.ingestion.pbdb_snapshot import CanaryAcquisition

    selectors = []

    def transport(url):
        params = parse_qs(urlparse(url).query)
        selector = params.get("id", params.get("taxon_id"))[0]
        selectors.append(selector)
        if params.get("variant") == ["all"] and selector == "txn:37647":
            error = HTTPError(
                url,
                404,
                "Not Found",
                {},
                io.BytesIO(b'{"status_code":404,"errors":["Unknown taxon \'37647\'"]}'),
            )
            raise ValueError("PBDB HTTP 404") from error
        rows = (
            [{"opinion_no": "opn:621367", "orig_no": "txn:37647"}]
            if "/taxa/opinions" in url
            else [{"taxon_no": "var:37647", "orig_no": "txn:37647"}]
        )
        return json.dumps(
            {
                "data_provider": "The Paleobiology Database",
                "data_license": "Creative Commons CC0",
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "records_found": len(rows),
                "records_returned": len(rows),
                "records": rows,
            }
        ).encode()

    client = CanaryAcquisition(tmp_path / "taxonomy", transport=transport)
    client.export_taxonomy(["var:37647"])
    assert selectors == ["var:37647", "txn:37647", "var:37647", "var:37647"]
    assert len(client.responses["taxa"]) == len(client.responses["opinions"]) == 1


def test_taxon_resolution_exports_shared_concept_and_variants_once(tmp_path):
    from urllib.parse import parse_qs, urlparse

    from app.ingestion.pbdb_snapshot import CanaryAcquisition

    urls = []

    def transport(url):
        urls.append(url)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if parsed.path.endswith("/taxa/opinions.json"):
            assert params["taxon_id"] == ["txn:51515"] and "base_id" not in params
            rows = [{"opinion_no": "opn:1"}, {"opinion_no": "opn:2"}]
        elif params.get("variant") == ["all"]:
            assert params["id"] == ["txn:51515"]
            rows = [
                {"taxon_no": "var:43962", "orig_no": "txn:51515", "flags": "V"},
                {"taxon_no": "var:51515", "orig_no": "txn:51515", "flags": "B"},
            ]
        else:
            assert params["id"] == ["var:43962,txn:51515"]
            rows = [
                {"taxon_no": "var:43962", "orig_no": "txn:51515"},
                {"taxon_no": "var:51515", "orig_no": "txn:51515"},
            ]
        assert params["rel"] == ["exact"] and params["limit"] == ["all"]
        return json.dumps(
            {
                "data_provider": "The Paleobiology Database",
                "data_license": "Creative Commons CC0",
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "records_found": len(rows),
                "records_returned": len(rows),
                "records": rows,
            }
        ).encode()

    client = CanaryAcquisition(tmp_path / "taxonomy", transport=transport)
    client.export_taxonomy(["var:43962", "txn:51515", "var:43962"])
    assert len(urls) == 3
    assert len(client.responses["taxa"]) == 2 and len(client.responses["opinions"]) == 2


def modified_snapshot(tmp_path, kind, edit):
    from app.ingestion.pbdb import Snapshot

    target = tmp_path / "snapshot"
    shutil.copytree(FIXTURE, target)
    manifest = json.loads((target / "manifest.json").read_bytes())
    for entry in manifest["responses"]:
        if entry["kind"] != kind:
            continue
        path = target / entry["file"]
        response = json.loads(path.read_bytes())
        edit(response)
        raw = json.dumps(response).encode()
        path.write_bytes(raw)
        entry.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf8")
    return Snapshot.load(target)


def test_retained_taxonomic_scope_cannot_switch_to_descendants(tmp_path):
    from urllib.parse import urlencode

    from app.ingestion.pbdb import Snapshot

    target = tmp_path / "snapshot"
    shutil.copytree(FIXTURE, target)
    manifest = json.loads((target / "manifest.json").read_bytes())
    entry = next(item for item in manifest["responses"] if item["kind"] == "opinions")
    entry["parameters"]["base_id"] = entry["parameters"].pop("taxon_id")
    entry["parameters"]["rel"] = "all_children"
    entry["url"] = entry["url"].split("?")[0] + "?" + urlencode(entry["parameters"])
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf8")
    with pytest.raises(ValueError, match="taxonomic scope"):
        Snapshot.load(target)


@pytest.mark.integration
def test_partial_occurrence_scope_does_not_deactivate_unseen_records(db_session, tmp_path):
    from urllib.parse import urlencode

    from sqlalchemy import text

    from app.discovery.pbdb import occurrence_catalog
    from app.discovery.schemas import ContextQuery
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.pbdb import Snapshot

    snapshot = Snapshot.load(FIXTURE)
    ingest_snapshot(db_session, snapshot)
    target = tmp_path / "subset"
    shutil.copytree(FIXTURE, target)
    manifest = json.loads((target / "manifest.json").read_bytes())
    occurrence = snapshot.occurrences()[0]
    manifest["scope"]["occurrence_ids"] = [occurrence.id]
    material_ids = {
        row["specimen_no"]
        for row in snapshot.records("materials")
        if row["occurrence_no"] == f"occ:{occurrence.id}"
    }
    for entry in manifest["responses"]:
        path = target / entry["file"]
        response = json.loads(path.read_bytes())
        kind = entry["kind"]
        if kind in {"histories", "latest", "originals", "materials"}:
            response["records"] = [
                row for row in response["records"] if row["occurrence_no"] == f"occ:{occurrence.id}"
            ]
            entry["parameters"]["occ_id"] = occurrence.id
        elif kind == "collections":
            response["records"] = [
                row
                for row in response["records"]
                if row["collection_no"] == f"col:{occurrence.collection_id}"
            ]
            entry["parameters"]["coll_id"] = occurrence.collection_id
        elif kind == "measurements":
            response["records"] = [
                row for row in response["records"] if row["specimen_no"] in material_ids
            ]
        response["records_found"] = response["records_returned"] = len(response["records"])
        entry["url"] = entry["url"].split("?")[0] + "?" + urlencode(entry["parameters"])
        raw = json.dumps(response).encode()
        path.write_bytes(raw)
        entry.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf8")
    result = ingest_snapshot(db_session, Snapshot.load(target))
    assert result["occurrences"] == 1 and result["inserted"] == result["updated"] == 0
    assert occurrence_catalog(db_session, ContextQuery()).total == 8
    assert db_session.scalar(text("SELECT count(*) FROM source_record WHERE NOT is_current")) == 0


@pytest.mark.parametrize(
    "unit,value", [("Ma", "30.5"), ("Ka", "18"), ("YBP", "1200"), ("unknown-unit", "100")]
)
def test_determined_dates_keep_entered_units_without_conversion_or_inferred_error(unit, value):
    context = normalize_collection(
        {
            "collection_no": "1",
            "direct_ma_value": value,
            "direct_ma_unit": unit,
            "max_ma": 20,
            "min_ma": 0,
        }
    )
    assert context.dates["direct"].value == Decimal(value)
    assert context.dates["direct"].unit == unit
    assert context.dates["direct"].error is None
    assert context.older_ma == 20 and context.younger_ma == 0


@pytest.mark.parametrize(
    "raw,status",
    [
        ({}, "missing"),
        ({"lat": 28}, "missing"),
        ({"lat": 91, "lng": -82}, "out-of-range"),
        ({"lat": 0, "lng": 0}, "datum-unverified"),
    ],
)
def test_missing_or_unverified_position_never_creates_geometry(raw, status):
    context = normalize_collection({"collection_no": "1", "paleolat": 25, "paleolng": 10, **raw})
    assert context.position.status == status
    assert context.position.geometry is None


@pytest.mark.parametrize(
    "raw",
    [
        {"max_ma": -1},
        {"max_ma": 1, "min_ma": 2},
        {"max_ma": "NaN"},
        {"min_ma": "Infinity"},
        {"max_ma": True},
        {"direct_ma_error": -1},
    ],
)
def test_invalid_scientific_numbers_are_rejected(raw):
    with pytest.raises(ValueError):
        normalize_collection({"collection_no": "1", **raw})


def test_missing_and_partial_provider_age_is_preserved():
    assert normalize_collection({"collection_no": "1"}).older_ma is None
    partial = normalize_collection({"collection_no": "1", "max_ma": 5})
    assert partial.older_ma == 5 and partial.younger_ma is None


def test_source_models_keep_material_measurements_and_opinions_separate():
    from app.ingestion.pbdb import (
        normalize_material,
        normalize_measurement,
        normalize_opinion,
        normalize_reference,
    )

    material = normalize_material(
        {
            "specimen_no": "spm:133",
            "occurrence_no": "occ:187885",
            "specimen_id": "UF:VP 123",
            "n_measured": 4,
            "reference_no": "ref:2375",
        }
    )
    assert material.id == "133" and material.occurrence_id == "187885"
    assert material.catalog_label == "UF:VP 123" and material.recorded_measured_count == 4
    assert material.canonical_specimen_id is None
    measurement = normalize_measurement(
        {
            "measurement_no": "mea:265",
            "specimen_no": "spm:133",
            "average": "115.5",
            "measurement_type": "length",
        }
    )
    assert measurement.material_id == "133" and measurement.values["average"] == Decimal("115.5")
    assert measurement.unit is None
    opinion = normalize_opinion(
        {
            "opinion_no": "opn:1",
            "orig_no": "txn:65044",
            "child_spelling_no": "var:65045",
            "parent_no": "txn:65046",
            "status": "belongs to",
            "reference_no": "ref:51111",
        }
    )
    assert opinion.child_identifier == "var:65045" and opinion.relationship == "belongs to"
    assert opinion.evidence_kind == "taxonomic-opinion"
    reference = normalize_reference(
        {"reference_no": "ref:17344", "doi": "10.1080/02724634.1997.10010984", "pubyr": "1997"}
    )
    assert reference.id == "17344" and reference.doi == "10.1080/02724634.1997.10010984"


@pytest.mark.integration
def test_projection_failure_rolls_back_new_source_and_canonical_revisions(db_session, tmp_path):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.discovery.pbdb import occurrence_catalog
    from app.discovery.schemas import ContextQuery
    from app.ingestion.import_pbdb import DATASET_UUID, ingest_snapshot
    from app.ingestion.pbdb import Snapshot

    original = ingest_snapshot(db_session, Snapshot.load(FIXTURE))
    count = db_session.scalar(text("SELECT count(*) FROM source_record_revision"))
    db_session.execute(
        text(
            "ALTER TABLE catalog_entry ADD CONSTRAINT pbdb_test_projection_failure "
            "CHECK (label NOT LIKE 'PBDB occurrence %') NOT VALID"
        )
    )

    def edit(response):
        response["records"][0]["collection_name"] = "Updated provider context"

    try:
        with pytest.raises(IntegrityError):
            ingest_snapshot(db_session, modified_snapshot(tmp_path, "collections", edit))
        assert db_session.scalar(text("SELECT count(*) FROM source_record_revision")) == count
        assert (
            db_session.scalar(
                text("SELECT version FROM source_dataset WHERE id=:id"), {"id": DATASET_UUID}
            )
            == original["snapshot"]
        )
        assert occurrence_catalog(db_session, ContextQuery()).total == 8
        assert (
            db_session.scalar(
                text("SELECT count(*) FROM collection_event WHERE name='Updated provider context'")
            )
            == 0
        )
        assert (
            db_session.scalar(text("SELECT count(*) FROM ingestion_run WHERE status='failed'")) == 1
        )
    finally:
        db_session.execute(
            text("ALTER TABLE catalog_entry DROP CONSTRAINT pbdb_test_projection_failure")
        )


def test_changed_control_metadata_cannot_be_published_as_a_coherent_history():
    from app.ingestion.pbdb import Snapshot

    snapshot = Snapshot.load(FIXTURE)
    histories = snapshot.records("histories")
    controls = [dict(row) for row in snapshot.records("latest")]
    controls[0]["modified"] = "2099-01-01 00:00:00"
    with pytest.raises(ValueError, match="history"):
        normalize_occurrences(histories, controls, snapshot.records("originals"))


def test_retained_fixture_replays_acquisition_without_live_network(tmp_path):
    from app.ingestion.pbdb import Snapshot
    from app.ingestion.pbdb_snapshot import CanaryAcquisition

    snapshot = Snapshot.load(FIXTURE)
    pending = list(snapshot.manifest["responses"])
    urls = []

    def transport(url):
        urls.append(url)
        entry = pending.pop(0)
        assert url == entry["url"]
        return (FIXTURE / entry["file"]).read_bytes()

    acquired = CanaryAcquisition(tmp_path / "acquired", transport=transport).acquire(
        occurrence_ids=snapshot.manifest["scope"]["occurrence_ids"]
    )
    assert len(acquired.occurrences()) == 8 and len(urls) == len(snapshot.manifest["responses"])
    assert not pending
    assert acquired.manifest["scope"]["selection"] == "fixed IDs"


@pytest.mark.integration
def test_material_membership_change_retains_old_evidence_without_deactivation(db_session, tmp_path):
    from sqlalchemy import text

    from app.discovery.pbdb import inspect_occurrence
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.pbdb import Snapshot, stable_id

    ingest_snapshot(db_session, Snapshot.load(FIXTURE))
    before = inspect_occurrence(db_session, stable_id("occurrence", "187885"))
    assert before["materials"]

    def edit(response):
        response["records"] = [
            row for row in response["records"] if row["occurrence_no"] != "occ:187885"
        ]
        response["records_found"] = response["records_returned"] = len(response["records"])

    # Measurements are dependencies of returned materials; remove their old records
    # from this bounded export while keeping the historical evidence in the database.
    snapshot = modified_snapshot(tmp_path, "materials", edit)
    manifest = snapshot.manifest
    wanted = {row["specimen_no"] for row in snapshot.records("materials")}
    for entry in manifest["responses"]:
        if entry["kind"] == "measurements":
            path = snapshot.path / entry["file"]
            response = json.loads(path.read_bytes())
            response["records"] = [
                row for row in response["records"] if row["specimen_no"] in wanted
            ]
            response["records_found"] = response["records_returned"] = len(response["records"])
            raw = json.dumps(response).encode()
            path.write_bytes(raw)
            entry.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    (snapshot.path / "manifest.json").write_text(json.dumps(manifest), encoding="utf8")
    ingest_snapshot(db_session, Snapshot.load(snapshot.path))
    after = inspect_occurrence(db_session, stable_id("occurrence", "187885"))
    assert after["materials"] == [] and after["material_evidence_count"] == 0
    assert db_session.scalar(text("SELECT count(*) FROM material_evidence")) == 8
    assert db_session.scalar(text("SELECT count(*) FROM source_record WHERE NOT is_current")) == 0


def test_snapshot_tampering_missing_controls_and_mislabelled_selector_are_rejected(tmp_path):
    from app.ingestion.pbdb import Snapshot

    target = tmp_path / "snapshot"
    shutil.copytree(FIXTURE, target)
    manifest = json.loads((target / "manifest.json").read_bytes())
    path = target / manifest["responses"][0]["file"]
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="hash"):
        Snapshot.load(target)
    path.write_bytes(original)
    manifest["responses"][0]["parameters"]["idtype"] = "latest"
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf8")
    with pytest.raises(ValueError, match="disagree"):
        Snapshot.load(target)
    manifest["responses"] = [
        entry for entry in manifest["responses"] if entry["kind"] != "originals"
    ]
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf8")
    with pytest.raises(ValueError, match="completeness"):
        Snapshot.load(target)


@pytest.mark.integration
def test_pbdb_associations_search_age_and_material_evidence_are_typed(db_session):
    from sqlalchemy import text

    from app.discovery.pbdb import inspect_occurrence, occurrence_catalog
    from app.discovery.schemas import ContextQuery
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.pbdb import Snapshot, stable_id

    snapshot = Snapshot.load(FIXTURE)
    ingest_snapshot(db_session, snapshot)
    searched = occurrence_catalog(db_session, ContextQuery(q="Crenatosiren"))
    assert searched.total == 1
    item = searched.items[0]
    assert occurrence_catalog(db_session, ContextQuery(taxon_id=item.taxon_id)).total == 1
    assert occurrence_catalog(db_session, ContextQuery(locality_id=item.locality_id)).total >= 1
    assert (
        occurrence_catalog(
            db_session, ContextQuery(older_ma=item.younger_ma, younger_ma=item.younger_ma)
        ).total
        >= 1
    )
    assert occurrence_catalog(db_session, ContextQuery(older_ma=0, younger_ma=0)).total == 0
    assert (
        occurrence_catalog(db_session, ContextQuery(west=-180, east=180, south=-90, north=90)).total
        == 0
    )
    material = inspect_occurrence(db_session, stable_id("occurrence", "187885"))
    assert material["material_evidence_count"] > 0 and material["materials"]
    assert (
        material["references"]
        and material["provider_age"]["policy"] != "ufvp-geology-v1:ics-2026-06"
    )
    assert db_session.scalar(text("SELECT count(*) FROM specimen")) == 0
    assert db_session.scalar(text("SELECT count(*) FROM age_interpretation")) == 0
    assert db_session.scalar(text("SELECT count(*) FROM collection_reference_evidence")) == 7
    assert db_session.scalar(text("SELECT count(*) FROM identification_evidence")) > 8


@pytest.mark.integration
def test_pbdb_partial_age_does_not_inherit_ufvp_mapping_or_determined_dates(db_session, tmp_path):
    from app.discovery.pbdb import inspect_occurrence, occurrence_catalog
    from app.discovery.schemas import ContextQuery
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.pbdb import stable_id

    def edit(response):
        for row in response["records"]:
            row.pop("min_ma", None)
            row.update(direct_ma_value=1200, direct_ma_unit="YBP", direct_ma_method="14C")

    ingest_snapshot(db_session, modified_snapshot(tmp_path, "collections", edit))
    assert occurrence_catalog(db_session, ContextQuery()).total == 8
    assert all(
        item.older_ma is None and item.younger_ma is None and item.age_basis == "provider-partial"
        for item in occurrence_catalog(db_session, ContextQuery()).items
    )
    assert occurrence_catalog(db_session, ContextQuery(older_ma=10000, younger_ma=0)).total == 0
    detail = inspect_occurrence(db_session, stable_id("occurrence", "148077"))
    assert detail["provider_age"]["determined_dates"]["direct"]["unit"] == "YBP"
    assert detail["source_numeric_age"]["older_ma"] is None


@pytest.mark.integration
def test_changed_context_versions_normalization_even_when_occurrence_bytes_match(
    db_session, tmp_path
):
    from sqlalchemy import text

    from app.discovery.pbdb import inspect_occurrence, occurrence_catalog
    from app.discovery.schemas import ContextQuery
    from app.ingestion.import_pbdb import ingest_snapshot, record_id
    from app.ingestion.pbdb import Snapshot, stable_id

    ingest_snapshot(db_session, Snapshot.load(FIXTURE))
    occ = stable_id("occurrence", "148077")
    before = inspect_occurrence(db_session, occ)
    collection = before["collection_id"]
    # A source dependency changes independently; the old occurrence projection must disappear.
    db_session.execute(
        text("UPDATE source_record SET content_hash=:hash WHERE id=:id"),
        {"id": record_id("collection", collection), "hash": "0" * 64},
    )
    assert occurrence_catalog(db_session, ContextQuery(q="Crenatosiren")).total == 0

    def edit(response):
        for row in response["records"]:
            if row["collection_no"] == f"col:{collection}":
                row.update(max_ma=99, min_ma=98)

    result = ingest_snapshot(db_session, modified_snapshot(tmp_path, "collections", edit))
    after = inspect_occurrence(db_session, occ)
    assert result["updated"] == 1
    assert after["provenance"]["content_hash"] == before["provenance"]["content_hash"]
    assert after["provenance"]["normalization_hash"] != before["provenance"]["normalization_hash"]
    assert after["provider_age"]["older_ma"] == 99
    assert (
        db_session.scalar(
            text("SELECT count(*) FROM normalized_source_revision WHERE source_record_id=:id"),
            {"id": before["provenance"]["source_record_id"]},
        )
        == 2
    )


@pytest.mark.integration
def test_invalid_dependencies_fail_atomically_and_leave_previous_generation(db_session, tmp_path):
    from sqlalchemy import text

    from app.discovery.pbdb import occurrence_catalog
    from app.discovery.schemas import ContextQuery
    from app.ingestion.import_pbdb import DATASET_UUID, ingest_snapshot
    from app.ingestion.pbdb import Snapshot

    before = ingest_snapshot(db_session, Snapshot.load(FIXTURE))

    def edit(response):
        response["records"] = []
        response["records_found"] = response["records_returned"] = 0

    bad = modified_snapshot(tmp_path, "references", edit)
    with pytest.raises(ValueError, match="dependencies"):
        ingest_snapshot(db_session, bad)
    assert occurrence_catalog(db_session, ContextQuery()).total == 8
    assert (
        db_session.scalar(
            text("SELECT version FROM source_dataset WHERE id=:id"), {"id": DATASET_UUID}
        )
        == before["snapshot"]
    )
    assert db_session.scalar(text("SELECT count(*) FROM ingestion_run WHERE status='failed'")) == 1
    assert db_session.scalar(text("SELECT count(*) FROM source_record WHERE NOT is_current")) == 0


@pytest.mark.integration
def test_ufvp_rebuild_preserves_pbdb_and_public_material_stays_separate(db_session, tmp_path):
    from test_ufvp import fixture_rows, make_archive

    from app.discovery.index import rebuild
    from app.discovery.pbdb import occurrence_catalog
    from app.discovery.queries import catalog
    from app.discovery.schemas import ContextQuery
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.import_ufvp import ingest
    from app.ingestion.pbdb import Snapshot

    ingest_snapshot(db_session, Snapshot.load(FIXTURE))
    result = ingest(
        db_session, make_archive(tmp_path, fixture_rows()), raw_dir=tmp_path / "retained"
    )
    assert result.status == "completed"
    rebuild(db_session)
    assert occurrence_catalog(db_session, ContextQuery()).total == 8
    public = catalog(db_session, ContextQuery())
    assert public.total == 8
    assert all(item.specimen_id and item.evidence_kind == "material" for item in public.items)


def test_provider_envelope_is_independent_of_determined_date_and_coordinates():
    context = normalize_collection(
        {
            "collection_no": "17341",
            "collection_name": "I-75",
            "early_interval": "Whitneyan",
            "max_ma": "31.8",
            "min_ma": "29.5",
            "direct_ma_value": "30.5",
            "direct_ma_error": "0.5",
            "direct_ma_unit": "Ma",
            "direct_ma_method": "other",
            "lat": "29.633333",
            "lng": "-82.366669",
            "latlng_basis": "based on political unit",
            "latlng_precision": "minutes",
            "paleolat": 32.45,
            "paleolng": -69.12,
        }
    )
    assert context.older_ma == Decimal("31.8")
    assert context.younger_ma == Decimal("29.5")
    assert context.dates["direct"].value == Decimal("30.5")
    assert context.dates["direct"].error == Decimal("0.5")
    assert context.dates["direct"].unit == "Ma"
    assert context.position.latitude == Decimal("29.633333")
    assert context.position.geometry is None
    assert context.position.status == "datum-unverified"
    assert context.raw["paleolat"] == 32.45


def test_original_reidentification_and_accepted_concept_survive_independently():
    original = {
        "occurrence_no": "45198",
        "collection_no": "3568",
        "flags": "R",
        "identified_name": "Ostrea podogrina",
        "accepted_name": "Ostrea",
        "accepted_no": "16870",
        "reference_no": "124",
    }
    latest = {
        "occurrence_no": "45198",
        "collection_no": "3568",
        "reid_no": "19428",
        "identified_name": "Ostrea podagrina",
        "accepted_name": "Ostrea (Ostrea) podagrina",
        "accepted_no": "81313",
        "reference_no": "11845",
    }
    record = normalize_occurrences([original, latest], [latest], [original])[0]
    assert record.id == "45198"
    assert record.latest.name == "Ostrea podagrina"
    assert record.latest.accepted_name == "Ostrea (Ostrea) podagrina"
    assert record.original.name == "Ostrea podogrina"
    assert [ident.reference_id for ident in record.identifications] == ["124", "11845"]
    assert record.complete_history
    with pytest.raises(ValueError, match="history"):
        normalize_occurrences([original], [latest], [original])


def test_truncated_history_and_changed_rights_cannot_claim_completeness():
    import json

    response = {
        "data_provider": "The Paleobiology Database",
        "data_license": "Creative Commons CC0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "records_found": 1,
        "records_returned": 1,
        "records": [{"occurrence_no": "45198", "flags": "R"}],
    }
    with pytest.raises(ValueError, match="all_idents"):
        decode_response(
            json.dumps(response).encode(), {"all_idents": "yes", "limit": "1"}, history=True
        )
    response["records_found"] = 2
    with pytest.raises(ValueError, match="count"):
        decode_response(
            json.dumps(response).encode(),
            {"idtype": "all", "limit": "all", "occ_id": "45198", "rowcount": "yes"},
            history=True,
        )
    response["records_found"] = 1
    response["data_license"] = "CC BY"
    with pytest.raises(ValueError, match="license"):
        decode_response(
            json.dumps(response).encode(),
            {"idtype": "all", "limit": "all", "occ_id": "45198", "rowcount": "yes"},
            history=True,
        )


def test_explicit_taxon_name_variant_is_accepted_without_losing_raw_namespace():
    assert identifier("var:65045", "txn") == "65045"
    with pytest.raises(ValueError):
        identifier("col:65045", "txn")


@pytest.mark.integration
def test_retained_pbdb_import_is_discoverable_without_manufacturing_specimens(db_session):
    from app.discovery.pbdb import inspect_occurrence, occurrence_catalog
    from app.discovery.queries import catalog
    from app.discovery.schemas import ContextQuery
    from app.ingestion.import_pbdb import ingest_snapshot
    from app.ingestion.pbdb import Snapshot, stable_id

    snapshot = Snapshot.load(FIXTURE)
    result = ingest_snapshot(db_session, snapshot)
    assert result["status"] == "completed"
    assert result["occurrences"] == 8
    page = occurrence_catalog(db_session, ContextQuery(limit=3))
    assert page.total == 8
    assert len(page.items) == 3
    assert all(
        item.specimen_id is None and item.evidence_kind == "occurrence" for item in page.items
    )
    next_page = occurrence_catalog(db_session, ContextQuery(limit=3, cursor=page.next_cursor))
    assert {item.id for item in page.items}.isdisjoint(item.id for item in next_page.items)
    detail = inspect_occurrence(db_session, stable_id("occurrence", "148077"))
    assert detail["history_complete"]
    assert detail["original_identification"]["identified_name"] == "aff. Halitherium olseni"
    assert detail["latest_identification"]["accepted_name"] == "Crenatosiren olseni"
    assert detail["provider_age"]["policy"] == "pbdb-provider-envelope-v1"
    assert detail["source"]["dataset_id"] == stable_id("dataset", "pbdb:public:florida:v1")
    assert detail["source"]["license"] == "CC0 1.0"
    assert detail["source_numeric_age"] == {"older_ma": None, "younger_ma": None}
    assert catalog(db_session, ContextQuery()).total == 0  # public product remains material-only
    repeated = ingest_snapshot(db_session, snapshot)
    assert repeated["inserted"] == 0
    assert repeated["updated"] == 0
    assert repeated["occurrences"] == 8
