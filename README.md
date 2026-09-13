# Outlaw's Inventory Device Profiles — catalog v8

109 external profiles: 106 DJI consumer/hobbyist devices and three Fujifilm products. See [coverage and exceptions](COVERAGE.md).

Requires Outlaw's Inventory v0.18.8 for the O4 Air Unit version-comparison rule. Upgrade the app first, then publish/synchronize this catalog. Profiles download on demand for matched devices.

Build and validate with `python scripts/build_catalog.py --catalog-version 7` (PyYAML and jsonschema required). Runtime JSON and index are generated from YAML; do not edit generated profiles directly.

The catalog is published at the existing repository root. Preserve `catalog/index.json`, `catalog/profiles/`, profiles, schemas and manifest. Firmware versions are fetched from the declared official source at check time.

Catalog v8 retains 109 profiles. It adds one O4 Air Unit version-comparison rule: a Pro-style stored version is reported as Unknown rather than guessed as an update. The builder validates all inputs and duplicate identities before publishing, stages complete output, and recovers prior artifacts on publication failure.
