# Ingestion scripts

The official UFVP adapter lives in `apps/api/app/ingestion/`; CLI commands use the
application's configuration, engine and typed normalization boundary. Raw downloads go in ignored
`data/raw/`, normalized artifacts in ignored `data/processed/`.

The implemented pipeline is raw → normalized → deterministic source grouping → canonical.
Every import must retain dataset provenance, track its ingestion run, and be safe to
rerun. Failed or partial runs must never deactivate unseen source records.
Synthetic fixtures are separate from real imports: run
`uv run --project apps/api python -m app.seed_demo` from the repository root.
They use invented associations and two fixed synthetic provenance snapshots.
See the root README for idempotency and reserved-fixture reset behavior.
See [UFVP ingestion](../../docs/ufvp-ingestion.md) for rights, sample/full commands,
identifier rules, raw retention and failure behavior. `scripts/prepare_ufvp_fixture.py`
creates an ignored eight-record offline archive for browser/CLI checks.
