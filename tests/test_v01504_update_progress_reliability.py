from pathlib import Path

MAIN = Path("app/main.py").read_text()


def _progress_block() -> str:
    start = MAIN.index("def _application_update_progress_page")
    end = MAIN.index('@app.post("/settings/application-update/rollback")', start)
    return MAIN[start:end]


def test_progress_screen_uses_simple_copy_without_live_status_line():
    block = _progress_block()
    assert "This will take about a minute..." in block
    assert "This page verifies the new version when it returns." not in block
    assert "Starting update…" not in block
    assert "Waiting for Outlaw\\'s Inventory to return…" not in block


def test_status_fetch_is_more_tolerant_but_polling_remains_two_seconds():
    block = _progress_block()
    assert "const pollIntervalMs=2000" in block
    assert "controller.abort(),5000" in block
    assert "window.setTimeout(poll,pollIntervalMs)" in block


def test_success_still_requires_verified_running_target_version():
    block = _progress_block()
    assert "status.state==='completed'" in block
    assert "status.runtime_verified===true" in block
    assert "String(status.app_version||'')===targetVersion" in block
    assert "window.location.replace(successUrl)" in block
