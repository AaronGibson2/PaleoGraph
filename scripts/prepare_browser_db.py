"""Isolated browser-test fixture preparation. Refuses every other database URL."""

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.db import create_db_engine
from app.ingestion.import_ufvp import ingest
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
URL = "postgresql+psycopg://paleograph_browser:paleograph_browser@127.0.0.1:56432/paleograph_browser"


def main() -> None:
    if os.environ.get("DATABASE_URL") != URL:
        raise SystemExit(
            "Browser fixtures require the exact disposable browser database URL"
        )
    sys.path.insert(0, str(ROOT / "apps/api/tests"))
    from test_ufvp import fixture_rows, make_archive

    rows = fixture_rows()
    template = rows[0]
    rows.extend(
        {
            **template,
            "id": f"PALEOGRAPH-TEST-ONLY-{i}",
            "occurrenceID": f"PALEOGRAPH-TEST-ONLY-{i}",
            "catalogNumber": f"TEST-{i:03}",
            "locationID": f"TEST-PLACE-{i % 5}",
            "locality": f"Fictional automated test locality {i % 5}",
            "decimalLatitude": "29.36",
            "decimalLongitude": "-82.19",
            "earliestEpochOrLowestSeries": "Miocene, late" if i < 65 else "Miocene(?)",
        }
        for i in range(73)
    )
    engine = create_db_engine(Settings())
    try:
        with TemporaryDirectory() as folder, Session(engine) as session:
            path = Path(folder)
            run = ingest(
                session, make_archive(path, rows), limit=None, raw_dir=path / "retained"
            )
            if run.status != "completed":
                raise RuntimeError(run.error_summary)
            from app.ingestion.import_pbdb import ingest_snapshot
            from app.ingestion.pbdb import Snapshot

            ingest_snapshot(
                session, Snapshot.load(ROOT / "apps/api/tests/fixtures/pbdb")
            )
            session.commit()
            print(
                json.dumps({"isolated_browser_fixture_records": run.records_accepted})
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
