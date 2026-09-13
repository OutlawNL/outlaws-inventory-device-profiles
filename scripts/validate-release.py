#!/usr/bin/env python3
from __future__ import annotations
import argparse, re, sys, zipfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("package", type=Path)
parser.add_argument("--version", required=True)
args = parser.parse_args()
expected_root = f"outlaws-inventory-v{args.version}/"
forbidden_parts = ("/__pycache__/", "/.pytest_cache/", ".pyc")
required = {expected_root + "app/main.py", expected_root + "install.sh", expected_root + "update.sh", expected_root + "README.md"}
with zipfile.ZipFile(args.package) as archive:
    names = archive.namelist()
    bad_roots = sorted({n.split('/',1)[0] for n in names if n and not n.startswith(expected_root)})
    if bad_roots:
        raise SystemExit(f"Unexpected ZIP root(s): {bad_roots}")
    missing = sorted(required - set(names))
    if missing:
        raise SystemExit(f"Missing required files: {missing}")
    forbidden = [n for n in names if any(part in n for part in forbidden_parts) or "/data/" in n or re.search(r"/Release-Notes-v.*\.md$", n)]
    if forbidden:
        raise SystemExit("Forbidden release artifacts: " + ", ".join(forbidden[:10]))
    main = archive.read(expected_root + "app/main.py").decode("utf-8")
    if f'APP_VERSION = "{args.version}"' not in main:
        raise SystemExit("APP_VERSION does not match package version")
print(f"Release package validated: {args.package.name}")
