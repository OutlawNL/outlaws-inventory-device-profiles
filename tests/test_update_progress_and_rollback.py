from pathlib import Path

def test_update_progress_uses_independent_status_verification():
    text = Path("app/main.py").read_text()
    assert "const targetVersion=" in text
    assert "const pollIntervalMs=2000" in text
    assert "/settings/application-update/status?expected=" in text
    assert "status.runtime_verified===true" in text
    assert "300000" in text

def test_progress_page_no_longer_swallows_errors_forever():
    text = Path("app/main.py").read_text()
    start = text.index("function complete(message)")
    end = text.index("@app.post(\"/settings/application-update/rollback\")", start)
    block = text[start:end]
    assert "window.setTimeout(poll,pollIntervalMs)" in block
    assert "did not confirm a successful update within 5 minutes" in block

def test_manual_update_records_immediately_previous_version_for_rollback():
    text = Path("update.sh").read_text()
    assert 'PREVIOUS_VERSION="$(current_installed_version)"' in text
    assert 'publish_manual_rollback "$PREVIOUS_VERSION"' in text
    assert '"version":sys.argv[2]' in text
    assert 'ROLLBACK_STATE="$APP_DIR/data/update-staging/rollback.json"' in text

def test_gui_self_update_does_not_duplicate_manual_rollback_snapshot():
    text = Path("update.sh").read_text()
    assert 'INTERNAL_UPDATE="${OUTLAWS_INTERNAL_UPDATE:-0}"' in text
    assert '[[ "$INTERNAL_UPDATE" == "1" ]] && return 0' in text

def test_manual_rollback_snapshot_is_published_only_after_validation():
    text = Path("update.sh").read_text()
    validation = text.index('runtime_version_check "$SOURCE_VERSION"')
    publish = text.index('publish_manual_rollback "$PREVIOUS_VERSION"')
    assert validation < publish
