"""Explicit offline provenance audit; unavailable bytes always produce failure."""

import argparse
import json
from pathlib import Path

from app.config import Settings
from app.db import create_db_engine
from app.ingestion.archive import ArchiveError, LocalArchiveStore
from app.ingestion.archive_db import (
    audit_archives,
    audit_normalizations,
    audit_raw_revisions,
)
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--normalizations", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = Settings()
    if settings.paleograph_heavy_work_paused:
        raise ValueError("Heavy provenance auditing is paused for storage review")
    engine = create_db_engine(settings)
    try:
        with Session(engine) as session:
            store = LocalArchiveStore(args.store)
            result = audit_archives(session, store)
            if args.raw and result["status"] == "verified":
                try:
                    result["raw"] = audit_raw_revisions(session, store)
                except ArchiveError as error:
                    result.update(status="failed", raw_error=str(error))
            if args.normalizations and result["status"] == "verified":
                try:
                    result["normalizations"] = audit_normalizations(session)
                except ArchiveError as error:
                    result.update(status="failed", normalization_error=str(error))
        encoded = json.dumps(result, indent=2)
        if args.output:
            args.output.write_text(encoded + "\n", encoding="utf8")
        print(encoded)
        if result["status"] != "verified":
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
