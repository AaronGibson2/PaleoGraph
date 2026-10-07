"""Versioned, snapshot-checked occurrence eligibility; live authority on invalidation."""

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import create_db_engine
from app.discovery.pbdb import ELIGIBLE, parameters
from app.discovery.queries import JOINS, PUBLIC
from app.ingestion.pbdb import ADAPTER_VERSION, POLICY_VERSION

VERSION = f"occurrence-browse-v1:{ADAPTER_VERSION}:{POLICY_VERSION}"
FRESH = """coalesce((SELECT p.built_revision=s.input_revision
    AND p.projection_version=:occurrence_browse_version
    FROM occurrence_browse_state p CROSS JOIN browse_projection_state s
    WHERE p.id=1 AND s.id=1),false)"""
VALIDATED = """coalesce((SELECT projection_version=:occurrence_browse_version
    FROM occurrence_browse_state WHERE id=1),false)"""
MEMBER = """EXISTS (SELECT 1 FROM occurrence_browse_member m
    WHERE m.occurrence_id=ce.occurrence_id AND m.source_record_id=ce.source_record_id
      AND m.content_hash=ce.content_hash AND m.normalization_hash=ce.normalization_hash)"""
CURRENT = """NOT EXISTS (SELECT 1 FROM source_normalization_invalid i
    WHERE i.source_record_id=ce.source_record_id AND i.content_hash=ce.content_hash
      AND i.normalization_hash=ce.normalization_hash)"""


def eligibility(source: str) -> str:
    """Each SELECT independently checks the generation and falls back to exact authority."""
    pbdb = (
        f"(ce.evidence_kind='occurrence' AND ce.specimen_id IS NULL "
        f"AND ce.policy_version=:pbdb_policy AND (({VALIDATED} AND {MEMBER} AND {CURRENT}) "
        f"OR (NOT {VALIDATED} AND ({ELIGIBLE}))))"
    )
    ufvp = f"(ce.evidence_kind='material' AND {PUBLIC})"
    return ufvp if source == "ufvp" else pbdb if source == "pbdb" else f"({ufvp} OR {pbdb})"


def query_parameters() -> dict[str, Any]:
    return {**parameters(), "occurrence_browse_version": VERSION}


def rebuild(session: Session) -> dict[str, Any]:
    """Atomic derived replacement in the caller transaction; never modify source evidence."""
    with session.begin_nested():
        session.execute(text("SELECT pg_advisory_xact_lock(74003501)"))
        revision = session.scalar(
            text("SELECT input_revision FROM browse_projection_state WHERE id=1 FOR UPDATE")
        )
        session.execute(text("DELETE FROM occurrence_browse_member"))
        session.execute(
            text(f"""INSERT INTO occurrence_browse_member
            (occurrence_id,source_record_id,content_hash,normalization_hash)
            SELECT ce.occurrence_id,ce.source_record_id,ce.content_hash,ce.normalization_hash
            {JOINS} WHERE {ELIGIBLE}"""),
            parameters(),
        )
        session.execute(
            text("""INSERT INTO occurrence_browse_state
            (id,built_revision,projection_version) VALUES (1,:revision,:version)
            ON CONFLICT(id) DO UPDATE SET built_revision=excluded.built_revision,
              projection_version=excluded.projection_version,built_at=now()"""),
            {"revision": revision, "version": VERSION},
        )
        session.execute(text("ANALYZE occurrence_browse_member"))
        count = session.scalar(text("SELECT count(*) FROM occurrence_browse_member"))
    return {"projection_version": VERSION, "input_revision": revision, "occurrences": count}


def main() -> None:
    engine = create_db_engine(Settings())
    try:
        with Session(engine) as session:
            if session.scalar(text("SELECT current_database()")) == "paleograph":
                root = Path(__file__).resolve().parents[4]
                checkpoint = json.loads(
                    (root / "data/processed/phase4e-pre-4e-checkpoint.json").read_bytes()
                )
                if checkpoint["status"] != "verified" or checkpoint["label"] != "pre-4e":
                    raise ValueError(
                        "Normal product projection requires the verified pre-4E checkpoint"
                    )
                with Path(checkpoint["path"]).open("rb") as dump:
                    if hashlib.file_digest(dump, "sha256").hexdigest() != checkpoint["sha256"]:
                        raise ValueError("Pre-4E checkpoint changed")
            result = rebuild(session)
            session.commit()
            print(json.dumps(result))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
