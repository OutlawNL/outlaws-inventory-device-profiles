from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
SYSTEM = (ROOT / "app" / "templates" / "system_checks.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "app" / "templates" / "system_check_detail.html").read_text(encoding="utf-8")
FIRMWARE = (ROOT / "app" / "templates" / "firmware.html").read_text(encoding="utf-8")


def test_release_version_is_01627():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_minecraft_release_lookup_failure_is_attention_not_failed():
    block = MAIN[MAIN.index("if application_type == 'minecraft':"):MAIN.index("# Pi-hole's update checker")]
    assert "return {'status':'attention','details':details,'error':f'Could not retrieve latest Minecraft release: {exc}'}" in block
    assert "return {'status':'attention','details':details,'error':'Could not retrieve latest Minecraft release.'}" in block
    assert "return {'status':'failed','details':details,'error':f'Could not retrieve latest Minecraft release" not in block
    # Runtime and listening-port failures must be evaluated before the release lookup.
    assert block.index("runtime_state in ('failed','stopped')") < block.index("try: latest=_latest_minecraft_release()")
    assert block.index("not port_status.get('listening')") < block.index("try: latest=_latest_minecraft_release()")


def test_minecraft_attention_aggregates_to_host_attention_and_is_presented_as_warning():
    status_block = MAIN[MAIN.index("def _system_check_status"):MAIN.index("def _system_check_rows")]
    assert 'in {"available", "attention"}' in status_block
    assert "server.minecraft.status in ['available','attention']" in SYSTEM
    assert "server.minecraft.status in ['available','attention']" in DETAIL
    assert "Version check unavailable" in DETAIL


def test_phone_system_checks_and_firmware_share_compact_two_column_layout():
    assert '<table class="system-checks-mobile-table"' in SYSTEM
    assert '<table class="firmware-mobile-table"' in FIRMWARE
    assert '<th>Device</th><th>Status</th>' in FIRMWARE
    mobile_css = CSS[CSS.index("/* v0.16.27 phone overview consistency") :]
    assert ".system-checks-mobile-table," in mobile_css
    assert ".firmware-mobile-table{" in mobile_css
    assert "width:62%" in mobile_css
    assert "width:38%" in mobile_css
    assert "text-align:center!important" in mobile_css
    assert ".firmware-table{display:none!important}" in mobile_css
    assert ".firmware-mobile-table{display:table!important}" in mobile_css


def test_runtime_health_refresh_preserves_release_lookup_attention():
    runtime = MAIN[MAIN.index("def execute_minecraft_runtime_check"):MAIN.index("def execute_application_check")]
    assert "release_check_attention" in runtime
    assert "previous_error.startswith('Could not retrieve latest Minecraft release')" in runtime
    assert "elif release_check_attention:" in runtime
    assert "status='attention'; error=previous_error" in runtime
