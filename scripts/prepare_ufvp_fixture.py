"""Build an ignored DwC-A from the eight attributed offline fixture records."""

import csv
import io
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
fixture = root / "apps/api/tests/fixtures/ufvp"
rows = json.loads((fixture / "records.json").read_text(encoding="utf-8"))
output = io.StringIO(newline="")
fields = list(rows[0])
writer = csv.writer(output, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
writer.writerow(fields)
writer.writerows([[row[key] for key in fields] for row in rows])
target = root / "data/raw/ufvp-offline-fixture.zip"
target.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("occurrence.txt", output.getvalue())
    for name in ("eml.xml", "meta.xml"):
        archive.writestr(name, (fixture / name).read_bytes())
print(target)
