from pathlib import Path

def test_overview_update_disclosure_is_single_and_closed_by_default():
    text = Path("app/templates/system_checks.html").read_text()
    assert ' available' in text
    assert 'update{% if server.updates.package_count != 1 %}s{% endif %}' in text
    assert 'aria-expanded="false"' in text
    assert 'classic-system-update-details" hidden' in text
    assert '<details open>' not in text

def test_detail_upgrade_has_operation_overlay():
    text = Path("app/templates/system_check_detail.html").read_text()
    assert 'data-operation="upgrade"' in text
    assert 'data-operation-overlay' in text
    assert 'Upgrading ${name}…' in text
    assert 'This can take several minutes. The server will be checked again automatically.' in text

def test_dashboard_uses_device_wording_not_health_host():
    text = Path("app/templates/dashboard.html").read_text()
    assert "health host(s)" not in text
    assert "device{% if" in text

def test_status_action_alignment_css_exists():
    css = Path("app/static/app.css").read_text()
    assert ".system-checks-classic-table th:nth-child(6)" in css
    assert ".system-checks-classic-table td:nth-child(7)" in css
