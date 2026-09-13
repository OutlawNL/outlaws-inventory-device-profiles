from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _main():
    return (ROOT / 'app/main.py').read_text(encoding='utf-8')


def _block():
    text = _main()
    return text[text.index('def configure_remote_host'):text.index('def ensure_managed_host_checks')]


def test_release_version_01426():
    main = _main()
    for constant in ('APP_VERSION', 'DATABASE_SCHEMA_VERSION', 'INSTALLER_VERSION'):
        assert f'{constant} = "0.18.8"' in main


def test_reconfigure_keeps_proven_01422_ssh_provisioning_pattern():
    block = _block()
    assert '/usr/bin/install -d -m 700 -o ' in block
    assert 'key_file="$home_dir/.ssh/authorized_keys"' in block
    assert '/usr/bin/grep -qxF' in block
    assert 'authorized_keys' in block
    assert '/usr/bin/chown' in block and '/usr/bin/chmod 600' in block


def test_reconfigure_does_not_duplicate_authorized_key():
    block = _block()
    assert 'grep -qxF' in block
    assert '|| /usr/bin/printf' in block


def test_sudoers_fragment_is_merged_not_blindly_replaced():
    block = _block()
    assert 'if [ -f "$sudo_file" ]; then /usr/bin/cat "$sudo_file" > "$sudo_tmp"' in block
    assert 'grep -qxF' in block
    assert '/usr/sbin/visudo -cf "$sudo_tmp"' in block
    assert 'cmp -s "$sudo_tmp" "$sudo_file"' in block
    assert 'printf \'%s\'' not in block or 'sudoers)' not in block


def test_sudoers_exact_pihole_rules_are_only_added_when_enabled():
    block = _block()
    assert 'if enable_pihole:' in block
    assert 'NOPASSWD: /usr/local/bin/pihole -up --check-only' in block
    assert 'NOPASSWD: /usr/local/bin/pihole -up' in block


def test_optional_locale_timezone_cannot_abort_required_setup():
    block = _block()
    assert 'timedatectl set-timezone' not in block
    assert 'current_timezone=' in block
    assert 'current_locale=' in block
    assert 'Warning: optional timezone configuration' in block
    assert 'Warning: optional locale configuration' in block


def test_packages_only_install_when_missing():
    block = _block()
    assert "missing_packages=''" in block
    assert 'dpkg-query -W' in block
    assert 'if [ -n "$missing_packages" ]' in block


def test_reconfigure_validates_real_managed_login_and_all_permissions():
    block = _block()
    for label in (
        'SSH key login', 'APT available', 'APT update permission',
        'APT upgrade permission', 'Kernel upgrade permission', 'Reboot permission',
        'Pi-hole check permission', 'Pi-hole update permission',
    ):
        assert label in block
    assert 'inspect_host_integration(device, profile)' in block


def test_reconfigure_check_form_includes_pihole_and_current_state():
    form = (ROOT / 'app/templates/host_integration_form.html').read_text(encoding='utf-8')
    assert 'name="create_pihole"' in form
    assert 'setup_checks.pihole' in form
