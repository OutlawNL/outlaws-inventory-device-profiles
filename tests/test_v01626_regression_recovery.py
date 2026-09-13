from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/app.css").read_text(encoding="utf-8")
SYSTEM_CHECKS = (ROOT / "app/templates/system_checks.html").read_text(encoding="utf-8")


def test_release_version_is_01626():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_v01625_broad_admin_only_middleware_is_removed():
    assert "ADMIN_ONLY_PATH_PREFIXES" not in MAIN
    assert "_admin_only_path(path)" not in MAIN
    for route in (
        '@app.post("/settings/system/restart-app")',
        '@app.post("/settings/system/reboot")',
        '@app.post("/settings/system/shutdown")',
        '@app.post("/settings/application-update/check")',
        '@app.post("/settings/application-update/install")',
        '@app.post("/settings/application-update/rollback")',
        '@app.post("/settings/backups/create")',
        '@app.post("/settings/backups/configure")',
        '@app.post("/settings/ssh-profiles")',
        '@app.post("/settings/data-integrity/check")',
    ):
        assert route in MAIN


def test_existing_explicit_administrator_controls_remain():
    # User/authentication administration was intentionally admin-controlled before 0.16.25.
    assert '@app.post("/settings/users/create")' in MAIN
    assert 'if not _is_admin(request):' in MAIN
    assert 'admin_only = {"daily_check_time", "maintenance_check_interval_hours", "default_health_check_interval_minutes", "disk_usage_warning_percent", "disk_usage_critical_percent"}' in MAIN


def test_system_action_feedback_fix_from_01625_is_preserved():
    assert "system_action_message=Outlaw%27s+Inventory+restarted+successfully." in MAIN
    assert "system_actions_open=1#system-actions" in MAIN
    assert "update_message=Outlaw%27s+Inventory+restarted+successfully" not in MAIN


def test_mobile_system_checks_is_a_real_two_column_table():
    assert '<table class="system-checks-mobile-table"' in SYSTEM_CHECKS
    mobile = SYSTEM_CHECKS[SYSTEM_CHECKS.index('<table class="system-checks-mobile-table"'):]
    mobile = mobile[:mobile.index("</table>") + len("</table>")]
    assert "<th>Name</th><th>Status</th>" in mobile
    assert "display:table!important" in CSS
    assert ".system-checks-mobile-table th:last-child" in CSS
    assert "min-width:92px" in CSS
    assert "display:block!important;\n    width:100%!important;" not in CSS[CSS.index("/* System Checks phone view."):CSS.index("/* Dashboard simplification", CSS.index("/* System Checks phone view."))]
