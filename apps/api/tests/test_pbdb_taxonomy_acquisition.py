"""Unique-identity acquisition, bounded paging and archived graph reversibility."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_taxonomy import florida as florida

from app.ingestion.archive import LocalArchiveStore, read_object, verify_archive
from app.ingestion.pbdb import LICENSE, PROVIDER
from app.taxonomy.acquire import Acquisition, replay, seeds, verify_proofs
from app.taxonomy.queries import detail, listing
from app.taxonomy.schemas import TaxonomyQuery


def transport(calls: list[dict[str, list[str]]]):
    def get(url: str) -> bytes:
        query = parse_qs(urlparse(url).query)
        calls.append(query)
        rows = []
        if "/taxa/list.json" in url:
            for identity in query["taxon_id"][0].split(","):
                rows.append(
                    {
                        "orig_no": identity,
                        "taxon_no": "var:" + identity[4:],
                        "taxon_name": "Life" if identity == "txn:1" else "Taxon " + identity,
                        "taxon_rank": "unranked clade" if identity == "txn:1" else "species",
                        "parent_no": "0" if identity == "txn:1" else "txn:1",
                        "accepted_no": identity,
                    }
                )
        return json.dumps(
            {
                "data_provider": PROVIDER,
                "data_license": "Creative Commons CC0",
                "license_url": LICENSE,
                "records": rows,
            }
        ).encode()

    return get


def test_unique_id_acquisition_shared_ancestors_and_offline_checkpoint(tmp_path: Path):
    calls: list[dict[str, list[str]]] = []
    store = LocalArchiveStore(tmp_path / "archive")
    acquisition = Acquisition(store, tmp_path / "checkpoint", transport(calls), delay=0)
    manifest_hash = acquisition.acquire(set(["txn:2", "txn:2", "txn:3"] * 100), [])
    taxon_calls = [call for call in calls if call.get("rel") == ["exact"]]
    assert len(taxon_calls) == 2
    assert taxon_calls[0]["taxon_id"] == ["txn:2,txn:3"]
    assert taxon_calls[1]["taxon_id"] == ["txn:1"]
    manifest = verify_archive(store, manifest_hash)
    assert manifest["counts"]["concepts"] == 3
    second = Acquisition(store, tmp_path / "checkpoint", lambda _: pytest.fail("network"), delay=0)
    second_hash = second.acquire({"txn:2", "txn:3"}, [])
    assert verify_archive(store, second_hash)["snapshot_hash"] == manifest["snapshot_hash"]
    graph = json.loads(
        read_object(store, next(f for f in manifest["files"] if f["kind"] == "pbdb-taxonomy-graph"))
    )
    verify_proofs(store, manifest, graph)
    graph["txn:2"]["parent_no"] = "txn:3"
    with pytest.raises(ValueError, match="disagrees with raw proof"):
        verify_proofs(store, manifest, graph)


def test_exact_selector_variant_resolution_is_witnessed_not_retyped(tmp_path: Path):
    calls: list[dict[str, list[str]]] = []
    base = transport(calls)

    def get(url: str) -> bytes:
        response = json.loads(base(url))
        for row in response["records"]:
            if row["orig_no"] == "txn:22":
                row["orig_no"] = row["accepted_no"] = "txn:2"
        return json.dumps(response).encode()

    store = LocalArchiveStore(tmp_path / "archive")
    manifest = verify_archive(
        store, Acquisition(store, tmp_path / "checkpoint", get, 0).acquire({"txn:22"}, [])
    )
    graph = json.loads(
        read_object(store, next(f for f in manifest["files"] if f["kind"] == "pbdb-taxonomy-graph"))
    )
    assert graph["txn:22"]["orig_no"] == "txn:2"
    assert graph["txn:22"]["selector_resolution"]["requested"] == "txn:22"
    assert calls[0]["taxon_id"] == ["txn:22"]


def test_repeated_page_is_rejected_even_with_broken_provider_count_metadata(
    tmp_path: Path, monkeypatch
):
    import app.taxonomy.acquire as module

    monkeypatch.setattr(module, "PAGE_SIZE", 1)
    calls: list[dict[str, list[str]]] = []
    acquisition = Acquisition(
        LocalArchiveStore(tmp_path / "archive"), tmp_path / "checkpoint", transport(calls), 0
    )
    with pytest.raises(ValueError, match="repeated a page"):
        acquisition.request("taxa/list", ["txn:2"], rel="exact")


@pytest.mark.integration
def test_replay_nests_real_fixture_ids_preserves_sources_and_rebuilds_deterministically(
    florida: Session, tmp_path: Path
):
    identities, retained = seeds(florida)
    assert len(identities) < florida.scalar(text("SELECT count(*) FROM catalog_entry")) * 2
    # The synthetic transport gives every exact selector a witnessed parent; no
    # fixture source records or occurrences are changed to construct the graph.
    before = florida.scalar(
        text("SELECT md5(string_agg(to_jsonb(t)::text,'' ORDER BY id)) FROM occurrence t")
    )
    store = LocalArchiveStore(tmp_path / "archive")
    manifest_hash = Acquisition(store, tmp_path / "checkpoint", transport([]), 0).acquire(
        identities, []
    )
    first = replay(florida, store, manifest_hash)
    roots = listing(florida, TaxonomyQuery(source="pbdb"))
    assert roots.total == 1 and roots.items[0].name == "Life"
    assert roots.items[0].counts.pbdb_occurrence_count == 8
    found = listing(florida, TaxonomyQuery(source="pbdb", q="Velates floridanus"), search=True)
    assert found.items and found.items[0].parent_id is not None
    selected = detail(florida, found.items[0].id, TaxonomyQuery(source="pbdb"))
    assert selected.ancestors[0].name == "Life"
    assert selected.concepts[0].details["hierarchy"]["proof"]
    second = replay(florida, store, manifest_hash)
    assert first["input_hash"] == second["input_hash"]
    assert florida.scalar(text("SELECT count(*) FROM pbdb_taxonomy_snapshot")) == 1
    assert (
        florida.scalar(
            text("SELECT md5(string_agg(to_jsonb(t)::text,'' ORDER BY id)) FROM occurrence t")
        )
        == before
    )
