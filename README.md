# Outlaw's Inventory Device Profiles

Public Device Profiles for Outlaw's Inventory. A Device Profile is declarative product knowledge: **what the device is, where its firmware information lives, and how the generic Outlaw's Inventory parser should read that source**.

The profile repository is intentionally independent from the Outlaw's Inventory application release cycle. Adding or correcting a supported device should normally require only a Device Profile/catalog update, not an application release.

## Runtime model

Outlaw's Inventory synchronizes only the lightweight `catalog/index.json` on its daily Device Profiles check. The catalog contains identity/matching metadata, profile version, the URL of the runtime profile and its SHA-256 hash.

The full Device Profile is downloaded only when an Inventory item matches it. Installed profiles are cached locally and refreshed when their catalog revision changes. Profiles that are no longer used by any Inventory item can be removed from the local cache. This keeps an installation small even when the public catalog eventually contains hundreds or thousands of profiles.

Human-maintained YAML remains the source format in this repository. `scripts/build_catalog.py` generates one JSON runtime profile per YAML file under `catalog/profiles/` plus the lightweight index.

## Current DJI profiles

The first broader DJI batch covers 15 profiles:

- DJI Neo 2
- DJI Mini 4 Pro
- DJI Mini 5 Pro
- DJI Osmo Action 3
- DJI Osmo Action 4
- DJI Osmo Action 5 Pro
- DJI Osmo Action 6
- DJI Osmo Pocket 3
- DJI Osmo 360
- DJI Osmo Mobile 7
- DJI Osmo Mobile 7P
- DJI RS 4
- DJI RS 4 Pro
- DJI RS 4 Mini
- DJI RS 5

These profiles use the generic `release_notes_pdf` capability. Each profile supplies its own download/support URL, rules for identifying the correct Release Notes PDF, the exact firmware-version label, date format/look-ahead window, and the boundaries of the What's New section.

## Design rule

The core application provides a fixed set of safe parser capabilities. Profiles compose those capabilities with declarative data. Profiles must never contain executable code or require device-specific `if vendor/model` logic in the core.

The core knows how to fetch HTTPS sources, discover/download PDFs, extract text, find label-bound values, parse declared date formats, extract sections between headings, and validate results. The profile decides which source, labels, patterns and boundaries apply to its device.

## Repository layout

- `profiles/` — human-readable YAML Device Profiles
- `schemas/` — strict JSON Schema for profile validation
- `catalog/index.json` — lightweight generated catalog used for matching
- `catalog/profiles/*.json` — generated on-demand runtime profiles
- `manifest.json` — SHA-256 hashes for generated runtime artifacts
- `scripts/build_catalog.py` — validates YAML and rebuilds runtime artifacts

## Catalog updates

When publishing a catalog change, increment the catalog version:

```bash
python -m pip install -r requirements-dev.txt
python scripts/build_catalog.py --catalog-version 3
```

Profile revisions use `profile_version`; the generated catalog has its own independent `catalog_version`.

## Trust and safety

Profiles are declarative only. No Python, JavaScript, shell commands or arbitrary executable templates belong in a Device Profile. Runtime profile JSON is hash-pinned from the catalog, in addition to HTTPS transport. Catalog signing remains planned before broad community publishing.

No license has been selected yet. Public visibility does not imply a grant of reuse rights.
