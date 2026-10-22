# Outlaw's Inventory Device Profiles — catalog v16

189 external profiles: 106 DJI consumer/hobbyist devices, 78 Fujifilm X-system products, Sennheiser MOMENTUM 4 Wireless, APsystems ECU-R, myenergi zappi V2.1, HiBy R1 and M-VAVE FM-1. See [coverage and exceptions](COVERAGE.md).

Requires Outlaw's Inventory v0.18.28 or newer. Publish/synchronize this catalog after upgrading the app. Profiles download on demand only for matched devices.

Build and validate with `python scripts/build_catalog.py --catalog-version 16` (PyYAML and jsonschema required). Runtime JSON and index are generated from YAML; do not edit generated profiles directly.

The catalog is published at the existing repository root. Preserve `catalog/index.json`, `catalog/profiles/`, profiles, schemas and manifest. Firmware versions are fetched from the declared official source at check time.

Catalog v16 adds a verified M-VAVE FM-1 profile. It reads the exact PC Firmware item and currently detects V16, dated 21 October 2026.

Catalog v15 adds a verified HiBy R1 profile, which reads the exact official R1 firmware entry from the HiBy Help Center and currently detects v2.0.

Catalog v14 adds a verified myenergi zappi V2.1 / multiphase profile. It reads Myenergi's public Help Centre API rather than the Cloudflare-protected release-notes listing. The generic `json_html_release_table` capability requires Outlaw's Inventory v0.18.27 or newer.

Catalog v9 adds 75 verified Fujifilm profiles: 50 X-series cameras and 25 XF/XC X-mount lenses. Together with the three existing Fujifilm profiles, it covers 51 cameras and 27 lenses. Each profile reads its own official Fujifilm firmware page; the overview pages are used for discovery only. GFX, GF and ETERNA remain outside this consumer/hobbyist release.

The builder validates all inputs and duplicate identities before publishing, stages complete output, and recovers prior artifacts on publication failure.
