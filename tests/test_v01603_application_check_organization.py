from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app/templates/system_check_detail.html").read_text()
CSS = (ROOT / "app/static/app.css").read_text()
MAIN = (ROOT / "app/main.py").read_text()


def test_release_version_is_0163():
    assert 'APP_VERSION = "0.18.8"' in MAIN
    assert 'DATABASE_SCHEMA_VERSION = "0.18.8"' in MAIN
    assert 'INSTALLER_VERSION = "0.18.8"' in MAIN


def test_checks_are_grouped_without_changing_selectors():
    assert '>System Checks</div>' in TEMPLATE
    assert '>Application Checks</div>' in TEMPLATE
    for name in ('check_ping', 'check_disk', 'check_http', 'check_apt_updates', 'check_pihole', 'check_minecraft'):
        assert f'name="{name}"' in TEMPLATE
    assert 'check-group-divider' in TEMPLATE


def test_minecraft_jar_configuration_lives_in_minecraft_card():
    minecraft_start = TEMPLATE.index('<div id="minecraft-updates"')
    minecraft_end = TEMPLATE.index('{% if server.pihole %}', minecraft_start)
    minecraft = TEMPLATE[minecraft_start:minecraft_end]
    assert '<summary>Configuration</summary>' in minecraft
    assert 'name="minecraft_jar_path"' in minecraft
    checks_start = TEMPLATE.index('<div id="checks"')
    checks_end = TEMPLATE.index('<div id="history"', checks_start)
    checks = TEMPLATE[checks_start:checks_end]
    assert 'Minecraft server JAR path' not in checks


def test_application_toggle_autosave_refreshes_detail_page():
    assert 'data-application-check-toggle' in TEMPLATE
    assert 'reloadAfterSave = true' in TEMPLATE
    assert 'window.location.reload()' in TEMPLATE


def test_application_blocks_remain_conditioned_on_enabled_server_state():
    assert '{% if server.minecraft %}' in TEMPLATE
    assert '{% if server.pihole %}' in TEMPLATE
    assert 'if not device_id or not row["enabled"]' in MAIN


def test_minecraft_configuration_is_collapsed_by_default():
    assert '<details class="minecraft-configuration-disclosure">' in TEMPLATE
    assert '<details class="minecraft-configuration-disclosure" open>' not in TEMPLATE
    assert '.minecraft-configuration-disclosure' in CSS
