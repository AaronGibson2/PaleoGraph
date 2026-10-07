# Performance

These are representative local development database paths measured in October 2026, not end-to-end browser latency or production SLAs. Cold/warm describes the measured path's cache state, not a universally controlled hardware benchmark. Dataset and query shape must accompany timing claims.

| Path | Before | After | Context |
| --- | --- | --- | --- |
| Locality cold | ~2.4 s | ~136 ms | Florida UFVP browse |
| Locality warm | ~191 ms | ~17 ms | Florida UFVP browse |
| Taxonomy warm | ~525 ms | ~14 ms | Florida UFVP browse |
| PBDB catalog | ~4.18 s | ~66–71 ms | 18,915 Florida occurrences |
| Occurrence detail / references | — | ~6 / 14 ms warm | Scale fixture, indexed point reads |

Browse summaries avoid repeated large joins. Catalog queries select page identities first. Full-text, trigram, B-tree and spatial indexes support each access shape. Request sessions use transaction-local planning settings instead of changing ingestion/server-wide behavior. Native currentness authority accelerates reads while preserving full proofs; dirty-state fallbacks suppress obsolete evidence.

Frontend continuity uses a persistent map, buffered coverage, debounced commits, cancellation, stale-response rejection and revision invalidation. Database timing alone does not measure interaction experience.

## Scale and limits

A retained validation fixture exercised 1,507,657 typed source records, 262,144 occurrences and 29,982,936 proof edges. It includes explicit scale-test data, not an actual global PBDB import. Final resumed ingestion measured approximately 129 MiB peak process RSS; acquisition, earlier attempts and all pipeline phases are not included in that one measurement.

Broad fixture discovery remained slower: warm search ~1.48 s, Lineage ~2.60 s, catalog ~692 ms, time ~767 ms and locality ~1.45 s. Fast point reads do not establish equally fast global exploration.

Design C's current global forecast is ~46.74 GiB PostgreSQL and ~3.09 GiB external archives. These are extrapolations, not observed sizes of an imported global database. WAL, staging and coupled restore headroom exceed final size. No global import or production-scale availability is claimed.
