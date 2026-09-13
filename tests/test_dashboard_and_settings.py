from pathlib import Path

def test_dashboard_has_four_kpi_cards():
    text = Path("app/templates/dashboard.html").read_text()
    assert 'class="grid cards4 dashboard-kpis dashboard-kpis-four"' in text
    block = text[text.index('class="grid cards4 dashboard-kpis dashboard-kpis-four"'):]
    block = block[:block.index("</div>") + len("</div>")]
    assert block.count('<a class="card card-link') == 4
    assert "Firmware OK" not in block
    assert "Firmware Updates" not in block
    assert "Application Updates" not in block
    assert '<span class="label dashboard-label-icon">' in block and '<span>Firmware</span>' in block

def test_dashboard_application_update_is_conditional_banner():
    text = Path("app/templates/dashboard.html").read_text()
    assert "{% if application_update.update_available %}" in text
    assert 'class="dashboard-application-update-banner"' in text
    assert "Outlaw's Inventory v{{ application_update.latest_version }} is available" in text
    assert '/settings?update_open=1#application-version' in text

def test_settings_has_three_visual_groups():
    text = Path("app/templates/settings.html").read_text()
    assert '<strong>Personal</strong><small>Account and notifications.</small>' in text
    assert '<strong>Application</strong><small>Inventory structure, data, integrations and application maintenance.</small>' in text
    assert '<strong>Administration</strong><small>Installation-wide controls, access, diagnostics and system actions.</small>' in text

def test_settings_remains_single_accordion():
    text = Path("app/templates/settings.html").read_text()
    assert text.count('<div class="settings-accordion" data-settings-accordion>') == 1
    assert "querySelectorAll(':scope > details.settings-collapsible')" in text
    assert "other.open = false" in text

def test_dashboard_css_keeps_four_card_responsive_layout_and_compact_rows():
    css = Path("app/static/app.css").read_text()
    block = css[css.index("Dashboard simplification and Settings hierarchy"):]
    assert "grid-template-columns:repeat(4,minmax(0,1fr))!important" in block
    assert ".settings-group-heading" in block
    assert ".settings-collapsible:not([open])>summary" in block
    assert "grid-template-columns:repeat(2,minmax(0,1fr))!important" in block
    assert "grid-template-columns:1fr!important" in block
