from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
DETAIL = (ROOT / "app/templates/system_check_detail.html").read_text()
LOGIN = (ROOT / "app/templates/login.html").read_text()

def test_version():
    assert 'APP_VERSION = "0.18.8"' in MAIN

def test_http_url_save_reruns_http_and_refreshes_detail_status():
    assert 'check_type == "http" and http_url_changed' in MAIN
    assert 'reloadAfterSave = true' in DETAIL
    assert 'window.setTimeout(() => window.location.reload(), 450)' in DETAIL

def test_login_has_no_application_specific_tabindex_override():
    assert 'tabindex=' not in LOGIN
    assert LOGIN.index('name="username"') < LOGIN.index('name="password"') < LOGIN.index('name="remember_me"') < LOGIN.index('>Sign In</button>')
