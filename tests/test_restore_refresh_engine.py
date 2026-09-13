from pathlib import Path

def test_shared_check_all_engine_exists_and_button_uses_it():
    text = Path("app/main.py").read_text()
    assert "def run_all_system_checks" in text
    route = text[text.index('@app.post("/system-checks/check-all")'):text.index('@app.get("/system-checks/{device_id}"')]
    assert "run_all_system_checks(notify=True, session_scoped=True)" in route

def test_setup_restore_refresh_is_a_separate_phase_without_notifications():
    text = Path("app/main.py").read_text()
    restore = text[text.index('@app.post("/setup/restore")'):text.index('@app.get("/setup/restore-complete"')]
    refresh = text[text.index('@app.post("/setup/restore-refresh")'):text.index('@app.get("/setup/restore-finish"')]
    assert "restore_full_backup(temporary)" in restore
    assert "run_all_system_checks" not in restore
    assert "run_all_system_checks(notify=False, session_scoped=False)" in refresh

def test_setup_restore_refresh_is_not_session_dependent():
    text = Path("app/main.py").read_text()
    block = text[text.index("def run_all_system_checks"):text.index('@app.post("/system-checks/check-all")')]
    assert "SELECT * FROM health_checks" in block
    assert "ORDER BY owner_user_id,device_id" in block
    assert 'SELECT * FROM update_checks ORDER BY owner_user_id,id' in block

def test_background_update_refresh_resolves_device_by_persisted_owner():
    text = Path("app/main.py").read_text()
    start = text.index("def execute_update_check")
    end = text.find("\ndef ", start + 10)
    block = text[start:end if end != -1 else len(text)]
    assert "fetch_device_for_owner" in block
    assert 'int(check["owner_user_id"] or 0)' in block

def test_refresh_does_not_leave_stale_health_status_on_execution_exception():
    text = Path("app/main.py").read_text()
    block = text[text.index("def run_all_system_checks"):text.index('@app.post("/system-checks/check-all")')]
    assert "SET status='unknown'" in block
    assert "Status refresh failed:" in block

def test_setup_ui_explains_two_phase_restore_refresh():
    text = Path("app/templates/setup_wizard.html").read_text()
    assert "Backup restored successfully" in text
    assert "Refreshing System Checks…" in text
    assert "System Checks completed" in text
