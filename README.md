# Outlaw's Inventory Device Profiles — catalog v9

184 external profiles: 106 DJI consumer/hobbyist devices and 78 Fujifilm X-system products. See [coverage and exceptions](COVERAGE.md).

Recommended with Outlaw's Inventory v0.18.9 or newer. Publish/synchronize this catalog after upgrading the app. Profiles download on demand only for matched devices.

Build and validate with `python scripts/build_catalog.py --catalog-version 9` (PyYAML and jsonschema required). Runtime JSON and index are generated from YAML; do not edit generated profiles directly.

The catalog is published at the existing repository root. Preserve `catalog/index.json`, `catalog/profiles/`, profiles, schemas and manifest. Firmware versions are fetched from the declared official source at check time.

Catalog v9 adds 75 verified Fujifilm profiles: 50 X-series cameras and 25 XF/XC X-mount lenses. Together with the three existing Fujifilm profiles, it covers 51 cameras and 27 lenses. Each profile reads its own official Fujifilm firmware page; the overview pages are used for discovery only. GFX, GF and ETERNA remain outside this consumer/hobbyist release.

The builder validates all inputs and duplicate identities before publishing, stages complete output, and recovers prior artifacts on publication failure.
