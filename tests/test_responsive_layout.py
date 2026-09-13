from pathlib import Path

def test_system_checks_desktop_column_distribution():
    css = Path("app/static/app.css").read_text()
    assert "final desktop System Checks spacing/responsive safeguard" in css
    assert "td:nth-child(1){width:20%}" in css
    assert "td:nth-child(2){width:20%}" in css
    assert "td:nth-child(3){width:22%}" in css
    assert "td:nth-child(4){width:14%}" in css
    assert "td:nth-child(5){width:12%;text-align:center}" in css

def test_narrow_desktop_uses_scroll_not_overlap():
    css = Path("app/static/app.css").read_text()
    assert ".system-checks-classic-card{" in css
    assert "overflow-x:auto" in css
    assert "min-width:1120px" in css
    assert "width:124px!important" in css

def test_overview_uses_six_columns_and_update_disclosure():
    text = Path("app/templates/system_checks.html").read_text()
    assert "<th>Name</th><th>System</th><th>Application</th><th>Last Checked</th><th>Status</th><th>Action</th>" in text
    assert "<th>Address</th>" not in text
    assert "<th>Updates</th>" not in text
    assert "classic-name-update-toggle" in text
    assert 'aria-expanded="false"' in text
