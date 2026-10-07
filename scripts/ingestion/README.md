# Ingestion tooling

Adapters live in `apps/api/app/ingestion`. They retain snapshots/revisions, normalize typed evidence and publish discovery transactionally. Failed/partial imports never deactivate unseen records. Source identity and full proofs remain distinct from rebuildable projections.

The root [README](../../README.md) provides a small offline preview using `scripts/prepare_ufvp_fixture.py`. Database/browser runners own separate disposable databases and never require complete exports. `scripts/audit_source_archives.py --store <archive-directory>` audits retained bytes and fails explicitly on unavailable/corrupt evidence.

Read [architecture](../../docs/architecture.md), [model](../../docs/data-model.md) and [rights](../../docs/data-sources.md) before acquisition/redistribution. Large downloads, staging databases, archives and output stay outside Git.
