import ast
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAIN_TEXT = (ROOT / "app/main.py").read_text(encoding="utf-8")
SETTINGS = (ROOT / "app/templates/settings.html").read_text(encoding="utf-8")
FORM = (ROOT / "app/templates/device_form.html").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/app.css").read_text(encoding="utf-8")
DOC = (ROOT / "docs/DEVICE_PROFILES.md").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

from app import device_profiles as dp


def _catalog_entry(profile_bytes: bytes, *, model="Neo 2", profile_id="dji-neo-2", profile_version=3):
    return {
        "schema_version": 1,
        "id": profile_id,
        "profile_version": profile_version,
        "origin": "official",
        "status": "verified",
        "updated": "2026-09-11",
        "device": {"vendor": "DJI", "model": model, "aliases": [f"DJI {model}"], "category": "Drone"},
        "profile_url": f"https://example.invalid/{profile_id}.json",
        "sha256": hashlib.sha256(profile_bytes).hexdigest(),
    }


def _profile(*, model="Neo 2", profile_id="dji-neo-2", profile_version=3):
    return {
        "schema_version": 1,
        "id": profile_id,
        "profile_version": profile_version,
        "origin": "official",
        "status": "verified",
        "updated": "2026-09-11",
        "device": {"vendor": "DJI", "model": model, "aliases": [f"DJI {model}"], "category": "Drone"},
        "firmware": {
            "strategy": "release_notes_pdf",
            "source": {"type": "html", "url": "https://www.dji.com/example"},
            "discovery": {"document_type": "pdf", "title_contains": [f"DJI {model} - Release Notes"]},
            "extraction": {
                "version": {"labels": [f"DJI {model} Firmware:"], "pattern": r"[Vv]?\s*([0-9]+(?:\.[0-9]+){2,3})", "group": 1},
                "release_date": {"labels": ["Date:"], "formats": ["%Y.%m.%d"]},
                "whats_new": {"start_labels": ["What's New"], "end_labels": ["Notes:"], "max_items": 3},
            },
        },
    }


class _Response:
    def __init__(self, content: bytes):
        self.content = content
        self.text = content.decode("utf-8")
        self.headers = {"content-type": "application/json"}
    def raise_for_status(self):
        return None
    def json(self):
        return json.loads(self.content)


def test_catalog_is_lightweight_and_runtime_profile_is_downloaded_on_demand(monkeypatch, tmp_path):
    profile_bytes = (json.dumps(_profile(), separators=(",", ":")) + "\n").encode()
    entry = _catalog_entry(profile_bytes)
    catalog = dp.validate_catalog({"schema_version": 1, "catalog_version": 3, "profiles": [entry]})
    assert "firmware" not in catalog["profiles"][0]
    assert dp.installed_profiles(tmp_path) == []

    monkeypatch.setattr(dp.requests, "get", lambda *a, **k: _Response(profile_bytes))
    installed, changed = dp.ensure_profile(tmp_path, entry)
    assert changed is True
    assert installed["firmware"]["strategy"] == "release_notes_pdf"
    assert [p["id"] for p in dp.installed_profiles(tmp_path)] == ["dji-neo-2"]


def test_profile_download_is_hash_pinned(monkeypatch, tmp_path):
    good = (json.dumps(_profile()) + "\n").encode()
    entry = _catalog_entry(good)
    monkeypatch.setattr(dp.requests, "get", lambda *a, **k: _Response(b"{}"))
    with pytest.raises(ValueError, match="hash mismatch"):
        dp.sync_profile(tmp_path, entry)


def test_unused_runtime_profiles_are_pruned(tmp_path):
    for profile_id, model in (("dji-neo-2", "Neo 2"), ("dji-mini-5-pro", "Mini 5 Pro")):
        profile = _profile(model=model, profile_id=profile_id, profile_version=1)
        (tmp_path / f"{profile_id}.json").write_text(json.dumps(profile), encoding="utf-8")
    removed = dp.prune_profiles(tmp_path, {"dji-neo-2"})
    assert removed == 1
    assert [p["id"] for p in dp.installed_profiles(tmp_path)] == ["dji-neo-2"]


def _load_extractors():
    tree = ast.parse(MAIN_TEXT)
    wanted = {"_extract_profile_labeled_value", "_extract_profile_labeled_date"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    def _extract_date_as_iso(value):
        for pattern in (r"(20\\d{2})[.\\-/](\\d{1,2})[.\\-/](\\d{1,2})", r"(\\d{1,2})[.\\-/](\\d{1,2})[.\\-/](20\\d{2})"):
            m = re.search(pattern, value or "")
            if m:
                if len(m.group(1)) == 4:
                    y, mo, d = m.groups()
                else:
                    d, mo, y = m.groups()
                return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        return ""
    ns = {"re": re, "datetime": datetime, "_extract_date_as_iso": _extract_date_as_iso}
    exec(compile(module, "<extractors>", "exec"), ns)
    return ns


def test_pdf_table_column_layout_uses_declared_label_window():
    h = _load_extractors()
    # PyPDF can emit the left table column first and the right column afterwards.
    text = """DJI Mini 4 Pro Release Notes
Date:
Aircraft Firmware:
DJI RC 2 Firmware:
2025.11.05
v01.00.1100
02.02.0300
What's New
Fixed known issues.
Notes:
Restart after update.
"""
    date = h["_extract_profile_labeled_date"](text, {"labels": ["Date:"], "formats": ["%Y.%m.%d"], "max_lines": 12})
    version = h["_extract_profile_labeled_value"](text, {"labels": ["Aircraft Firmware:"], "pattern": r"[Vv]\s*([0-9]+(?:\.[0-9]+){2,3})", "group": 1, "max_lines": 12})
    assert date == "2025-11-05"
    assert version == "01.00.1100"



def test_action4_column_layout_extracts_four_segment_version_and_date():
    h = _load_extractors()
    text = """DJI Osmo Action 4 Release Notes
Date:
Firmware Version:
DJI Mimo App iOS:
2026.07.21
01.07.06.10
v2.11.0
What's New
• Added album password lock.
Notes:
"""
    date = h["_extract_profile_labeled_date"](text, {"labels": ["Date:"], "formats": ["%Y.%m.%d"], "max_lines": 12})
    version = h["_extract_profile_labeled_value"](text, {"labels": ["Firmware Version:"], "pattern": r"(?:[Vv]\s*)?([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", "group": 1, "max_lines": 12})
    assert date == "2026-07-21"
    assert version == "01.07.06.10"

def test_profile_errors_do_not_pollute_whats_new():
    assert '"summary": summary' in MAIN_TEXT
    assert 'firmware_check_error' in MAIN_TEXT
    assert 'request.query_params.get(\'firmware_check_error\')' in FORM
    assert "Release Notes PDF was read, but the profile's firmware-version rule did not produce a valid value." in MAIN_TEXT


def test_settings_distinguishes_catalog_availability_from_installed_profiles_and_uses_normal_typography():
    assert "Available Profiles" in SETTINGS
    assert "Installed Profiles" in SETTINGS
    assert "A full profile is downloaded only when" not in SETTINGS
    assert ".installed-device-profile-row>span:first-child>strong" in CSS
    assert "font-size:.9rem" in CSS


def test_documentation_records_catalog_only_sync_and_on_demand_profiles():
    assert "lightweight catalog" in DOC.lower()
    assert "on demand" in DOC.lower() or "on-demand" in DOC.lower()
    assert "hundreds or thousands" in DOC.lower()
    assert "New device support should normally require only a Device Profile update" in DOC
    assert "0.18.3" in CHANGELOG
