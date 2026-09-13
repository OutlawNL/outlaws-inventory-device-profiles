from pathlib import Path

MAIN = Path('app/main.py').read_text()
DETAIL = Path('app/templates/system_check_detail.html').read_text()
CSS = Path('app/static/app.css').read_text()


def test_release_version_is_01612():
    assert 'APP_VERSION = "0.18.8"' in MAIN
    assert 'DATABASE_SCHEMA_VERSION = "0.18.8"' in MAIN
    assert 'INSTALLER_VERSION = "0.18.8"' in MAIN


def test_pihole_dns_has_fast_health_refresh_separate_from_daily_versions():
    assert 'def execute_pihole_dns_health_check' in MAIN
    assert "application_type='pihole'" in MAIN
    assert 'execute_pihole_dns_health_check(pihole_check)' in MAIN
    assert 'execute_all_application_checks()' in MAIN


def test_fast_dns_refresh_merges_existing_version_components():
    assert "if str(c.get('key') or '').lower() != 'dns'" in MAIN
    assert "components.insert(0" in MAIN
    assert "status='available'" in MAIN


def test_application_check_copy_describes_health_and_updates():
    assert 'Checks DNS health and Pi-hole updates' in DETAIL
    assert 'Checks server health and Minecraft updates' in DETAIL


def test_http_url_has_matching_section_hierarchy():
    assert 'class="http-url-settings"' in DETAIL
    assert '<strong>HTTP(S) URL</strong>' in DETAIL
    assert '.http-url-settings{' in CSS
    assert 'font-weight:700' in CSS
