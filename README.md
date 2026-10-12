# ARES unified schema

DACH ingestion contract for the UMAS v3 catalogue, scoped to **JOYN, JOYN_AT and JOYN_CH**. Three standard ARES Loaders converge on one content ID: Super creates/updates the catalogue; Metadata and Counters update their own fields on existing contents.

## Deliverables

- [Formal specification — PDF](outputs/ARES-DACH-Ingestion-Specification.pdf) and [editable Word document](outputs/ARES-DACH-Ingestion-Specification.docx), with open points first and one three-lane flow.
- [Content Loader input JSON Schema](outputs/schemas/content-loader.schema.json).
- [Counters Loader input JSON Schema](outputs/schemas/counters-loader.schema.json).
- [Shared OpenSearch mapping](outputs/opensearch/dach-content.mapping.json).
- [Flat content output contract](outputs/contracts/content-output-contract.json) and [Loader configuration profiles](outputs/contracts/loader-profiles.json).
- [Contract roster and provenance](outputs/contracts/contract-roster.json), [synthetic input examples](outputs/contracts/), [editable flow](outputs/figures/ingestion-three-lanes.svg), and [verification receipt](outputs/verification.json).

These are reviewable configuration artifacts. They do not create Loaders, install scripts or deploy an index. The document identifies outstanding Product, catalogue, producer and operational decisions. In particular, the 36-field counters contract uses proposed AVOD/SVOD labels and nullable complete snapshots, pending producer confirmation. Detailed Metadata fields remain outside this delivery.

## Reproduction and checks

Run [the package verifier](scripts/dach_delivery/verify_delivery.py) with Python 3 and `jsonschema` installed:

```sh
python3 scripts/dach_delivery/verify_delivery.py
```

It checks schema validity, synthetic positive/negative cases, field ownership and mapping alignment. It does not contact ARES or OpenSearch. [Reproduction instructions](scripts/dach_delivery/README.md) describe regeneration and document rendering. The [package manifest](outputs/manifest.json) uses portable relative paths and SHA-256 hashes.

The repository contains the reviewed delivery and its generators. Real Kafka examples, the Vela source checkout, partner source documents and historical local analysis are intentionally outside the published package. The local workspace retains the ongoing register and audit boards; no real payloads are required for the published checks.
