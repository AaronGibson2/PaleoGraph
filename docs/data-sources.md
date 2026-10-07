# Data sources and rights

The root [GNU Affero General Public License version 3](../LICENSE), SPDX **AGPL-3.0-only**, applies only to original PaleoGraph software/code. It does not relicense museum records, scientific datasets, images, media, reference materials, maps or publications. Preserve each provider's rights/attribution. No provider endorsement is implied.

## UFVP

The retained Florida import is University of Florida Vertebrate Paleontology DwC-A **v1.182**, published 2026-09-28 and retrieved 2026-10-02: **462,280 records**. Provider: Florida Museum of Natural History; attribution: Rachel Narducci / UFVP. Retained EML explicitly specifies **CC BY-NC 4.0**, requiring attribution and noncommercial use. [Versioned dataset](https://ipt.floridamuseum.ufl.edu/ipt/resource?r=ufvp&v=1.182), [license](https://creativecommons.org/licenses/by-nc/4.0/).

Only [eight attributed offline rows and source metadata](../apps/api/tests/fixtures/ufvp/README.md) are included, not the museum export. Provider-published professional contacts in EML are source provenance, not contributor account details. Fictional test mutations are not provider observations.

Media has distinct per-item rights. Audited multimedia metadata included CC BY-NC 3.0 image terms; the core dataset's license does not license every image. Unknown media rights never inherit fallback terms. Decorative icons are not museum specimen photographs. No complete media collection is redistributed.

## Paleobiology Database

Florida browsing uses **18,915 occurrences** in **1,118 PBDB collections**, retained from public [Data Service 1.2](https://paleobiodb.org/data1.2/) in October 2026. API version is not a frozen database release; snapshots retain requests, timestamps, metadata and content hashes.

Retained responses identify **Creative Commons CC0**, linked to [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). The provider's [FAQ](https://paleobiodb.org/#/faq) describes CC0 International and asks for PBDB/reference/contributor citation; it also contains inconsistent older attribution-license wording. PaleoGraph preserves actual response terms and retrieval context rather than recasting CC0 as CC BY.

The [small fixture](../apps/api/tests/fixtures/pbdb/README.md) includes exact public responses and a URL/timestamp/SHA-256 manifest. No embargoed or authenticated data is used. Material, measurement, taxonomy/opinion and reference assertions retain distinct roles. Metadata does not grant rights to publication full text, PhyloPic imagery or reconstruction-model assets; those assets are not imported.

The global archive-first pipeline is implemented and scale-tested. Actual global PBDB import has not occurred. Unverified datum/CRS semantics keep PBDB positions out of Atlas; source coordinates are retained.

## International Commission on Stratigraphy

The reference is pinned to **ICS 2026/06**: 178 chart units and eight separately cited subepoch compositions. The transcription retains RDF commit, source SHA-256, PDF hash, uncertainty, hierarchy, citations and two documented official-PDF-supported corrections.

[Reference artifact](source-data/ics-2026-06.json), [official chart](https://stratigraphy.org/ICSchart/ChronostratChart2026-06.pdf), [ICS model and terms](https://stratigraphy.org/pages/models/vis.html). Retained reference metadata specifies **CC BY 4.0**; transcription and chart-detail crops are attributed adaptations. Copyright International Commission on Stratigraphy, 2026; colors credited to CGMW. Citation: Cohen, Harper, Gibbard and Car, *The ICS international chronostratigraphic chart this decade*, Episodes 48 (2025), 105–115, [DOI](https://doi.org/10.18814/epiiugs/2025/025001). Reference calibrations are not measured specimen ages.

## Interface artwork, screenshots and maps

The fourteen shipped animal-archetype PNGs were generated with GPT Image and curated as decorative interface artwork, not scientific specimen images or third-party museum assets. Original fallback glyphs contain their own CC0 dedication. Source membership rules select icons; labels do not establish identity. There is no runtime AI service.

The four screenshots show actual local application views with attributed UFVP/PBDB evidence, ICS reference presentation and cartographic layers. Embedded third-party content retains those rights; the software license does not grant unrestricted reuse of all pixels. Attribution remains visible. Screenshots are not downloadable source datasets.

Maps use [OpenFreeMap](https://openfreemap.org/), OpenMapTiles and OpenStreetMap contributors. Preserve displayed attribution and applicable [OpenStreetMap rights](https://www.openstreetmap.org/copyright) and provider terms. No tile/font archive is committed. Cartographic infrastructure is separate from scientific evidence.
