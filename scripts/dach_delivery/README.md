# Reproducing the DACH delivery

The published package is self-contained for verification. Contract generation additionally needs the five UMAS v3 schema snapshots listed with hashes in `outputs/contracts/contract-roster.json`; the Vela source checkout is not published here.

## Contracts

```sh
python3 scripts/dach_delivery/build_contracts.py --umas-source /path/to/vela-media-asset-service/localstack/schemas
python3 scripts/dach_delivery/verify_delivery.py --skip-manifest
```

The generator uses source schema definitions, not real Kafka payloads. The content input is intentionally a technical gate: root ID required, source discriminators/types retained, structural presence relaxed, unknown fields allowed. The strict flat output contract and mapping describe the selected index projection. Counter fields are an explicitly labelled producer proposal.

The generated Loader profiles are descriptive and deliberately omit environment IDs and executable scripts; do not submit them directly as ARES configuration.

## Document and figure

Requirements: Python 3 with `python-docx`, `PyMuPDF` (figure raster export), and a compatible headless LibreOffice renderer. The authoring environment used Codex bundled runtime 26.1011.11113 and its document skill renderer. In Codex, resolve those runtimes through `load_workspace_dependencies`; use its bundled LibreOffice, not a desktop installation.

```sh
python3 scripts/dach_delivery/build_figure.py
python3 scripts/dach_delivery/build_document.py
```

The document source is `document.md`. Render the DOCX with the Codex document skill's `render_docx.py --emit_pdf` and inspect every page; copy the resulting PDF to `outputs/ARES-DACH-Ingestion-Specification.pdf`. The expected layout is thirteen A4 pages: eight specification pages (page 2 landscape) and five landscape dictionary pages (§11). Office binary hashes may differ with fonts/renderer versions. Keep headings, the eight opening open-point bullets, all tables and the single three-lane figure intact.

After final visual review, refresh the portable manifest and verify:

```sh
python3 scripts/dach_delivery/verify_delivery.py --skip-manifest --write-receipt
python3 scripts/dach_delivery/package_manifest.py
python3 scripts/dach_delivery/verify_delivery.py
```

No script performs deployment or remote publication. Apply JSON Schemas to the JSON payload, not the gRPC envelope. Mapping acceptance, pipeline/decorator execution, schedule behaviour, Merge/reject delivery, API capacity and realtime latency still require target-environment qualification.
