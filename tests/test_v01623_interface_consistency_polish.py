from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/'app/main.py').read_text()
SETTINGS=(ROOT/'app/templates/settings.html').read_text()
CSS=(ROOT/'app/static/app.css').read_text()

def test_version():
    for c in ('APP_VERSION','DATABASE_SCHEMA_VERSION','INSTALLER_VERSION'):
        assert f'{c} = "0.18.8"' in MAIN

def test_account_grouping():
    assert 'account-overview-card' in SETTINGS
    assert 'account-devices-group' in SETTINGS
    assert 'profile-picture-remove' in SETTINGS
    assert 'profile-picture-layout' in SETTINGS

def test_release_notes_root_spacing_fix():
    assert '.inline-details[open]>.application-release-notes{margin-top:12px!important}' in CSS
    assert '.application-version-card .inline-details{margin-bottom:14px!important}' not in CSS
    assert '.application-version-card .inline-details[open]{margin-bottom:16px!important}' not in CSS

def test_normal_button_is_solid():
    tail=CSS.split('/* v0.16.23 — interface consistency polish. */',1)[1]
    assert '.button{background:#24344d;color:#e8eef7}' in tail
