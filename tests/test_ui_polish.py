from pathlib import Path

def test_system_checks_overview_has_six_columns():
    text = Path("app/templates/system_checks.html").read_text()
    assert "<th>Name</th><th>System</th><th>Application</th><th>Last Checked</th><th>Status</th><th>Action</th>" in text
    assert "<th>Address</th>" not in text
    assert "<th>Updates</th>" not in text
    assert 'colspan="7"' not in text
    assert 'colspan="6"' in text

def test_update_disclosure_is_preserved_and_collapsed():
    text = Path("app/templates/system_checks.html").read_text()
    assert "classic-name-update-toggle" in text
    assert "updates.package_count" in text
    assert 'aria-expanded="false"' in text
    assert 'classic-system-update-details" hidden' in text

def test_status_action_controls_share_geometry():
    css = Path("app/static/app.css").read_text()
    assert "System Checks cross-browser table normalization" in css
    assert "height:32px!important" in css
    assert "vertical-align:middle!important" in css
    assert "table-layout:fixed" in css
