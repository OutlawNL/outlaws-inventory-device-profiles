from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import requests

DEFAULT_CATALOG_URL = os.environ.get(
    "OUTLAWS_DEVICE_PROFILES_CATALOG_URL",
    "https://raw.githubusercontent.com/OutlawNL/outlaws-inventory-device-profiles/main/catalog/index.json",
)
MAX_CATALOG_BYTES = 2 * 1024 * 1024
MAX_PROFILE_BYTES = 256 * 1024
ALLOWED_STRATEGIES = {"release_notes_pdf", "dji_release_notes_pdf", "html_release"}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower().replace("+", "plus"))


def _validate_identity(raw: dict[str, Any], *, context: str) -> None:
    profile_id = str(raw.get("id") or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", profile_id):
        raise ValueError(f"Invalid Device Profile id in {context}.")
    if raw.get("schema_version") != 1 or not isinstance(raw.get("profile_version"), int):
        raise ValueError(f"Invalid Device Profile version: {profile_id}")
    device = raw.get("device")
    if not isinstance(device, dict) or not str(device.get("vendor") or "").strip() or not str(device.get("model") or "").strip():
        raise ValueError(f"Invalid Device Profile identity: {profile_id}")


def validate_profile(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Device Profile must be a JSON object.")
    _validate_identity(payload, context="profile")
    profile_id = str(payload.get("id") or "").strip()
    firmware = payload.get("firmware")
    if not isinstance(firmware, dict) or firmware.get("strategy") not in ALLOWED_STRATEGIES:
        raise ValueError(f"Unsupported Device Profile strategy: {profile_id}")
    source = firmware.get("source")
    source_url = str(source.get("url") or "") if isinstance(source, dict) else ""
    if not source_url.startswith("https://"):
        raise ValueError(f"Device Profile source must use HTTPS: {profile_id}")
    if firmware.get("strategy") == "release_notes_pdf":
        discovery = firmware.get("discovery")
        extraction = firmware.get("extraction")
        if not isinstance(discovery, dict) or discovery.get("document_type") != "pdf":
            raise ValueError(f"Invalid PDF discovery rules: {profile_id}")
        titles = discovery.get("title_contains")
        if not isinstance(titles, list) or not any(str(value).strip() for value in titles):
            raise ValueError(f"Device Profile needs a document title matcher: {profile_id}")
        if not isinstance(extraction, dict):
            raise ValueError(f"Device Profile needs extraction rules: {profile_id}")
        for key in ("version", "release_date", "whats_new"):
            if not isinstance(extraction.get(key), dict):
                raise ValueError(f"Device Profile is missing {key} extraction rules: {profile_id}")
    if firmware.get("strategy") == "html_release":
        extraction = firmware.get("extraction") or {}
        if not isinstance(extraction.get("html"), dict):
            raise ValueError(f"Device Profile needs HTML selectors: {profile_id}")
        for key in ("version", "release_date", "whats_new"):
            if not isinstance(extraction.get(key), dict):
                raise ValueError(f"Device Profile is missing {key} rules: {profile_id}")
    return dict(payload)


def validate_catalog(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Device Profiles catalog must be a JSON object.")
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported Device Profiles catalog schema.")
    version = payload.get("catalog_version")
    if not isinstance(version, int) or version < 1:
        raise ValueError("Invalid Device Profiles catalog version.")
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("Device Profiles catalog is missing profiles.")
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for raw in profiles:
        if not isinstance(raw, dict):
            raise ValueError("Invalid Device Profile catalog entry.")
        _validate_identity(raw, context="catalog")
        profile_id = str(raw.get("id") or "").strip()
        if profile_id in seen:
            raise ValueError(f"Duplicate Device Profile id: {profile_id}")
        seen.add(profile_id)
        profile_url = str(raw.get("profile_url") or "").strip()
        sha256 = str(raw.get("sha256") or "").strip().lower()
        if not profile_url.startswith("https://"):
            raise ValueError(f"Device Profile runtime URL must use HTTPS: {profile_id}")
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError(f"Invalid Device Profile hash: {profile_id}")
        cleaned.append(dict(raw))
    result = dict(payload)
    result["profiles"] = cleaned
    return result


def load_catalog(cache_file: Path) -> dict[str, Any]:
    try:
        return validate_catalog(json.loads(cache_file.read_text(encoding="utf-8")))
    except Exception:
        return {"schema_version": 1, "catalog_version": 0, "profiles": []}


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def sync_catalog(cache_file: Path, *, url: str = DEFAULT_CATALOG_URL, user_agent: str = "OutlawsInventory") -> dict[str, Any]:
    if not url.startswith("https://"):
        raise ValueError("Device Profiles catalog URL must use HTTPS.")
    response = requests.get(url, timeout=15, allow_redirects=True, headers={"User-Agent": user_agent, "Accept": "application/json"})
    response.raise_for_status()
    if len(response.content) > MAX_CATALOG_BYTES:
        raise ValueError("Device Profiles catalog is too large.")
    content_type = (response.headers.get("content-type") or "").lower()
    if "json" not in content_type and not response.text.lstrip().startswith("{"):
        raise ValueError("Device Profiles catalog did not return JSON.")
    catalog = validate_catalog(response.json())
    _atomic_write(cache_file, (json.dumps(catalog, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return catalog


def profile_version_map(catalog: dict[str, Any]) -> dict[str, int]:
    return {
        str(profile.get("id")): int(profile.get("profile_version", 0) or 0)
        for profile in catalog.get("profiles", [])
        if isinstance(profile, dict) and profile.get("id")
    }


def match_profile(catalog: dict[str, Any], vendor: str, model: str) -> dict[str, Any] | None:
    vendor_key = _norm(vendor)
    model_key = _norm(model)
    if not vendor_key or not model_key:
        return None
    matches: list[dict[str, Any]] = []
    for profile in catalog.get("profiles", []):
        if not isinstance(profile, dict):
            continue
        device = profile.get("device") or {}
        if _norm(str(device.get("vendor") or "")) != vendor_key:
            continue
        names = [str(device.get("model") or "")] + [str(value) for value in (device.get("aliases") or [])]
        if model_key in {_norm(value) for value in names if value}:
            matches.append(profile)
    if not matches:
        return None
    return matches[0] if len(matches) == 1 else None


def _profile_cache_file(cache_dir: Path, profile_id: str) -> Path:
    return cache_dir / f"{profile_id}.json"


def load_profile(cache_dir: Path, profile_id: str) -> dict[str, Any] | None:
    try:
        profile = validate_profile(json.loads(_profile_cache_file(cache_dir, profile_id).read_text(encoding="utf-8")))
        return profile if str(profile.get("id") or "") == profile_id else None
    except Exception:
        return None


def sync_profile(cache_dir: Path, catalog_entry: dict[str, Any], *, user_agent: str = "OutlawsInventory") -> dict[str, Any]:
    profile_id = str(catalog_entry.get("id") or "").strip()
    profile_url = str(catalog_entry.get("profile_url") or "").strip()
    expected_hash = str(catalog_entry.get("sha256") or "").strip().lower()
    if not profile_url.startswith("https://"):
        raise ValueError(f"Device Profile runtime URL must use HTTPS: {profile_id}")
    response = requests.get(profile_url, timeout=15, allow_redirects=True, headers={"User-Agent": user_agent, "Accept": "application/json"})
    response.raise_for_status()
    if len(response.content) > MAX_PROFILE_BYTES:
        raise ValueError(f"Device Profile is too large: {profile_id}")
    actual_hash = hashlib.sha256(response.content).hexdigest()
    if not expected_hash or actual_hash != expected_hash:
        raise ValueError(f"Device Profile hash mismatch: {profile_id}")
    profile = validate_profile(response.json())
    if str(profile.get("id") or "") != profile_id:
        raise ValueError(f"Device Profile id mismatch: {profile_id}")
    if int(profile.get("profile_version", 0) or 0) != int(catalog_entry.get("profile_version", 0) or 0):
        raise ValueError(f"Device Profile version mismatch: {profile_id}")
    _atomic_write(_profile_cache_file(cache_dir, profile_id), response.content)
    return profile


def ensure_profile(cache_dir: Path, catalog_entry: dict[str, Any], *, user_agent: str = "OutlawsInventory") -> tuple[dict[str, Any], bool]:
    profile_id = str(catalog_entry.get("id") or "").strip()
    cached = load_profile(cache_dir, profile_id)
    wanted_version = int(catalog_entry.get("profile_version", 0) or 0)
    if cached and int(cached.get("profile_version", 0) or 0) == wanted_version:
        return cached, False
    try:
        return sync_profile(cache_dir, catalog_entry, user_agent=user_agent), True
    except Exception:
        # A catalog/profile outage must not disable a previously cached compatible profile.
        if cached:
            return cached, False
        raise


def installed_profiles(cache_dir: Path) -> list[dict[str, Any]]:
    if not cache_dir.exists():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(cache_dir.glob("*.json")):
        profile = load_profile(cache_dir, path.stem)
        if profile:
            result.append(profile)
    return result


def prune_profiles(cache_dir: Path, required_ids: set[str]) -> int:
    if not cache_dir.exists():
        return 0
    removed = 0
    for path in cache_dir.glob("*.json"):
        if path.stem not in required_ids:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed
