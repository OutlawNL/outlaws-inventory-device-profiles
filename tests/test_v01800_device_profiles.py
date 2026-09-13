from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.device_profiles import match_profile, validate_catalog

MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")
FORM = (ROOT / "app/templates/device_form.html").read_text(encoding="utf-8")
SETTINGS = (ROOT / "app/templates/settings.html").read_text(encoding="utf-8")
DOC = (ROOT / "docs/DEVICE_PROFILES.md").read_text(encoding="utf-8")


def _catalog():
    return {
        "schema_version": 1,
        "catalog_version": 1,
        "profiles": [
            {
                "schema_version": 1,
                "id": "dji-neo-2",
                "profile_version": 1,
                "origin": "official",
                "status": "verified",
                "updated": "2026-09-11",
                "device": {"vendor": "DJI", "model": "Neo 2", "aliases": ["DJI Neo 2"], "category": "Drone"},
                "profile_url": "https://raw.githubusercontent.com/OutlawNL/outlaws-inventory-device-profiles/main/catalog/profiles/dji-neo-2.json",
                "sha256": "0" * 64,
            }
        ],
    }


def test_catalog_validation_and_exact_vendor_model_matching():
    catalog = validate_catalog(_catalog())
    assert match_profile(catalog, "DJI", "Neo 2")["id"] == "dji-neo-2"
    assert match_profile(catalog, "dji", "DJI Neo 2")["id"] == "dji-neo-2"
    assert match_profile(catalog, "DJI", "Neo") is None
    assert match_profile(catalog, "Other", "Neo 2") is None


def test_profile_catalog_is_public_external_runtime_data():
    assert "raw.githubusercontent.com/OutlawNL/outlaws-inventory-device-profiles/main/catalog/index.json" in (ROOT / "app/device_profiles.py").read_text()
    assert "DEVICE_PROFILES_CACHE_FILE" in MAIN
    assert "profiles remain usable" in MAIN.lower()


def test_add_device_live_profile_matching_is_non_blocking():
    assert 'id="device-profile-match"' in FORM
    assert "/device-profiles/match?vendor=" in FORM
    assert "Device Profile found" in FORM
    assert "Without a Device Profile, Outlaw's Inventory uses the generic parser" in FORM


def test_exact_profile_precedes_existing_provider_fallbacks():
    profile_pos = MAIN.index("profile_result = _device_profile_result(device)")
    old_dji_pos = MAIN.index("dji = _dji_result(device)")
    assert profile_pos < old_dji_pos
    assert 'strategy != "dji_release_notes_pdf"' in MAIN


def test_settings_exposes_profile_catalog_status_and_manual_sync():
    for label in ("Catalog Version", "Installed Profiles", "Last Checked", "Last Updated", "Profiles Updated", "Check Now"):
        assert label in SETTINGS
    assert 'action="/settings/device-profiles/check"' in SETTINGS
    assert "Device Profiles, System, Application, then Firmware" in SETTINGS


def test_device_profile_architecture_is_documented():
    assert "Reuse first. Specialize only when necessary." in DOC
    assert "DJI Neo 2" in DOC
    assert "DJI Mini 4 Pro" in DOC
    assert "declarative data only" in DOC
    assert "Cryptographic signing" in DOC
