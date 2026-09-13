from pathlib import Path

def test_update_purges_stale_python_bytecode():
    text = Path("update.sh").read_text()
    assert "Clearing Python cache" in text
    assert "find \"$APP_DIR\" -type d -name '__pycache__' -prune -exec rm -rf {} +" in text
    assert "-name '*.pyc'" in text
    assert "-name '*.pyo'" in text

def test_update_verifies_running_app_version_via_ready_endpoint():
    text = Path("update.sh").read_text()
    assert "runtime_version_check()" in text
    assert "/system/ready" in text
    assert "running == expected" in text
    assert 'runtime_version_check "$SOURCE_VERSION"' in text

def test_restore_path_also_purges_bytecode_before_restart():
    text = Path("update.sh").read_text()
    restore = text[text.index("restore_existing()"):text.index("trap finish_update EXIT")]
    assert "__pycache__" in restore
    assert "*.pyc" in restore
    assert 'systemctl restart "$SERVICE"' in restore

def test_gui_self_updater_has_independent_runtime_gate():
    text = Path("scripts/outlaws-inventory-self-update").read_text()
    assert "/system/ready" in text
    assert "Runtime version verification failed" in text
    assert "payload.get('ready') is not True or running != expected" in text
    success_pos = text.index('write_status success "Update completed"')
    runtime_pos = text.index("RUNTIME_VERSION=")
    assert runtime_pos < success_pos
