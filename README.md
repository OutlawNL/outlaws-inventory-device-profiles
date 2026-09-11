# Outlaw's Inventory Device Profiles

Public Device Profiles for Outlaw's Inventory. A Device Profile is declarative product knowledge: **what the device is, where its firmware information lives, and how the generic Outlaw's Inventory parser should read that source**.

The profile repository is intentionally independent from the Outlaw's Inventory application release cycle. Adding or correcting a supported device should normally require only a Device Profile/catalog update, not an application release.

## Current profiles

- DJI Neo 2
- DJI Mini 4 Pro
- DJI Mini 5 Pro
- DJI Osmo Action 4

These profiles use the generic `release_notes_pdf` capability. Each profile supplies its own download/support URL, rules for identifying the correct Release Notes PDF, the exact firmware-version label, date format, and the boundaries of the What's New section.

## Design rule

The core application provides a fixed set of safe parser capabilities. Profiles compose those capabilities with declarative data. Profiles must never contain executable code or require device-specific `if vendor/model` logic in the core.

For example, the core knows how to:

- fetch an HTTPS HTML source;
- discover and download a PDF;
- extract text from a PDF;
- find a value after a configured label and pattern;
- parse a date after a configured label;
- extract a section between configured headings;
- validate the extracted firmware version.

The profile decides which labels and document matchers apply to its device.

## Repository layout

- `profiles/` — human-readable YAML Device Profiles
- `schemas/` — strict JSON Schema for profile validation
- `catalog/index.json` — generated catalog consumed by Outlaw's Inventory
- `manifest.json` — catalog hash manifest
- `scripts/build_catalog.py` — validates YAML and rebuilds the catalog

## Catalog updates

The runtime catalog is generated from the YAML profiles. When publishing a catalog change, explicitly increment the catalog version:

```bash
python -m pip install -r requirements-dev.txt
python scripts/build_catalog.py --catalog-version 2
```

Profile revisions use `profile_version`; the generated catalog has its own independent `catalog_version`.

## Trust and safety

Profiles are declarative only. No Python, JavaScript, shell commands or arbitrary executable templates belong in a Device Profile. The official repository is maintainer-reviewed. Catalog signing is planned before broad community publishing; the current catalog uses HTTPS plus a SHA-256 manifest and deliberately records that it is not yet signed.

No license has been selected yet. Public visibility does not imply a grant of reuse rights.
