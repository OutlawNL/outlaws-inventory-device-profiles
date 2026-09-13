from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SETTINGS=(ROOT/'app/templates/settings.html').read_text()
CSS=(ROOT/'app/static/app.css').read_text()
UI=(ROOT/'docs/UI_STYLE.md').read_text()
README=(ROOT/'README.md').read_text()
TODO=(ROOT/'docs/TODO.md').read_text()
SYSTEM=(ROOT/'docs/SYSTEM_CHECKS.md').read_text()

def test_v01624_version():
    main=(ROOT/'app/main.py').read_text()
    for c in ('APP_VERSION','DATABASE_SCHEMA_VERSION','INSTALLER_VERSION'):
        assert f'{c} = "0.18.8"' in main

def test_account_picture_contains_only_picture_controls():
    block=SETTINGS.split('<section class="profile-identity-card">',1)[1].split('</section>',1)[0]
    assert '<h3>Account Picture</h3>' in block
    assert "@{{ current_user['username'] }}" not in block
    assert "current_user['display_name']" not in block
    assert 'profile-picture-remove' in block
    assert 'profile-avatar-help' in block
    assert 'JPG, PNG or WEBP. Maximum 5 MB.' in block

def test_account_picture_alignment_css():
    assert '/* v0.16.24 — Account Picture alignment' in CSS
    assert '.profile-picture-visual{justify-items:center;align-content:start}' in CSS
    assert '.profile-picture-remove{min-width:104px;text-align:center}' in CSS

def test_title_case_rule_is_documented():
    assert 'Use **Title Case** for interface labels and control text' in UI
    assert 'Use **sentence case** for explanatory copy' in UI
    for label in ('Account Picture','Active Sessions','Backup Now','Application Version'):
        assert label in UI

def test_current_documentation_baseline_and_features():
    assert 'supported technical baseline is **v0.15.0 or newer**' in README
    assert 'Pi-hole DNS/update health' in README
    assert 'Minecraft runtime/version health' in README
    assert 'Current technical baseline: **v0.15.0+**' in TODO
    assert 'Current release line: **v0.18.x**' in TODO
    assert 'A failed/incomplete version lookup while DNS responds is Unknown' in SYSTEM
