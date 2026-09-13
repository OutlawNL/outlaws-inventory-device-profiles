from pathlib import Path

MAIN = Path("app/main.py").read_text(encoding="utf-8")


def _progress_block() -> str:
    start = MAIN.index("def _application_update_progress_page")
    end = MAIN.index('@app.post("/settings/application-update/rollback")', start)
    return MAIN[start:end]


def _status_block() -> str:
    start = MAIN.index("def _tail_application_update_log")
    end = MAIN.index("BACKUP_FORMAT =", start)
    return MAIN[start:end]


def test_failed_update_status_exposes_only_tail_of_fixed_updater_log():
    block = _status_block()
    assert 'UPDATE_STAGING_DIR / "update.log"' in block
    assert 'lines[-max(1, min(int(max_lines), 100)):]' in block
    failed = block.index('if result_state == "failed"')
    exposed = block.index('result["update_log"] = update_log')
    assert exposed > failed


def test_progress_page_shows_log_only_when_failed_status_contains_it():
    block = _progress_block()
    assert "<summary>Show update log</summary>" in block
    assert "status.state==='failed'" in block
    assert "status.update_log||''" in block
    assert "document.getElementById('update-log').style.display='block'" in block
    assert "document.getElementById('update-log-text').textContent=log" in block


def test_success_path_remains_existing_redirect_without_log_ui_changes():
    block = _progress_block()
    assert "status.state==='completed'" in block
    assert "window.location.replace(successUrl)" in block
