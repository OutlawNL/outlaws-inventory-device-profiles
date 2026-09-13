from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
SETTINGS = (ROOT / "app/templates/settings.html").read_text()
BACKUPS = (ROOT / "docs/BACKUPS.md").read_text()
SECURITY = (ROOT / "docs/SECURITY.md").read_text()
RELEASE_PROCESS = (ROOT / "docs/RELEASE_PROCESS.md").read_text()


def test_release_contract_is_v0171():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_release_channel_labels_are_expanded_without_changing_switch_contract():
    assert '>Production</span>' in SETTINGS
    assert '>Acceptance</span>' in SETTINGS
    assert '>Prod</span>' not in SETTINGS
    assert '>Acc</span>' not in SETTINGS
    assert 'name="channel" value="acceptance"' in SETTINGS
    assert 'onchange="this.form.submit()"' in SETTINGS
    assert 'acceptance-channel' in SETTINGS


def test_backup_and_distribution_secret_boundary_is_documented():
    assert 'complete recovery artifact' in BACKUPS
    assert 'GitHub access token and SMTP secret' in BACKUPS
    assert 'distribution ZIP does **not** contain instance-specific tokens' in BACKUPS
    assert 'Release/distribution ZIPs' in SECURITY
    assert 'must not contain runtime data, instance tokens, credentials, keys or local secrets' in SECURITY


def test_private_beta_token_ownership_and_public_goal_are_documented():
    assert 'Each private-beta installation/user should use its own token' in RELEASE_PROCESS
    assert 'public GitHub repository should work without requiring a personal access token' in RELEASE_PROCESS
