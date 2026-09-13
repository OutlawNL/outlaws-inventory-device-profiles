import ast
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_TEXT = (ROOT / "app/main.py").read_text(encoding="utf-8")
DOC = (ROOT / "docs/DEVICE_PROFILES.md").read_text(encoding="utf-8")
PROFILE_RUNTIME = (ROOT / "app/device_profiles.py").read_text(encoding="utf-8")


def _load_helpers():
    tree = ast.parse(MAIN_TEXT)
    wanted = {
        "_extract_profile_labeled_value",
        "_extract_profile_labeled_date",
        "_extract_profile_section",
    }
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])

    def _extract_date_as_iso(value):
        for pattern in (r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", r"(\d{1,2})[.\-/](\d{1,2})[.\-/](20\d{2})"):
            m = re.search(pattern, value or "")
            if m:
                if len(m.group(1)) == 4:
                    y, mo, d = m.groups()
                else:
                    d, mo, y = m.groups()
                return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        return ""

    ns = {"re": re, "datetime": datetime, "_extract_date_as_iso": _extract_date_as_iso}
    exec(compile(module, "<profile-helpers>", "exec"), ns)
    return ns


HELPERS = _load_helpers()
_extract_profile_labeled_value = HELPERS["_extract_profile_labeled_value"]
_extract_profile_labeled_date = HELPERS["_extract_profile_labeled_date"]
_extract_profile_section = HELPERS["_extract_profile_section"]


def test_profile_extracts_exact_neo2_firmware_label_not_other_versions():
    text = """DJI Neo 2 Release Notes
Date: 2026.06.23
DJI Neo 2 Firmware: V01.00.0700
DJI RC-N3 Firmware: V01.00.0200
DJI Goggles N3 Firmware: V01.00.0900
DJI Fly App: v1.21.0
What's New
• Added support for Highlight Slow-Mo.
• Fixed known issues.
Notes:
Restart after update.
"""
    rule = {"labels": ["DJI Neo 2 Firmware:"], "pattern": r"[Vv]?([0-9]+(?:\.[0-9]+){2,3})", "group": 1}
    assert _extract_profile_labeled_value(text, rule) == "01.00.0700"


def test_profile_extracts_action4_generic_firmware_version_label():
    text = "Date: 2024.11.26\nFirmware Version: 01.06.04.10\nDJI Mimo App iOS: v2.1.8"
    rule = {"labels": ["Firmware Version:"], "pattern": r"[Vv]?([0-9]+(?:\.[0-9]+){2,3})", "group": 1}
    assert _extract_profile_labeled_value(text, rule) == "01.06.04.10"


def test_profile_extracts_declared_release_date():
    text = "DJI Neo 2 Release Notes\nDate: 2026.06.23\nDJI Neo 2 Firmware: V01.00.0700"
    rule = {"labels": ["Date:"], "formats": ["%Y.%m.%d"]}
    assert _extract_profile_labeled_date(text, rule) == "2026-06-23"


def test_profile_extracts_only_whats_new_section():
    text = """DJI Neo 2 Release Notes
Date: 2026.06.23
DJI Neo 2 Firmware: V01.00.0700
What's New
• Added support for Highlight Slow-Mo and Helix Close-Up modes.
• Fixed known issues.
Notes:
• Restart the aircraft after the update.
"""
    rule = {"start_labels": ["What's New", "What’s New"], "end_labels": ["Notes:", "Notes"], "max_items": 3}
    assert _extract_profile_section(text, rule) == (
        "Added support for Highlight Slow-Mo and Helix Close-Up modes.\nFixed known issues."
    )


def test_runtime_supports_declarative_release_notes_pdf_profile():
    from app.device_profiles import ALLOWED_STRATEGIES
    assert {'release_notes_pdf', 'dji_release_notes_pdf', 'html_release'} <= ALLOWED_STRATEGIES
    assert 'firmware.get("strategy") == "release_notes_pdf"' in PROFILE_RUNTIME
    assert "Device Profile needs extraction rules" in PROFILE_RUNTIME


def test_documentation_records_core_profile_boundary_and_generic_fallback():
    assert "New device support should normally require only a Device Profile update" in DOC
    assert "Generic parser remains the fallback" in DOC
    assert "release_notes_pdf" in DOC
    assert 'strategy == "release_notes_pdf"' in MAIN_TEXT
