from pathlib import Path

def test_authentication_failure_is_classified_as_configuration_issue():
    text = Path("app/main.py").read_text()
    assert "def _system_check_configuration_issue" in text
    assert '"authentication failed"' in text
    assert '"permission denied"' in text
    assert '"SSH access to this host could not be authenticated.' in text
    assert 'item["configuration_issue"] = None if item["overall_status"] == "maintenance" else _system_check_configuration_issue(item)' in text

def test_system_checks_overview_hides_raw_authentication_error():
    text = Path("app/templates/system_checks.html").read_text()
    assert "server.updates.last_error" not in text
    # Existing update package expansion remains intact.
    assert "server.updates.packages" in text
    assert "update-details-{{ server.id }}" in text

def test_device_page_surfaces_configuration_issue_and_reconfigure_action():
    text = Path("app/templates/device_form.html").read_text()
    assert "system_check.configuration_issue" in text
    assert ">Attention</span>" in text
    assert "Reconfigure System Checks" in text
    assert "host-integration?reconfigure=1&return_to=device" in text
    assert "Open Details" in text

def test_system_check_detail_has_reconfigure_action():
    text = Path("app/templates/system_check_detail.html").read_text()
    assert "server.configuration_issue" in text
    assert "Reconfigure System Checks" in text
    assert "host-integration?reconfigure=1&return_to=system-checks" in text

def test_existing_host_integration_can_be_forced_back_into_configuration_form():
    text = Path("app/templates/host_integration.html").read_text()
    assert "request.query_params.get('reconfigure') == '1'" in text
    assert "and not reconfigure" in text
    assert "Reconfigure System Checks" in text

def test_successful_reconfigure_returns_to_calling_page():
    text = Path("app/main.py").read_text()
    assert 'return_to == "system-checks"' in text
    assert 'RedirectResponse(f"/system-checks/{device_id}"' in text
    assert 'return_to == "device"' in text
    assert 'RedirectResponse(f"/devices/{device_id}"' in text

def test_recent_activity_has_standard_vertical_spacing():
    css = Path("app/static/app.css").read_text()
    block = css[css.index("v0.14.2 — System Checks reconfiguration"):]
    assert ".device-history" in block
    assert "margin-top:16px!important" in block
