from pathlib import Path

def test_dashboard_firmware_does_not_get_unknown_border():
    text = Path("app/templates/dashboard.html").read_text()
    marker = '<span>Firmware</span>'
    pos = text.index(marker)
    start = text.rfind('<a class="card card-link', 0, pos)
    end = text.index("</a>", pos) + len("</a>")
    firmware = text[start:end]
    assert "unknown-card" not in firmware
    assert "firmware_updates > 0" in firmware

def test_dashboard_current_status_is_title_case_in_css():
    css = Path("app/static/app.css").read_text()
    block = css[css.index("Dashboard/Settings polish"):]
    assert ".dashboard-hero .eyebrow" in block
    assert "text-transform:none" in block
    assert "letter-spacing:0" in block

def test_settings_group_headings_are_title_case_and_aligned():
    css = Path("app/static/app.css").read_text()
    block = css[css.index("Dashboard/Settings polish"):]
    assert ".settings-group-heading strong" in block
    assert "text-transform:none" in block
    assert "font-size:.91rem" in block
    assert "padding:0 16px" in block

def test_settings_summary_typography_is_stable_open_and_closed():
    css = Path("app/static/app.css").read_text()
    block = css[css.index("Dashboard/Settings polish"):]
    assert ".settings-collapsible[open]>summary strong" in block
    assert ".settings-collapsible:not([open])>summary strong" in block
    assert "font-size:.91rem" in block
    assert "padding-left:16px" in block

def test_device_delete_uses_in_app_confirmation_not_browser_confirm():
    text = Path("app/templates/device_form.html").read_text()
    assert "confirm('Delete this device?')" not in text
    assert "data-delete-device-open" in text
    assert "data-delete-device-dialog" in text
    assert "This action permanently deletes this device and cannot be undone." in text
    assert "I understand that this device will be permanently deleted." in text
    assert "data-delete-device-submit disabled" in text
    assert 'action="/devices/{{ device.id }}/delete"' in text

def test_delete_submit_only_enables_after_checkbox():
    text = Path("app/templates/device_form.html").read_text()
    assert "deleteDeviceSubmit.disabled=!deleteDeviceConfirm.checked" in text
    assert "deleteDeviceSubmit.disabled=true" in text
