from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
SYSTEM = (ROOT / "app" / "templates" / "system_checks.html").read_text(encoding="utf-8")
FIRMWARE = (ROOT / "app" / "templates" / "firmware.html").read_text(encoding="utf-8")
UI_STYLE = (ROOT / "docs" / "UI_STYLE.md").read_text(encoding="utf-8")


def test_release_version_is_01629():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_check_all_actions_keep_browser_on_overview_and_show_spinner():
    assert 'id="system-check-all-form"' in SYSTEM
    assert 'button-spinner' in SYSTEM
    assert "event.preventDefault();" in SYSTEM
    assert "fetch(form.action, {method:'POST'" in SYSTEM
    assert "pollSystemCheckAll()" in SYSTEM
    assert "window.location.replace('/system-checks')" in SYSTEM

    assert 'id="firmware-check-all-form"' in FIRMWARE
    assert 'button-spinner' in FIRMWARE
    assert "event.preventDefault();" in FIRMWARE
    assert "fetch(form.action, {method:'POST'" in FIRMWARE
    assert "poll();" in FIRMWARE
    assert "window.location.replace('/firmware')" in FIRMWARE


def test_static_check_all_get_fallbacks_precede_dynamic_integer_routes():
    system_static = MAIN.index('@app.get("/system-checks/check-all"')
    system_dynamic = MAIN.index('@app.get("/system-checks/{device_id}"')
    assert system_static < system_dynamic

    updates_static = MAIN.index('@app.get("/updates/check-all"')
    updates_dynamic = MAIN.index('@app.get("/updates/{check_id}"')
    assert updates_static < updates_dynamic

    assert '@app.get("/firmware/check-all", include_in_schema=False)' in MAIN
    assert '@app.get("/health/check-all", include_in_schema=False)' in MAIN


def test_long_running_post_action_refresh_fallbacks_exist():
    routes = [
        '/system-checks/{device_id}/check',
        '/system-checks/{device_id}/upgrade',
        '/system-checks/{device_id}/applications/pihole/update',
        '/system-checks/{device_id}/applications/minecraft/update',
        '/system-checks/{device_id}/reboot',
        '/settings/system/restart-app',
        '/settings/system/reboot',
        '/settings/system/shutdown',
        '/settings/application-update/check',
        '/settings/application-update/prepare',
        '/settings/application-update/install',
        '/settings/application-update/rollback',
        '/settings/data-integrity/check',
        '/settings/backups/create',
        '/settings/backups/restore-upload',
        '/settings/backups/{filename}/restore',
        '/devices/{device_id}/host-integration/validate',
        '/devices/{device_id}/check',
        '/updates/{check_id}/check',
        '/updates/{check_id}/upgrade',
        '/updates/{check_id}/reboot',
    ]
    for route in routes:
        assert f'@app.get("{route}"' in MAIN, route


def test_long_running_action_rule_is_documented():
    assert '## Long-running Actions' in UI_STYLE
    assert 'normal GET page' in UI_STYLE
    assert '405' in UI_STYLE and '422' in UI_STYLE


def test_self_update_and_rollback_progress_live_on_get_route():
    assert '@app.get("/settings/application-update/progress"' in MAIN
    assert 'return RedirectResponse(f"/settings/application-update/progress?version={quote(latest)}", status_code=303)' in MAIN
    assert 'return RedirectResponse(f"/settings/application-update/progress?version={quote(rollback_version)}", status_code=303)' in MAIN
    assert "return _application_update_progress_page(target, success_url)" in MAIN


def test_legacy_single_update_check_redirect_has_defined_device_id():
    start = MAIN.index('def check_updates_one(check_id: int):')
    end = MAIN.index('@app.post("/updates/{check_id}/upgrade")', start)
    block = MAIN[start:end]
    assert 'device_id = int(check["device_id"] or 0) if check else 0' in block
