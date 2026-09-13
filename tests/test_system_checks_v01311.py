from pathlib import Path

def test_system_checks_overview_has_update_disclosure():
    text = Path("app/templates/system_checks.html").read_text()
    assert 'classic-name-update-toggle' in text
    assert 'classic-system-update-details' in text

def test_system_check_detail_autosaves_without_save_button():
    text = Path("app/templates/system_check_detail.html").read_text()
    assert 'data-autosave-system-checks' in text
    assert "Upgrade Now" in text
    assert "Check Now" in text
    assert '>Save</button>' not in text
    assert "<span>Available</span>" not in text
    assert 'class="detail-output classic-detail-packages" open' in text

def test_attention_surfaces_exist():
    text = Path("app/templates/system_check_detail.html").read_text()
    css = Path("app/static/app.css").read_text()
    assert "attention-surface" in text
    assert ".attention-surface" in css

def test_device_summary_links_to_system_check_details():
    text = Path("app/templates/device_form.html").read_text()
    assert '/system-checks/{{ device.id }}#online-status' in text
    assert '/system-checks/{{ device.id }}#updates' in text
    assert "Configured' if health_check" not in text

def test_account_chevron_removed():
    text = Path("app/templates/base.html").read_text()
    assert "user-menu-chevron" not in text
