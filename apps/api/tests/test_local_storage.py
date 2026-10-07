from collections import namedtuple
from pathlib import Path

import pytest

from app.ingestion.local_storage import capacity_plan, phase5b1_work, require_large_task_space


def test_same_filesystem_reservations_are_summed(tmp_path, monkeypatch):
    usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(
        "app.ingestion.local_storage.shutil.disk_usage", lambda _p: usage(100, 30, 70)
    )
    plan = capacity_plan(
        [
            ("stage", tmp_path / "new-stage", 25),
            ("postgres", tmp_path / "new-database", 30),
        ],
        reserve_bytes=20,
    )
    assert plan["status"] == "fail"
    assert len(plan["filesystems"]) == 1
    assert plan["filesystems"][0]["required_bytes"] == 55
    assert plan["filesystems"][0]["free_bytes"] == 70


def test_paused_operation_never_probes_or_opens_database(monkeypatch):
    monkeypatch.setenv("PALEOGRAPH_HEAVY_WORK_PAUSED", "true")

    def unexpected_probe(_path):
        pytest.fail("Paused work must refuse before starting capacity or database work")

    monkeypatch.setattr("app.ingestion.local_storage.shutil.disk_usage", unexpected_probe)
    with pytest.raises(ValueError, match="paused for storage review"):
        require_large_task_space("million-scale replay")


def test_postgres_host_location_is_required(tmp_path, monkeypatch):
    monkeypatch.setenv("PALEOGRAPH_HEAVY_WORK_PAUSED", "false")
    monkeypatch.setenv("PALEOGRAPH_POSTGRES_STORAGE_PATH", str(tmp_path / "missing-image.vhdx"))
    with pytest.raises(ValueError, match="verified host storage location"):
        require_large_task_space("pilot")


def test_developer_root_can_relocate_without_scientific_input(tmp_path, monkeypatch):
    monkeypatch.setenv("PALEOGRAPH_DATA_ROOT", str(tmp_path))
    assert phase5b1_work() == tmp_path.resolve() / "phase5b1"


def test_negative_reservation_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="cannot be negative"):
        capacity_plan([("bad", tmp_path, -1)])
