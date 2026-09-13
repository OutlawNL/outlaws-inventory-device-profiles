from pathlib import Path

def test_check_all_uses_current_update_executor():
    text = Path("app/main.py").read_text()
    helper_start = text.index("def run_all_system_checks")
    helper_end = text.index('@app.post("/system-checks/check-all")', helper_start)
    helper = text[helper_start:helper_end]
    route_start = helper_end
    route_end = text.index('@app.get("/system-checks/{device_id}"', route_start)
    route = text[route_start:route_end]
    assert "execute_update_check(check)" in helper
    assert "run_all_system_checks(notify=True, session_scoped=True)" in route
    assert "perform_update_check" not in helper
    assert "status='failed'" in helper
    assert "except Exception:\\n                pass" not in helper

def test_device_system_checks_is_configuration_state():
    text = Path("app/templates/device_form.html").read_text()
    assert "Enabled" in text
    assert "Not Configured" in text
    assert "system_check.configuration_issue" in text
    assert "Reconfigure System Checks" in text
    assert "device.integration_status=='failed'" not in text

def test_check_selector_cards_are_neutral():
    text = Path("app/templates/system_check_detail.html").read_text()
    assert 'check-state-attention' not in text
    assert 'check-state-critical' not in text

def test_application_version_supports_newer_installed_state():
    main = Path("app/main.py").read_text()
    settings = Path("app/templates/settings.html").read_text()
    assert '"newer_than_release"' in main
    assert "Installed version v{APP_VERSION} is newer than the latest published release" in main
    assert "Newer Version Installed" in settings

def test_dark_number_stepper_and_fixed_columns():
    css = Path("app/static/app.css").read_text()
    assert "color-scheme:dark" in css
    assert "::-webkit-inner-spin-button" in css
    assert "table-layout:fixed" in css
