from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
BASE = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
SYSTEM = (ROOT / "app" / "templates" / "system_checks.html").read_text(encoding="utf-8")
FIRMWARE = (ROOT / "app" / "templates" / "firmware.html").read_text(encoding="utf-8")
UI_STYLE = (ROOT / "docs" / "UI_STYLE.md").read_text(encoding="utf-8")


def test_release_version_is_01628():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_desktop_overviews_use_shared_alignment_semantics():
    assert 'class="system-checks-classic-table system-checks-desktop-table" data-ui-table="system-overview"' in SYSTEM
    assert '<th>Name</th><th>System</th><th>Application</th><th>Last Checked</th><th>Status</th><th>Action</th>' in SYSTEM
    assert 'class="firmware-table" data-ui-table="firmware-overview"' in FIRMWARE
    block = CSS[CSS.index("/* v0.16.28 shared overview-table alignment standard.") :]
    assert 'table[data-ui-table="system-overview"] th,' in block
    assert 'text-align:left!important' in block
    assert 'th:nth-child(5)' in block
    assert 'th:nth-child(6)' in block
    assert 'table[data-ui-table="firmware-overview"] th:nth-child(6)' in block
    assert 'text-align:center!important' in block


def test_firmware_and_system_checks_share_real_compact_phone_table():
    assert 'class="system-checks-mobile-table" data-ui-compact-mobile="true"' in SYSTEM
    assert 'class="firmware-mobile-table" data-ui-compact-mobile="true"' in FIRMWARE
    assert "table.dataset.uiCompactMobile === 'true'" in BASE
    block = CSS[CSS.index("/* v0.16.28 shared overview-table alignment standard.") :]
    assert 'table[data-ui-compact-mobile="true"]{' in block
    assert 'display:table!important' in block
    assert 'display:table-header-group!important' in block
    assert 'display:table-row!important' in block
    assert 'width:62%!important' in block
    assert 'width:38%!important' in block
    assert '.firmware-table{display:none!important}' in block


def test_ui_style_documents_reusable_alignment_rule():
    assert '## Overview Table Alignment' in UI_STYLE
    assert 'textual and data columns are left-aligned' in UI_STYLE
    assert '`data-ui-table`' in UI_STYLE
    assert '`data-ui-compact-mobile`' in UI_STYLE
