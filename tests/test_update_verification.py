from pathlib import Path

def test_manual_update_uses_checksum_rsync():
    text = Path("update.sh").read_text()
    assert "rsync -a --checksum --delete" in text

def test_manual_update_verifies_version_after_copy_and_restart():
    text = Path("update.sh").read_text()
    assert "INSTALLED_VERSION_AFTER_COPY" in text
    assert "Version verification failed after copying files" in text
    assert "INSTALLED_VERSION_AFTER_RESTART" in text
    assert "Version verification failed after restart" in text

def test_self_updater_cannot_report_success_on_wrong_installed_version():
    text = Path("scripts/outlaws-inventory-self-update").read_text()
    assert 'INSTALLED_VERSION="$(python3 - "$APP_DIR/app/main.py"' in text
    assert 'if [[ "$INSTALLED_VERSION" != "$VERSION" ]]' in text
    assert 'write_status failed "Version verification failed"' in text
