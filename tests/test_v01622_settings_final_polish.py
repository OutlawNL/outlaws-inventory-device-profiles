from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'app/templates/settings.html').read_text()
CSS=(ROOT/'app/static/app.css').read_text()
MAIN=(ROOT/'app/main.py').read_text()

def test_version():
    for c in ('APP_VERSION','DATABASE_SCHEMA_VERSION','INSTALLER_VERSION'):
        assert f'{c} = "0.18.8"' in MAIN

def test_account_and_settings_polish():
    assert 'account-overview-card' in HTML
    assert 'account-devices-group' in HTML
    assert '.application-version-card .inline-details{margin-bottom:12px!important}' in CSS
    assert '.application-version-card .inline-details[open]>.application-release-notes{margin-top:12px!important}' in CSS
    assert '.notification-actions{margin-top:12px!important}' in CSS
    assert '.button{background:#24344d;color:#e8eef7}' in CSS
    assert 'class="button primary"' not in HTML
