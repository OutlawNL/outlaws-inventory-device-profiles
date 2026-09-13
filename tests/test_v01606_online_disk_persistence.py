from pathlib import Path

MAIN = Path('app/main.py').read_text()


def test_release_version_is_v01606():
    assert 'APP_VERSION = "0.18.8"' in MAIN
    assert 'DATABASE_SCHEMA_VERSION = "0.18.8"' in MAIN
    assert 'INSTALLER_VERSION = "0.18.8"' in MAIN


def test_normalization_does_not_force_enable_online_or_disk():
    start = MAIN.index('def _normalize_system_checks_for_device')
    end = MAIN.index('\ndef _normalize_all_system_checks', start)
    block = MAIN[start:end]
    assert 'SET name=?,host=?,enabled=1,group_key=?' not in block
    assert "elif device[\"managed_host\"]:" not in block
    assert 'SET name=?,host=?,group_key=?,updated_at=?' in block


def test_save_health_group_still_removes_unchecked_health_types():
    start = MAIN.index('def _save_health_group')
    end = MAIN.index('\ndef _run_saved_health_group', start)
    block = MAIN[start:end]
    assert 'if check_type not in checks: con.execute("DELETE FROM health_checks' in block


def test_newly_enabled_health_check_is_still_run_immediately():
    start = MAIN.index('def save_system_check_detail')
    end = MAIN.index('\n@app.post("/system-checks/{device_id}/check")', start)
    block = MAIN[start:end]
    assert 'newly_enabled_health_types = requested_health_types - previously_enabled_health_types' in block
    assert 'execute_health_check(health_check)' in block
