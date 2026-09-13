from pathlib import Path

def test_system_check_detail_has_apt_toggle():
    text = Path("app/templates/system_check_detail.html").read_text()
    assert 'name="check_apt_updates"' in text
    assert "APT Package Updates" in text
    assert "managed SSH access" in text

def test_system_check_save_handles_apt_toggle():
    text = Path("app/main.py").read_text()
    assert "check_apt_updates: Optional[str] = Form(None)" in text
    assert "ensure_managed_host_checks(" in text
    assert "enabled=0, status='unknown'" in text

def test_device_page_shows_real_uptime():
    text = Path("app/templates/device_form.html").read_text()
    assert "{{ device_uptime }}" in text
    assert "Available In Details" not in text
