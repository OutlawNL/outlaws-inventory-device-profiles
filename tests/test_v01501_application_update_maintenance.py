from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")


def _block(start: str, end: str) -> str:
    return MAIN[MAIN.index(start):MAIN.index(end, MAIN.index(start))]


def test_release_is_v01501():
    assert 'APP_VERSION = "0.18.8"' in MAIN
    assert 'DATABASE_SCHEMA_VERSION = "0.18.8"' in MAIN
    assert 'INSTALLER_VERSION = "0.18.8"' in MAIN


def test_application_updates_enter_and_leave_temporary_maintenance():
    for fn, remote in (
        ("def execute_pihole_update", "run_remote_pihole_update"),
        ("def execute_minecraft_update", "run_remote_minecraft_update"),
    ):
        block = _block(fn, "\ndef ")
        assert "_begin_temporary_application_update_maintenance(check)" in block
        assert remote in block
        assert "finally:" in block
        assert "_end_temporary_application_update_maintenance(check, maintenance_snapshot)" in block
        assert "execute_application_check(refreshed)" in block


def test_temporary_maintenance_preserves_manual_maintenance_and_previous_health_state():
    begin = _block("def _begin_temporary_application_update_maintenance", "\ndef _end_temporary_application_update_maintenance")
    end = _block("def _end_temporary_application_update_maintenance", "\ndef _device_system_checks_maintenance")
    assert 'if int(row["maintenance"] or 0):' in begin
    assert "status='maintenance'" in begin
    assert '"status": str(row["status"] or "unknown")' in begin
    assert "SET maintenance=0,status=?,response_ms=?,last_error=?" in end
    assert "_application_update_maintenance_devices.discard(key)" in end


def test_notifications_and_schedulers_use_device_maintenance_guard():
    assert "_application_update_maintenance_devices" in MAIN
    helper = _block("def _device_system_checks_maintenance", "\ndef _device_online_status")
    assert "if key in _application_update_maintenance_devices" in helper
    notifications = _block("def collect_notification_events", "\ndef dispatch_notifications")
    assert "not _device_system_checks_maintenance" in notifications


def test_health_check_rereads_maintenance_to_close_scheduler_race():
    block = _block("def execute_health_check", "\ndef run_due_health_checks")
    assert 'SELECT maintenance FROM health_checks WHERE id=?' in block
    assert 'status=\'maintenance\'' in block
