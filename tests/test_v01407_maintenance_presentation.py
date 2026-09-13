from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_transport_error_helper_covers_ssh_connect_failures():
    text = (ROOT / "app/main.py").read_text()
    assert "def _is_system_check_transport_error" in text
    assert '"unable to connect to port"' in text
    assert '"connection refused"' in text
    assert '"no route to host"' in text

def test_system_check_rows_suppress_transport_error_for_offline_or_maintenance():
    text = (ROOT / "app/main.py").read_text()
    start = text.index("def _system_check_rows")
    end = text.index("\ndef _first_run_counts", start)
    block = text[start:end]
    assert 'item["overall_status"] == "maintenance"' in block
    assert 'ping_status in {"offline", "critical", "failed"}' in block
    assert "_is_system_check_transport_error(raw_update_error)" in block
    assert 'item["display_update_error"] = "" if suppress_transport_error else raw_update_error' in block

def test_maintenance_suppresses_configuration_warning():
    text = (ROOT / "app/main.py").read_text()
    assert 'item["configuration_issue"] = None if item["overall_status"] == "maintenance"' in text

def test_overview_does_not_render_raw_update_errors_under_host():
    template = (ROOT / "app/templates/system_checks.html").read_text()
    assert "server.updates.last_error" not in template
    assert "classic-system-update-details" in template
    assert "server.updates.packages" in template

def test_detail_uses_presentation_error_instead_of_raw_error():
    template = (ROOT / "app/templates/system_check_detail.html").read_text()
    assert "server.update_problem_visible" in template
    assert "server.display_update_error" in template
    assert "server.updates.last_error" not in template

def test_detail_maintenance_neutralizes_update_actions_and_surface():
    template = (ROOT / "app/templates/system_check_detail.html").read_text()
    assert "server.overall_status != 'maintenance' and server.updates.reboot_required" in template
    assert "server.overall_status != 'maintenance' and server.updates and server.updates.package_count" in template
    assert "server.overall_status != 'maintenance' and server.updates.status=='available'" in template

def test_dashboard_excludes_maintenance_devices_from_system_update_counts():
    text = (ROOT / "app/main.py").read_text()
    start = text.index("def dashboard")
    end = text.index('@app.get("/devices"', start)
    block = text[start:end]
    assert "maintenance_device_ids" in block
    assert 'int(row["device_id"] or 0) not in maintenance_device_ids' in block

def test_dashboard_maintenance_alone_is_healthy_overall():
    text = (ROOT / "app/main.py").read_text()
    start = text.index("def dashboard")
    end = text.index('@app.get("/devices"', start)
    block = text[start:end]
    assert 'overall = "maintenance"' not in block
    assert 'overall = "ok"' in block

def test_dashboard_system_checks_tile_still_uses_maintenance_color():
    template = (ROOT / "app/templates/dashboard.html").read_text()
    assert "health_counts.maintenance > 0 %}maintenance-card" in template
    assert "/ {{ health_counts.maintenance }} maintenance" in template

def test_dashboard_does_not_render_maintenance_server_as_failed_update_action():
    text = (ROOT / "app/main.py").read_text()
    start = text.index("def dashboard")
    end = text.index('@app.get("/devices"', start)
    block = text[start:end]
    assert "system_update_actions = [row for row in system_checks" in block
    assert "maintenance_device_ids" in block
