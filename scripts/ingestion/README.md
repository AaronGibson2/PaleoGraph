# Ingestion scripts

No external scientific ingestion is implemented. Future source adapters belong here;
add explicit commands only when implemented. Raw downloads go in ignored
`data/raw/`, normalized artifacts in ignored `data/processed/`.

The future pipeline is raw → normalized → deterministic reconciliation → canonical.
Every import must retain dataset provenance, track its ingestion run, and be safe to
rerun. Failed or partial runs must never deactivate unseen source records.
Synthetic fixtures are separate from real imports: run
`uv run --project apps/api python -m app.seed_demo` from the repository root.
They use invented associations and two fixed synthetic provenance snapshots.
See the root README for idempotency and reserved-fixture reset behavior.
