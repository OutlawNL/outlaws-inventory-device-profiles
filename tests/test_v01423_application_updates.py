from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_01423():
    main = (ROOT / "app/main.py").read_text()
    assert 'APP_VERSION = "0.18.8"' in main
    assert 'DATABASE_SCHEMA_VERSION = "0.18.8"' in main
    assert 'INSTALLER_VERSION = "0.18.8"' in main


def test_application_checks_have_dedicated_persistent_model():
    main = (ROOT / "app/main.py").read_text()
    assert "CREATE TABLE IF NOT EXISTS application_checks" in main
    assert "UNIQUE(device_id, application_type)" in main
    assert "details_json TEXT NOT NULL DEFAULT '{}'" in main
    assert "update_output TEXT DEFAULT ''" in main


def test_pihole_commands_are_fixed_not_user_supplied():
    main = (ROOT / "app/main.py").read_text()
    assert 'sudo -n /usr/local/bin/pihole -up --check-only' in main
    assert 'sudo -n /usr/local/bin/pihole -up"' in main
    assert "application_type not in ('pihole', 'minecraft')" in main
    assert 'Unsupported application check' in main


def test_system_checks_ui_uses_compact_labels_and_pihole_name():
    overview = (ROOT / "app/templates/system_checks.html").read_text()
    detail = (ROOT / "app/templates/system_check_detail.html").read_text()
    assert '</b>Ping' in overview
    assert '</b>Disk' in overview
    assert '</b>Pi-hole' in overview
    assert 'name="check_pihole"' in detail
    assert 'Update Pi-hole' in overview
    assert 'Update Pi-hole' in detail


def test_dashboard_uses_software_update_rollup():
    html = (ROOT / "app/templates/dashboard.html").read_text()
    main = (ROOT / "app/main.py").read_text()
    assert '<span>Software Updates</span>' in html
    assert '<h3>Software Update Action Items</h3>' in html
    assert 'software_update_count' in main
    assert 'application_update_actions' in html


def test_daily_checks_run_application_checks_between_system_and_firmware():
    main = (ROOT / "app/main.py").read_text()
    block = main[main.index("def run_due_maintenance_checks"):main.index("def _version_key")]
    assert block.index("execute_all_update_checks()") < block.index("execute_all_application_checks()")
    assert block.index("execute_all_application_checks()") < block.index("execute_all_firmware_checks()")


def test_managed_host_reconfigure_grants_only_exact_pihole_actions():
    main = (ROOT / "app/main.py").read_text()
    block = main[main.index("def configure_remote_host"):main.index("def ensure_managed_host_checks")]
    assert 'NOPASSWD: /usr/local/bin/pihole -up --check-only' in block
    assert 'NOPASSWD: /usr/local/bin/pihole -up' in block
    assert 'NOPASSWD: /bin/bash' not in block
