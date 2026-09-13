from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
DETAIL = (ROOT / "app/templates/system_check_detail.html").read_text()


def test_release_version_01617():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_pihole_check_is_noninteractive_and_bounded():
    assert 'sudo -n /usr/local/bin/pihole -up --check-only </dev/null' in MAIN
    assert 'timeout=90' in MAIN


def test_healthy_dns_with_update_check_failure_is_unknown_not_failed():
    assert "parsed['update_check']={'status':'unknown','detail':detail}" in MAIN
    assert "return {'status':'unknown','details':parsed,'error':error}" in MAIN
    assert 'Pi-hole update check could not query GitHub. DNS is responding normally.' in MAIN


def test_dns_refresh_preserves_unknown_update_failure():
    assert "if update_state == 'unknown':" in MAIN
    assert "error=str(check['last_error'] or '')" in MAIN


def test_pihole_diagnostic_output_is_visible_on_detail_page():
    assert 'Update Check Details' in DETAIL
    assert 'server.pihole.details.output' in DETAIL


def test_unknown_application_check_with_error_is_notifiable():
    assert 'r["status"] == "unknown" and str(r["last_error"] or "").strip()' in MAIN
