# Outlaw's Inventory Device Profiles

Public Device Profiles for Outlaw's Inventory. Profiles contain declarative hardware/vendor knowledge; they do not contain executable code.

## Current profiles

- DJI Neo 2
- DJI Mini 4 Pro

Both use the `dji_release_notes_pdf` strategy implemented by the Outlaw's Inventory core: the profile supplies the official DJI download page and matching labels; Outlaw's Inventory discovers the current Release Notes PDF and extracts firmware version/date.

## Repository layout

- `profiles/` — human-readable YAML Device Profiles
- `schemas/` — strict JSON Schema for profile validation
- `catalog/index.json` — generated catalog consumed by Outlaw's Inventory
- `manifest.json` — catalog hash manifest
- `scripts/build_catalog.py` — validates YAML and rebuilds the catalog

## Trust and safety

Profiles are declarative only. No Python, JavaScript, shell commands or arbitrary executable templates belong in a Device Profile. The official repository is maintainer-reviewed. Catalog signing is planned before broad community publishing; the initial v1 catalog uses HTTPS plus a SHA-256 manifest and deliberately records that it is not yet signed.

## Development

```bash
python -m pip install -r requirements-dev.txt
python scripts/build_catalog.py
```

No license has been selected yet. Public visibility does not imply a grant of reuse rights.
