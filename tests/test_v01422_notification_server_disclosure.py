from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_notification_server_is_nested_disclosure():
    html = (ROOT / "app/templates/settings.html").read_text()
    assert 'class="notification-server-disclosure"' in html
    assert '<strong>E-mail Server</strong>' in html
    assert '{% if not smtp_configured %}open{% endif %}' in html
    assert 'Save Notification Settings' in html
    assert 'Send Test E-mail' in html

def test_release_version():
    main = (ROOT / "app/main.py").read_text()
    assert 'APP_VERSION = "0.18.8"' in main
