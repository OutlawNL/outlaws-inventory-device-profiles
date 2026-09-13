from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_account_device_disclosures_override_profile_padding():
    css = (ROOT / 'app/static/app.css').read_text()
    assert '.account-settings-grid>.account-device-disclosure{padding:0!important}' in css
    assert '.account-settings-grid>.account-device-disclosure>summary{padding:18px 50px 18px 20px}' in css


def test_notification_fields_use_equal_columns():
    css = (ROOT / 'app/static/app.css').read_text()
    assert '.notification-field-grid{grid-template-columns:repeat(2,minmax(0,1fr));max-width:820px}' in css
    html = (ROOT / 'app/templates/settings.html').read_text()
    assert 'notification-url-field' in html
