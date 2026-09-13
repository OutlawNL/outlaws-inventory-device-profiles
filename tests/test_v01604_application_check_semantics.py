from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app/templates/system_check_detail.html").read_text()
RECONFIGURE = (ROOT / "app/templates/host_integration_form.html").read_text()
MAIN = (ROOT / "app/main.py").read_text()


def test_http_is_grouped_with_application_checks_on_detail_page():
    system_heading = TEMPLATE.index('<div class="check-group-heading">System Checks</div>')
    application_heading = TEMPLATE.index('<div class="check-group-heading">Application Checks</div>')
    http_toggle = TEMPLATE.index('id="enable-http-check"')
    apt_toggle = TEMPLATE.index('name="check_apt_updates"')
    assert system_heading < apt_toggle < application_heading < http_toggle


def test_reconfigure_uses_system_and_application_terminology():
    assert '<strong>System Checks</strong>' in RECONFIGURE
    assert '<strong>Application Checks</strong>' in RECONFIGURE
    assert '<strong>Host checks</strong>' not in RECONFIGURE


def test_enabling_application_check_during_autosave_runs_it_immediately():
    assert 'pihole_was_enabled = bool(existing_pihole and existing_pihole["enabled"])' in MAIN
    assert 'if pihole_check and (not autosave or not pihole_was_enabled):' in MAIN
    assert 'minecraft_was_enabled = bool(existing_minecraft and existing_minecraft["enabled"])' in MAIN
    assert 'if minecraft_check and (not autosave or not minecraft_was_enabled):' in MAIN
