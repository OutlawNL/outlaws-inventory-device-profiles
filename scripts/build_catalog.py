#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from datetime import date
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/device-profile-v1.schema.json").read_text())
validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

parser = argparse.ArgumentParser(description="Validate Device Profiles and rebuild the runtime catalog.")
parser.add_argument("--catalog-version", type=int, default=None, help="Explicit catalog version. Defaults to the existing version.")
args = parser.parse_args()

profiles = []
for path in sorted((ROOT / "profiles").rglob("*.yaml")):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        raise SystemExit(f"{path}: " + "; ".join(e.message for e in errors))
    data["profile_path"] = path.relative_to(ROOT).as_posix()
    profiles.append(data)
if not profiles:
    raise SystemExit("No Device Profiles found")

existing = ROOT / "catalog/index.json"
old_version = 0
if existing.exists():
    try:
        old_version = int(json.loads(existing.read_text()).get("catalog_version", 0))
    except Exception:
        pass
catalog_version = args.catalog_version if args.catalog_version is not None else max(1, old_version)
if catalog_version < 1:
    raise SystemExit("catalog version must be >= 1")

catalog = {
    "schema_version": 1,
    "catalog_version": catalog_version,
    "generated": str(date.today()),
    "repository": "OutlawNL/outlaws-inventory-device-profiles",
    "profiles": profiles,
}
raw = (json.dumps(catalog, indent=2, ensure_ascii=False) + "\n").encode()
(ROOT / "catalog").mkdir(exist_ok=True)
(ROOT / "catalog/index.json").write_bytes(raw)
manifest = {
    "schema_version": 1,
    "catalog_version": catalog["catalog_version"],
    "generated": catalog["generated"],
    "files": {"catalog/index.json": hashlib.sha256(raw).hexdigest()},
    "signature": None,
    "signature_status": "not-signed-yet",
}
(ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"Built catalog v{catalog_version} with {len(profiles)} profiles")
