# Outlaw's Inventory Device Profiles — catalog v7

109 external profiles: 106 DJI consumer/hobbyist devices and three Fujifilm products. See [coverage and exceptions](COVERAGE.md).

Requires Outlaw's Inventory v0.18.6 for the expanded parsing rules. Upgrade the app first, then publish/synchronize this catalog. Profiles download on demand for matched devices.

Build and validate with `python scripts/build_catalog.py --catalog-version 7` (PyYAML and jsonschema required). Runtime JSON and index are generated from YAML; do not edit generated profiles directly.

The catalog is published at the existing repository root. Preserve `catalog/index.json`, `catalog/profiles/`, profiles, schemas and manifest. Firmware versions are fetched from the declared official source at check time.

Catalog v7 retains the same 109 profiles and firmware rules. Only the builder is hardened: validate all inputs and duplicate identities before publishing, stage complete output, and recover prior artifacts on publication failure.
