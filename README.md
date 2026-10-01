# Outlaw's Inventory Device Profiles — catalog v10

185 external profiles: 106 DJI consumer/hobbyist devices, 78 Fujifilm X-system products and Sennheiser MOMENTUM 4 Wireless. See [coverage and exceptions](COVERAGE.md).

Recommended with Outlaw's Inventory v0.18.18 or newer. Publish/synchronize this catalog after upgrading the app. Profiles download on demand only for matched devices.

Build and validate with `python scripts/build_catalog.py --catalog-version 10` (PyYAML and jsonschema required). Runtime JSON and index are generated from YAML; do not edit generated profiles directly.

The catalog is published at the existing repository root. Preserve `catalog/index.json`, `catalog/profiles/`, profiles, schemas and manifest. Firmware versions are fetched from the declared official source at check time.

Catalog v10 adds the verified Sennheiser MOMENTUM 4 Wireless profile. It reads the maintained Sennheiser Consumer release table with an exact product row, Android version, release date and release-note summary. The profile requires the v0.18.18 `html_release_table` capability.

The builder validates all inputs and duplicate identities before publishing, stages complete output, and recovers prior artifacts on publication failure.
