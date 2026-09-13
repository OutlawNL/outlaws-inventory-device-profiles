from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _block():
    main = (ROOT / "app/main.py").read_text()
    return main[main.index("def configure_remote_host"):main.index("def ensure_managed_host_checks")]


def test_release_version_01424():
    main = (ROOT / "app/main.py").read_text()
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in main


def test_reconfigure_installs_packages_only_when_missing():
    block = _block()
    assert "missing_packages=''" in block
    assert "dpkg-query -W" in block
    assert 'if [ -n \"$missing_packages\" ]' in block or 'if [ -n "$missing_packages" ]' in block
    assert "apt-get update && /usr/bin/apt-get install -y $missing_packages" in block


def test_reconfigure_does_not_use_timedatectl_and_optional_settings_cannot_abort():
    block = _block()
    assert "timedatectl set-timezone" not in block
    assert "current_timezone=" in block
    assert "current_locale=" in block
    assert "Warning: optional timezone configuration" in block
    assert "Warning: optional locale configuration" in block


def test_reconfigure_prevents_duplicate_keys_and_rewrites_only_changed_managed_files():
    block = _block()
    assert "grep -qxF" in block
    assert "cmp -s" in block
    assert "authorized_keys" in block
    assert "/etc/sudoers.d/outlaws-inventory" in block
    assert "/usr/local/sbin/outlaws-kernel-upgrade" in block


def test_reconfigure_validates_pihole_permissions_when_enabled():
    block = _block()
    assert "if enable_pihole:" in block
    assert '"Pi-hole check permission", "sudo_pihole_check"' in block
    assert '"Pi-hole update permission", "sudo_pihole_update"' in block


def test_bootstrap_ssh_reload_only_happens_when_temp_file_exists():
    block = _block()
    assert "if [ -e /etc/ssh/sshd_config.d/99-outlaws-bootstrap.conf ]" in block
