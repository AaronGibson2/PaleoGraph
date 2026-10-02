# Contributing

Follow [README.md](README.md) to run both applications locally. Keep work in small,
reviewable branches. Both developers should review changes to scientific semantics,
public API contracts, schema, and dependencies with architectural impact.

- Keep application code small and explicit. Add feature modules only when they have
  a real responsibility; avoid generic repositories and speculative service layers.
- Use strict TypeScript, typed Python API boundaries, SQLAlchemy 2, and Ruff.
- Commit pnpm-lock.yaml and apps/api/uv.lock whenever dependencies change. Use pnpm
  for the frontend and uv for Python; never commit node_modules, .venv, secrets, or data.
- All database schema changes require Alembic migrations. Never call create_all or
  use manual GUI alterations as the normal setup path. Inspect generated migrations;
  PostGIS owns its own tables. Seeds and ingestion are separate from migrations.
- Follow the [glossary](CONTEXT.md), [ADRs](docs/adr/), and [data conventions](docs/data-model.md).
  Preserve source evidence and uncertainty; never silently reinterpret source values.

Before a PR, run the README's lint, typecheck, build, and test commands. For database
changes use `make test-db`, which owns a separate ephemeral Compose project and
runs migrations plus integration tests. Ordinary pytest skips integration unless
TEST_DATABASE_URL explicitly names a migrated disposable database. Never use
valuable development or production data for integration checks. For Explore changes,
run the documented Playwright checks against locally seeded application servers.

Describe the behavior changed, migration implications, and checks actually run.
Include screenshots for meaningful UI changes and report environmental blockers
honestly. Do not claim unexecuted checks passed. CI must pass before merge.

Phase 2 ends at the synthetic Explore vertical slice. Do not introduce real source
ingestion, specimens, search, graph, auth, or deployment as incidental changes.
Resolve the dataset, rights, lifecycle, and reconciliation choices documented in
docs/data-model.md before starting real ingestion.
