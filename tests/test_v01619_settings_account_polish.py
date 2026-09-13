from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
SETTINGS = (ROOT / "app/templates/settings.html").read_text()
CSS = (ROOT / "app/static/app.css").read_text()


def test_release_version_is_v01619():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_avatar_remove_is_neutral_not_destructive():
    marker = 'formaction="/profile/avatar/delete"'
    pos = SETTINGS.index(marker)
    button_start = SETTINGS.rfind('<button', 0, pos)
    button = SETTINGS[button_start:pos]
    assert 'button secondary' in button
    assert 'danger-outline' not in button


def test_mfa_uses_compact_state_not_pill():
    assert 'class="mfa-state ' in SETTINGS
    assert 'mfa-state-mark' in SETTINGS
    assert '<span class="pill {{ \'ok\' if current_user[\'mfa_enabled\']' not in SETTINGS
    assert '.mfa-state.enabled{color:var(--ok)}' in CSS


def test_settings_polish_is_targeted():
    assert '.settings-collapsible>summary strong{font-size:18px' in CSS
    assert '.settings-collapsible>summary small{font-size:14px' in CSS
    assert '.settings-group-heading strong{font-size:16px' in CSS
    assert '.notification-note{margin-top:8px}' in CSS
    assert '.notification-server-disclosure{margin-bottom:12px}' in CSS
