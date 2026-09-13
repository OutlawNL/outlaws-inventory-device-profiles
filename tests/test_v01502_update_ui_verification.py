from pathlib import Path

MAIN = Path("app/main.py").read_text()


def _progress_block() -> str:
    start = MAIN.index("def _application_update_progress_page")
    end = MAIN.index('@app.post("/settings/application-update/rollback")', start)
    return MAIN[start:end]


def _status_block() -> str:
    start = MAIN.index('@app.get("/settings/application-update/status")')
    end = MAIN.index("BACKUP_FORMAT =", start)
    return MAIN[start:end]


def test_update_page_polls_every_two_seconds_and_times_out_after_five_minutes():
    block = _progress_block()
    assert "const pollIntervalMs=2000" in block
    assert "const timeoutMs=300000" in block
    assert "window.setTimeout(poll,pollIntervalMs)" in block


def test_update_page_requires_runtime_verification_before_redirect():
    block = _progress_block()
    assert "status.state==='completed'" in block
    assert "status.runtime_verified===true" in block
    assert "String(status.app_version||'')===targetVersion" in block
    assert "window.location.replace(successUrl)" in block


def test_status_endpoint_verifies_helper_runtime_version_and_database():
    block = _status_block()
    assert 'result_state == "success"' in block
    assert "version_tuple(target_version) == version_tuple(APP_VERSION)" in block
    assert 'con.execute("SELECT 1")' in block
    assert "runtime_verified = bool(version_matches and database_ready and helper_succeeded)" in block
    assert '"state": "completed"' in block


def test_status_endpoint_is_not_cacheable():
    block = _status_block()
    assert '"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"' in block
