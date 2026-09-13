from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")
SYSTEM = (ROOT / "app/templates/system_checks.html").read_text(encoding="utf-8")
FIRMWARE = (ROOT / "app/templates/firmware.html").read_text(encoding="utf-8")


def test_release_version_is_01630():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_check_all_runs_in_background_with_user_scoped_server_state():
    assert '_OPERATION_STATES: dict[tuple[int, str]' in MAIN
    assert 'def _start_user_operation(' in MAIN
    assert 'threading.Thread(target=worker' in MAIN
    assert '_CURRENT_USER_ID.set(int(user_id))' in MAIN
    assert '_start_user_operation("firmware-check-all"' in MAIN
    assert '"system-check-all",' in MAIN


def test_overview_pages_receive_running_state_after_reload():
    assert 'check_all_running=_operation_state("firmware-check-all")["running"]' in MAIN
    assert 'check_all_running=_operation_state("system-check-all")["running"]' in MAIN
    assert "data-running=\"{{ 'true' if check_all_running else 'false' }}\"" in SYSTEM
    assert "data-running=\"{{ 'true' if check_all_running else 'false' }}\"" in FIRMWARE
    assert '{% if check_all_running %}<span class="button-spinner"' in SYSTEM
    assert '{% if check_all_running %}<span class="button-spinner"' in FIRMWARE


def test_check_all_status_endpoints_exist_and_are_polled():
    assert '@app.get("/system-checks/check-all/status"' in MAIN
    assert '@app.get("/firmware/check-all/status"' in MAIN
    assert '/system-checks/check-all/status?' in SYSTEM
    assert '/firmware/check-all/status?' in FIRMWARE
    assert 'window.setInterval(pollSystemCheckAll, 1500)' in SYSTEM
    assert 'window.setInterval(poll, 1500)' in FIRMWARE


def test_completion_refreshes_overview_but_reload_does_not_cancel_worker():
    assert "window.location.replace('/system-checks')" in SYSTEM
    assert "window.location.replace('/firmware')" in FIRMWARE
    assert "button.dataset.running==='true'" in SYSTEM
    assert "button.dataset.running === 'true'" in FIRMWARE
