from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
SETTINGS = (ROOT / "app/templates/settings.html").read_text()
CSS = (ROOT / "app/static/app.css").read_text()
RELEASE_PROCESS = (ROOT / "docs/RELEASE_PROCESS.md").read_text()
ROADMAP = (ROOT / "docs/ROADMAP.md").read_text()


def test_release_contract_is_v0171():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_release_channel_is_persisted_and_defaults_to_production():
    assert '"application_update_channel": "production"' in MAIN
    assert '@app.post("/settings/application-update/channel")' in MAIN
    assert 'channel = "acceptance" if channel == "acceptance" else "production"' in MAIN
    assert 'check_application_release()' in MAIN[MAIN.index('def set_application_update_channel'):MAIN.index('@app.post("/settings/application-update/test")')]


def test_production_and_acceptance_use_different_github_release_discovery():
    block = MAIN[MAIN.index('def check_application_release'):MAIN.index('def download_release_asset')]
    assert 'releases?per_page=100' in block
    assert 'releases/latest' in block
    assert 'if not item.get("draft")' in block
    assert 'channel == "acceptance"' in block


def test_settings_has_direct_prod_acc_switch_and_acceptance_accent():
    assert '<span>Release Channel</span>' in SETTINGS
    assert '>Production</span>' in SETTINGS
    assert '>Acceptance</span>' in SETTINGS
    assert 'name="channel" value="acceptance"' in SETTINGS
    assert 'onchange="this.form.submit()"' in SETTINGS
    assert 'acceptance-channel' in SETTINGS
    assert '.application-version-card.acceptance-channel' in CSS


def test_release_promotion_and_system_maintenance_are_documented():
    assert 'Do not rebuild or replace the ZIP' in RELEASE_PROCESS
    assert '## System Maintenance' in ROADMAP
    assert 'detect automatically, execute deliberately' in ROADMAP
