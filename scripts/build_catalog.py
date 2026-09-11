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

parser = argparse.ArgumentParser(description="Validate Device Profiles and rebuild the lightweight runtime catalog.")
parser.add_argument("--catalog-version", type=int, default=None, help="Explicit catalog version. Defaults to the existing version.")
args = parser.parse_args()

runtime_dir = ROOT / "catalog" / "profiles"
runtime_dir.mkdir(parents=True, exist_ok=True)
for old in runtime_dir.glob("*.json"):
    old.unlink()

catalog_entries = []
manifest_files = {}
for path in sorted((ROOT / "profiles").rglob("*.yaml")):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        raise SystemExit(f"{path}: " + "; ".join(e.message for e in errors))
    profile_id = data["id"]
    runtime_raw = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    runtime_path = runtime_dir / f"{profile_id}.json"
    runtime_path.write_bytes(runtime_raw)
    digest = hashlib.sha256(runtime_raw).hexdigest()
    runtime_rel = runtime_path.relative_to(ROOT).as_posix()
    manifest_files[runtime_rel] = digest
    catalog_entries.append({
        "schema_version": data["schema_version"],
        "id": profile_id,
        "profile_version": data["profile_version"],
        "origin": data["origin"],
        "status": data["status"],
        "updated": data["updated"],
        "device": data["device"],
        "profile_path": path.relative_to(ROOT).as_posix(),
        "profile_url": f"https://raw.githubusercontent.com/OutlawNL/outlaws-inventory-device-profiles/main/{runtime_rel}",
        "sha256": digest,
    })

if not catalog_entries:
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
    "profiles": catalog_entries,
}
raw = (json.dumps(catalog, indent=2, ensure_ascii=False) + "\n").encode()
(ROOT / "catalog").mkdir(exist_ok=True)
(ROOT / "catalog/index.json").write_bytes(raw)
manifest_files["catalog/index.json"] = hashlib.sha256(raw).hexdigest()
manifest = {
    "schema_version": 1,
    "catalog_version": catalog["catalog_version"],
    "generated": catalog["generated"],
    "files": manifest_files,
    "signature": None,
    "signature_status": "not-signed-yet",
}
(ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"Built catalog v{catalog_version} with {len(catalog_entries)} index entries and on-demand runtime profiles")
