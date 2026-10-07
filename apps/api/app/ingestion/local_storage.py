"""Developer filesystem placement and fail-closed operational capacity checks.

Paths and limits never participate in source identity or scientific hashes.
The PostgreSQL path is the operator-verified host disk image/data location,
not the Linux path reported by a Docker named volume.
"""

import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.config import Settings

GIB = 1024**3
PROFILE_OPTIONS = (
    "-c work_mem=16MB -c temp_file_limit=262144 -c statement_timeout=30000 "
    "-c lock_timeout=5000 -c idle_in_transaction_session_timeout=60000 "
    "-c max_parallel_workers_per_gather=0 -c jit=off -c plan_cache_mode=force_custom_plan"
)


def phase5b1_work() -> Path:
    return Settings().paleograph_data_root.expanduser().resolve() / "phase5b1"


def capacity_plan(
    reservations: list[tuple[str, Path, int]], *, reserve_bytes: int = 20 * GIB
) -> dict[str, Any]:
    """Sum simultaneous reservations per actual host filesystem, including C:."""
    groups: dict[int, dict[str, Any]] = {}
    names: dict[int, list[str]] = defaultdict(list)
    for label, target, required in reservations:
        if required < 0:
            raise ValueError("Disk reservations cannot be negative")
        resolved = target.expanduser().resolve()
        existing = resolved
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        if not existing.exists():
            raise ValueError(f"Storage target unavailable: {resolved}")
        device = existing.stat().st_dev
        names[device].append(label)
        group = groups.setdefault(
            device,
            {
                "filesystem": str(existing.anchor),
                "sample_path": str(existing),
                "free_bytes": shutil.disk_usage(existing).free,
                "required_bytes": 0,
                "safety_reserve_bytes": reserve_bytes,
                "targets": [],
            },
        )
        group["required_bytes"] += required
        group["targets"].append({"label": label, "path": str(resolved), "bytes": required})
    for device, group in groups.items():
        group["labels"] = names[device]
        group["pass"] = group["free_bytes"] >= group["required_bytes"] + reserve_bytes
    return {
        "status": "pass" if all(g["pass"] for g in groups.values()) else "fail",
        "filesystems": list(groups.values()),
    }


def require_large_task_space(
    operation: str, *, files_gib: int = 0, staging_gib: int = 0, postgres_gib: int = 1
) -> dict[str, Any]:
    settings = Settings()
    if settings.paleograph_heavy_work_paused:
        raise ValueError(f"{operation}: heavyweight PaleoGraph work is paused for storage review")
    postgres_path = settings.paleograph_postgres_storage_path
    if postgres_path is None or not postgres_path.exists():
        raise ValueError(
            "Set PALEOGRAPH_POSTGRES_STORAGE_PATH to the verified host storage location"
        )
    system_root = Path(os.environ.get("SystemDrive", "C:") + "/") if os.name == "nt" else Path("/")
    report = capacity_plan(
        [
            ("system drive", system_root, 0),
            ("bulk files and staging", phase5b1_work(), (files_gib + staging_gib) * GIB),
            ("PostgreSQL, indexes, WAL and temporary work", postgres_path, postgres_gib * GIB),
        ]
    )
    report["operation"] = operation
    if report["status"] != "pass":
        raise ValueError(f"{operation}: disk preflight failed: {report}")
    return report
