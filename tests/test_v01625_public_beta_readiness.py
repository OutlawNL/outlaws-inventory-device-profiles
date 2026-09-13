from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")
SETTINGS = (ROOT / "app/templates/settings.html").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
SECURITY = (ROOT / "docs/SECURITY.md").read_text(encoding="utf-8")
INSTALL = (ROOT / "install.sh").read_text(encoding="utf-8")
UPDATE = (ROOT / "update.sh").read_text(encoding="utf-8")


def test_release_version_is_01625():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_system_action_feedback_returns_to_its_own_disclosure():
    assert "system_action_message=Outlaw%27s+Inventory+restarted+successfully." in MAIN
    assert "system_actions_open=1#system-actions" in MAIN
    assert 'id="system-actions"' in SETTINGS
    assert "system_actions_open == '1'" in SETTINGS
    assert "system_action_message" in SETTINGS
    assert "update_message=Outlaw%27s+Inventory+restarted+successfully" not in MAIN



def test_private_runtime_files_have_restrictive_defaults():
    assert "UMask=0077" in INSTALL
    assert "UMask=0077" in UPDATE
    assert "for private_dir in (UPLOAD_DIR, AVATAR_DIR, BACKUP_DIR)" in MAIN
    assert "path.chmod(0o600)" in MAIN


def test_attachment_upload_is_bounded_and_randomized():
    assert "await file.read(DEVICE_EXPORT_MAX_BYTES + 1)" in MAIN
    assert 'stored = f"{device_id}-{uuid.uuid4().hex}{suffix}"' in MAIN
    assert "Attachment+must+be+50+MB+or+smaller" in MAIN
    assert "attachment_path.chmod(0o600)" in MAIN


def test_public_self_hosted_security_documentation_exists():
    assert "self-hosted" in README.lower()
    assert "centrally hosted/SaaS edition is not part" in README
    assert "Do not expose the built-in HTTP service directly to the public Internet" in README
    assert "# Security" in SECURITY
    assert "Full backups contain secrets" in SECURITY
