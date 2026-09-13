from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
DETAIL = (ROOT / "app/templates/system_check_detail.html").read_text()

def test_release_version_01611():
    assert 'APP_VERSION = "0.18.8"' in MAIN
    assert 'DATABASE_SCHEMA_VERSION = "0.18.8"' in MAIN
    assert 'INSTALLER_VERSION = "0.18.8"' in MAIN

def test_pihole_dns_probe_is_functional_local_query():
    assert 'def _pihole_dns_status' in MAIN
    assert "server=('127.0.0.1',53)" in MAIN
    assert "name='example.com'" in MAIN
    assert 'sock.settimeout(2.0)' in MAIN
    assert 'for attempt in range(2)' in MAIN
    assert 'rcode=flags & 0x000f' in MAIN
    assert 'if an<1' in MAIN

def test_pihole_dns_failure_controls_application_health():
    assert "'name':'DNS'" in MAIN
    assert "'status':'ok' if dns.get('ok') else 'failed'" in MAIN
    assert "if not dns.get('ok')" in MAIN
    assert 'Pi-hole DNS is not responding' in MAIN

def test_pihole_dns_is_visible_in_detail_card():
    assert 'DNS health and application update status' in DETAIL
    assert "component.status=='failed'" in DETAIL
    assert 'critical-text' in DETAIL
