# Contributing

Use the [README](README.md) for locked dependencies, local setup and checks. Discuss substantial model, adapter or scientific-policy changes before implementation. Pull requests should describe concrete behavior and relevant validation.

Contributions to original PaleoGraph software are made under the project's [AGPL-3.0-only license](LICENSE) unless the contribution policy changes. Third-party data and media retain their own terms.

## Scientific requirements

- Preserve source identity, raw revisions, exact dependency proofs and rights.
- Distinguish occurrence, physical specimen, museum collection and PBDB context.
- Keep source assertions separate from interpretation; retain uncertainty, qualifiers, missing values and conflicting evidence.
- Never merge taxonomy, places or material by name alone. Candidates are not deterministic identity; reconciliation stays reversible and inspectable.
- Version interpretation/calibration policies and explicitly rebuild affected projections. Model and semantic changes require meaningful tests.
- Respect source-specific media/data rights. Do not commit exports, dumps, credentials or local operational material. Small fixtures require attribution and clear distinction between retained responses and fictional mutations.

Read [data model](docs/data-model.md), [scientific semantics](docs/scientific-semantics.md) and [data sources](docs/data-sources.md) before changing ingestion/discovery.

## Engineering checks

Keep strict Python/TypeScript typing, lint and formatting passing. Run affected unit tests and full README checks for changes spanning API/frontend contracts. Browser tests exercise production builds and the actual API.

Use Alembic for schema changes; do not silently edit historical migrations. Preserve repeatable upgrades and inspect drift. Downgrade/upgrade tests belong only on disposable databases. Avoid destructive operations on scientific databases. Query/projection optimizations must preserve eligibility, counts, source distinctions and provenance.

CI uses read-only permissions, disposable credentials and offline fixtures. Do not introduce production secrets, privileged fork-PR workflows or automatic large acquisitions. Source rights and scientific mappings require primary-source evidence.
