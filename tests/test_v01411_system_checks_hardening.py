from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_old_health_and_updates_pages_redirect_to_system_checks():
    text = (ROOT / "app/main.py").read_text()
    for route in ('/health"', '/health/new"', '/health/{check_id}"', '/updates"', '/updates/new"', '/updates/{check_id}"'):
        assert route in text
    assert 'TemplateResponse("health.html"' not in text
    assert 'TemplateResponse("health_form.html"' not in text
    assert 'TemplateResponse("updates.html"' not in text
    assert 'TemplateResponse("update_form.html"' not in text

def test_old_health_and_updates_templates_are_removed():
    templates = ROOT / "app/templates"
    for name in ("health.html","health_form.html","updates.html","update_form.html"):
        assert not (templates / name).exists()

def test_ping_has_one_retry_before_existing_tcp_fallback():
    text = (ROOT / "app/main.py").read_text()
    block = text[text.index("def _ping_host"):text.index("\ndef _http_check")]
    assert "for _attempt in range(2):" in block
    assert '["ping", "-c", "1", "-W", "2", host]' in block
    assert "_tcp_probe_host(host)" in block

def test_maintenance_blocks_daily_update_checks():
    text = (ROOT / "app/main.py").read_text()
    block = text[text.index("def execute_all_update_checks"):text.index('@app.post("/updates/check-all")')]
    assert "_device_system_checks_maintenance" in block

def test_maintenance_blocks_update_notifications_as_safety_net():
    text = (ROOT / "app/main.py").read_text()
    start = text.index("def collect_notification_events")
    end = text.index("\ndef dispatch_notifications(", start)
    block = text[start:end]
    assert "not _device_system_checks_maintenance" in block

def test_notifications_use_system_checks_user_facing_category():
    text = (ROOT / "app/main.py").read_text()
    block = text[text.index("def dispatch_notifications"):text.index("\ndef _parse_setting_datetime")]
    assert 'category = "System Checks" if key.startswith(("health:", "updates:", "appupdates:")) else "Firmware"' in block
    assert 'category = "Health"' not in block

def test_disk_check_skips_ssh_when_online_status_is_offline():
    text = (ROOT / "app/main.py").read_text()
    block = text[text.index("def run_health_check"):text.index("\ndef _health_last_checked")]
    assert '_device_online_status' in block
    assert '== "offline"' in block
    assert '_disk_usage_check(check)' in block

def test_http_check_remains_independent_of_ping_failure():
    text = (ROOT / "app/main.py").read_text()
    block = text[text.index("def run_health_check"):text.index("\ndef _health_last_checked")]
    assert 'if check_type == "http":' in block
    assert '_http_check(target)' in block

def test_no_active_home_lab_wording_remains_in_main():
    text = (ROOT / "app/main.py").read_text().lower()
    assert "home lab" not in text
    assert "homelab" not in text


def test_update_check_refreshes_online_status_before_ssh_work():
    text = (ROOT / "app/main.py").read_text()
    assert "def _ensure_current_online_status" in text
    block = text[text.index("def execute_update_check"):text.index("\ndef fetch_users")]
    assert "_ensure_current_online_status(device_id, owner_user_id)" in block
    assert '== "offline"' in block

def test_setup_restore_uses_system_checks_wording():
    template = (ROOT / "app/templates/setup_wizard.html").read_text()
    assert "Refreshing current System Checks." in template
    assert "Checking current health and available system updates." not in template
