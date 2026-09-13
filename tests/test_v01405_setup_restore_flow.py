from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_restore_post_stops_after_successful_restore_and_does_not_run_checks_inline():
    text = (ROOT / "app/main.py").read_text()
    start = text.index('@app.post("/setup/restore")')
    end = text.index('@app.get("/setup/restore-complete"', start)
    block = text[start:end]
    assert "validate_full_backup(temporary)" in block
    assert "restore_full_backup(temporary)" in block
    assert "_write_setup_restore_result()" in block
    assert "run_all_system_checks" not in block
    assert block.index("validate_full_backup(temporary)") < block.index("restore_full_backup(temporary)")

def test_restore_refresh_is_a_separate_token_authorized_phase():
    text = (ROOT / "app/main.py").read_text()
    start = text.index('@app.post("/setup/restore-refresh")')
    end = text.index('@app.get("/setup/restore-finish"', start)
    block = text[start:end]
    assert "_read_setup_restore_result(token)" in block
    assert 'result.get("phase") != "restored"' in block
    assert "run_all_system_checks(notify=False, session_scoped=False)" in block
    assert 'result["phase"] = "checked"' in block

def test_restore_finish_consumes_temporary_state_before_login():
    text = (ROOT / "app/main.py").read_text()
    start = text.index('@app.get("/setup/restore-finish")')
    end = text.index('@app.get("/setup/complete"', start)
    block = text[start:end]
    assert "_consume_setup_restore_result(token)" in block
    assert 'RedirectResponse("/login?next=/"' in block

def test_restore_ui_has_two_distinct_verified_steps():
    template = (ROOT / "app/templates/setup_wizard.html").read_text()
    assert "Backup restored successfully" in template
    assert "Refreshing System Checks…" in template
    assert "System Checks completed" in template
    assert "/setup/restore-refresh" in template
    assert "/setup/restore-finish?token={{ restore_token }}" in template

def test_restore_failure_cannot_start_check_refresh():
    text = (ROOT / "app/main.py").read_text()
    restore_start = text.index('@app.post("/setup/restore")')
    restore_end = text.index('@app.get("/setup/restore-complete"', restore_start)
    restore = text[restore_start:restore_end]
    assert "except Exception as exc:" in restore
    assert "Restore failed:" in restore
    assert "run_all_system_checks" not in restore

def test_refresh_failure_is_not_described_as_restore_failure():
    template = (ROOT / "app/templates/setup_wizard.html").read_text()
    assert "Backup restore succeeded." in template
    assert "automatic status refresh did not finish" in template
    assert "The restored data is intact" in template
