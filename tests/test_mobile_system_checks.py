from pathlib import Path

def test_mobile_system_checks_has_only_name_and_status_source_columns():
    text = Path("app/templates/system_checks.html").read_text()
    assert '<table class="system-checks-mobile-table"' in text
    mobile = text[text.index('<table class="system-checks-mobile-table"'):]
    mobile = mobile[:mobile.index("</table>") + len("</table>")]
    assert "<th>Name</th><th>Status</th>" in mobile
    assert "<th>Checks</th>" not in mobile
    assert "<th>Last Checked</th>" not in mobile
    assert "<th>Action</th>" not in mobile

def test_mobile_status_links_to_system_check_details():
    text = Path("app/templates/system_checks.html").read_text()
    mobile = text[text.index('<table class="system-checks-mobile-table"'):]
    mobile = mobile[:mobile.index("</table>") + len("</table>")]
    assert 'class="status-link" href="/system-checks/{{ server.id }}"' in mobile

def test_desktop_system_checks_table_uses_six_columns():
    text = Path("app/templates/system_checks.html").read_text()
    desktop = text[text.index('<table class="system-checks-classic-table system-checks-desktop-table"'):]
    desktop = desktop[:desktop.index("</table>") + len("</table>")]
    assert "<th>Name</th><th>System</th><th>Application</th><th>Last Checked</th><th>Status</th><th>Action</th>" in desktop

def test_mobile_uses_dedicated_two_column_table_without_desktop_overflow():
    css = Path("app/static/app.css").read_text()
    assert "System Checks phone view" in css
    assert ".system-checks-desktop-table{" in css
    assert ".system-checks-mobile-table{" in css
    assert "display:table!important" in css
