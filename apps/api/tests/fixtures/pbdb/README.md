# Retained PBDB canary fixture

Exact public Data Service 1.2 responses, acquired 2026-10-05 (UTC), licensed CC0 1.0.
The 13 URLs, request parameters, retrieval timestamps, record counts and SHA-256
hashes are retained in `manifest.json`. Snapshot hash:
`3ae6683c4ac384ee99dfb784eba9dc6b4491b1331d4320408b734c1cc813c8f2`.

Eight fixed Florida occurrences exercise original/reidentified/accepted names,
identification qualifiers, provider-calibrated envelopes, modern and paleo positions,
explicit material records, measurements, source opinions and bibliographic references.
Concept IDs are resolved first. Opinion queries use `taxon_id` with `rel=exact`;
name queries include `variant=all` and export each resolved concept once.
These source opinions remain reference-backed taxonomy evidence, not phylogeny.

Tests using modified copies simulate later source responses; they are not live source
observations. Ordinary tests never call PBDB. No UFVP matching is asserted.
