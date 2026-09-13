from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
DETAIL = (ROOT / "app/templates/system_check_detail.html").read_text()
LOGIN = (ROOT / "app/templates/login.html").read_text()

def test_version():
    assert 'APP_VERSION = "0.18.8"' in MAIN

def test_http_url_enter_and_blur_autosave():
    assert "httpUrlInput.addEventListener('blur', saveHttpUrlIfChanged)" in DETAIL
    assert "if (event.key !== 'Enter') return" in DETAIL
    assert "event.preventDefault()" in DETAIL

def test_changed_http_url_reruns_only_http_health_check_path():
    assert 'http_url_changed = "http" in set(checks)' in MAIN
    assert 'check_type == "http" and http_url_changed' in MAIN

def test_login_uses_native_focusable_controls_in_dom_order():
    username = LOGIN.index('name="username"')
    password = LOGIN.index('name="password"')
    remember = LOGIN.index('name="remember_me"')
    submit = LOGIN.index('>Sign In</button>')
    assert username < password < remember < submit
    assert 'tabindex=' not in LOGIN
