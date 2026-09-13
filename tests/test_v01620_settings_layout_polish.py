from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/static/app.css").read_text()
SETTINGS = (ROOT / "app/templates/settings.html").read_text()
DEVICE = (ROOT / "app/templates/device_form.html").read_text()
MAIN = (ROOT / "app/main.py").read_text()


def test_version_is_01620():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_device_attachment_spacing_is_explicit_and_history_independent():
    assert 'class="card full device-attachments-card"' in DEVICE
    assert '.device-main-form + .device-attachments-card' in CSS
    assert '.device-history + .device-attachments-card' in CSS


def test_backup_restore_actions_use_compact_rows_without_changing_actions():
    assert 'backup-manual-grid backup-compact-actions' in SETTINGS
    assert 'action="/settings/backups/create"' in SETTINGS
    assert 'action="/settings/backups/restore-upload"' in SETTINGS
    assert '.backup-compact-actions .backup-manual-panel' in CSS
    assert 'grid-template-columns:minmax(260px,1fr) auto' in CSS


def test_account_release_notes_and_system_actions_are_compacted():
    assert 'application-release-notes' in SETTINGS
    assert '.application-release-notes>strong' in CSS
    assert '.account-settings-grid>.account-device-disclosure>summary' in CSS
    assert '.system-actions-card>.collapsible-content' in CSS
